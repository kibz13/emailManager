import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from src.api.gmail_client import GmailClient
from src.config import (
    CLIENT_CONFIG,
    SCOPES,
    CREDENTIALS_FILE,
    CORS_ORIGINS,
)
from src.scheduler import CleanupJob, SchedulerManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

OAUTH_REDIRECT_URI = CLIENT_CONFIG["installed"]["redirect_uris"][0]


def load_credentials_from_file(path: str) -> Credentials | None:
    try:
        with open(path, "r") as f:
            data = json.load(f)
        creds = Credentials(
            token=data.get("token"),
            refresh_token=data.get("refresh_token"),
            token_uri=data.get("token_uri"),
            client_id=data.get("client_id"),
            client_secret=data.get("client_secret"),
            scopes=data.get("scopes"),
        )
        if creds.expired and creds.refresh_token:
            creds.refresh(GoogleRequest())
            save_credentials_to_file(creds, path)
            logger.info("Credentials refreshed and saved.")
        if not creds.valid:
            return None
        return creds
    except FileNotFoundError:
        logger.info(f"Credentials file not found: {path}")
        return None
    except Exception as e:
        logger.error(f"Failed to load credentials from {path}: {e}")
        return None


def save_credentials_to_file(creds: Credentials, path: str):
    data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes) if creds.scopes else SCOPES,
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    logger.info(f"Credentials saved to {path}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    app.state.scheduler_manager = SchedulerManager()

    creds = load_credentials_from_file(CREDENTIALS_FILE)
    if creds:
        app.state.gmail_client = GmailClient(client_credentials=creds)
        logger.info("Gmail client initialized from saved credentials.")
    else:
        app.state.gmail_client = None
        logger.warning("No valid credentials found. Use /auth/initiate to authenticate.")

    def scheduled_cleanup():
        if app.state.gmail_client is None:
            logger.warning("Scheduler: no Gmail client, skipping cleanup.")
            return
        job = CleanupJob()
        job.run(app.state.gmail_client, app.state.scheduler_manager)

    scheduler = BackgroundScheduler(daemon=True)
    sm = app.state.scheduler_manager
    scheduler.add_job(
        scheduled_cleanup,
        CronTrigger(hour=sm.state.cron_hour, minute=sm.state.cron_minute),
        id="cleanup",
        replace_existing=True,
    )
    scheduler.start()
    app.state.scheduler = scheduler
    logger.info(
        f"Scheduler started. Cleanup runs daily at {sm.state.cron_hour:02d}:{sm.state.cron_minute:02d} UTC."
    )

    yield

    # Shutdown
    scheduler.shutdown(wait=False)
    logger.info("Scheduler shut down.")


app = FastAPI(title="Gmail Eraser", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {
        "status": "ok",
        "authenticated": app.state.gmail_client is not None,
        "scheduler_running": app.state.scheduler.running,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------

@app.get("/auth/status")
def auth_status():
    authenticated = app.state.gmail_client is not None
    return {
        "authenticated": authenticated,
        "message": "Gmail client is ready." if authenticated else "Not authenticated. Use POST /auth/initiate.",
    }


@app.post("/auth/initiate")
def auth_initiate():
    flow = Flow.from_client_config(
        CLIENT_CONFIG,
        scopes=SCOPES,
        redirect_uri=OAUTH_REDIRECT_URI,
    )
    auth_url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )
    app.state.oauth_flow = flow
    app.state.oauth_state = state
    return {
        "auth_url": auth_url,
        "message": "Open auth_url in your browser to authorize the application.",
    }


@app.get("/auth/callback")
def auth_callback(request: Request):
    flow: Flow = getattr(app.state, "oauth_flow", None)
    if flow is None:
        raise HTTPException(status_code=400, detail="No pending OAuth flow. Call POST /auth/initiate first.")

    try:
        flow.fetch_token(authorization_response=str(request.url))
    except Exception as e:
        logger.error(f"OAuth token fetch failed: {e}")
        raise HTTPException(status_code=400, detail=f"OAuth token exchange failed: {e}")

    creds = flow.credentials
    save_credentials_to_file(creds, CREDENTIALS_FILE)
    app.state.gmail_client = GmailClient(client_credentials=creds)
    app.state.oauth_flow = None
    app.state.oauth_state = None

    logger.info("OAuth completed. Gmail client activated.")
    return {"success": True, "message": "Authentication successful. Gmail client is now active."}


# ---------------------------------------------------------------------------
# Scheduler endpoints
# ---------------------------------------------------------------------------

@app.get("/scheduler/status")
def scheduler_status():
    sm: SchedulerManager = app.state.scheduler_manager
    scheduler: BackgroundScheduler = app.state.scheduler

    job = scheduler.get_job("cleanup")
    next_run = job.next_run_time.isoformat() if job and job.next_run_time else None

    status = sm.get_status()
    status["next_run"] = next_run
    return status


@app.post("/scheduler/run-now", status_code=202)
def scheduler_run_now():
    if app.state.gmail_client is None:
        raise HTTPException(status_code=401, detail="Not authenticated. Use /auth/initiate first.")

    def _run():
        job = CleanupJob()
        job.run(app.state.gmail_client, app.state.scheduler_manager)

    app.state.scheduler.add_job(_run, id="cleanup_manual", replace_existing=True)
    return {
        "message": "Cleanup job triggered.",
        "run_at": datetime.now(timezone.utc).isoformat(),
    }


@app.put("/scheduler/config")
def scheduler_config(
    categories: list[str] | None = None,
    lookback_days: int | None = None,
    cron_hour: int | None = None,
    cron_minute: int | None = None,
):
    sm: SchedulerManager = app.state.scheduler_manager
    sm.update_config(
        categories=categories,
        lookback_days=lookback_days,
        cron_hour=cron_hour,
        cron_minute=cron_minute,
    )

    # Reschedule cron if time changed
    if cron_hour is not None or cron_minute is not None:
        app.state.scheduler.reschedule_job(
            "cleanup",
            trigger=CronTrigger(hour=sm.state.cron_hour, minute=sm.state.cron_minute),
        )

    return {"message": "Scheduler config updated.", "config": sm.get_status()["config"]}
