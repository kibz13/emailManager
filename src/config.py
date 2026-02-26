import os
from dotenv import load_dotenv

load_dotenv()

CLIENT_CONFIG = {
    "installed": {
        "client_id": os.getenv("GMAIL_CLIENT_ID", ""),
        "client_secret": os.getenv("GMAIL_CLIENT_SECRET", ""),
        "project_id": os.getenv("GMAIL_PROJECT_ID", ""),
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "redirect_uris": [os.getenv("OAUTH_REDIRECT_URI", "http://localhost:8000/auth/callback")],
    }
}

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]

CREDENTIALS_FILE = os.getenv("CREDENTIALS_FILE", "user_credentials.json")
SCHEDULER_STATE_FILE = os.getenv("SCHEDULER_STATE_FILE", "scheduler_state.json")
CLEANUP_CATEGORIES = os.getenv("CLEANUP_CATEGORIES", "promotions,social").split(",")
CLEANUP_LOOKBACK_DAYS = int(os.getenv("CLEANUP_LOOKBACK_DAYS", "30"))
CLEANUP_CRON_HOUR = int(os.getenv("CLEANUP_CRON_HOUR", "2"))
CLEANUP_CRON_MINUTE = int(os.getenv("CLEANUP_CRON_MINUTE", "0"))
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")
