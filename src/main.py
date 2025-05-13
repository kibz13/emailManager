from fastapi import FastAPI, HTTPException
from google_auth_oauthlib.flow import InstalledAppFlow
from src.config import CLIENT_CONFIG, SCOPES
from src.api.auth import Auth
from src.api.gmail_client import GmailClient
from src.models.message import Message
from src.models.custom_cache import CustomCache
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

flow = InstalledAppFlow.from_client_config(client_config=CLIENT_CONFIG, scopes=SCOPES)
app = FastAPI()

oauth = Auth(flow)
gmail_client = None
cache = CustomCache()


@app.on_event("startup")
def startup_event():

    global gmail_client  # Use global if you need to access it elsewhere
    try:
        creds = oauth.get_client_credentials()
        gmail_client = GmailClient(client_credentials=creds.to_google_credentials())
    except HTTPException as e:
        logger.error(f"Failed to fetch client credentials. Status code: {e.status_code}, detail: {e.detail}")
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    except Exception as e:
        logger.error(f"Unknown error. Status code: 500, detail: {str(e)}")
        raise e


@app.get("/")
def get_root():
    return {"Application": "Begin"}


@app.get("/fetch_emails/{category}/{start}/{end}")
def fetch_emails(start, end, category="promotions"):
    try:
        raw_messages = gmail_client.fetch_user_emails(start_date=start , end_date=end, category=category)
        result = [Message(_id=message["id"], thread_id=message["threadId"]) for message in raw_messages]
        logger.info(f"Successfully fetched {len(result)} {category} emails.")
    except HTTPException as e:
        logger.error(f"Failed to fetch client credentials. Status code : {e.status_code} detail : {e.detail}")
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    except Exception as e:
        logger.error(f"Unknown error. Status code: 500, detail: {str(e)}")
        raise Exception(status_code=500)
    cache.insert(category, result)
    return result


@app.get("/cache_data")
def get_cache_data():
    return cache.get_cache_data()


@app.get("/delete_emails/{category}")
def delete_emails(category):
    try:
        deleted_count = gmail_client.delete_user_emails(cache, category)
    except HTTPException as e:
        logger.error(f"Failed to delete message. {e.status_code} detail : {e.detail}")
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    except Exception as e:
        logger.error(f"Unknown error. Status code: 500, detail: {str(e)}")
        raise Exception(status_code=500)

    return f"Successfully deleted {deleted_count} messages of category {category}"





