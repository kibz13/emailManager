import json
from src.models.ouath_credentials import OAuthCredentials
from pathlib import Path
from fastapi import HTTPException
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Auth:
    def __init__(self, flow):
        self.flow_server = flow

    def get_client_credentials(self):
        try:
            response = self.flow_server.run_local_server()
            logger.info("Successfully retrieved client credentials")
            creds = OAuthCredentials(
                token=response.token,
                refresh_token=response.refresh_token,
                token_uri=response.token_uri,
                client_id=response.client_id,
                client_secret=response.client_secret,
                scopes=response.scopes
            )
            return creds
        except Exception as e:
            logger.error(f"Error retrieving credentials: {str(e)}")
            raise

    @staticmethod
    def write_credentials_to_json(credentials, file_path='user_credentials.json'):
        try:
            file_path = Path(file_path)
            with open(file_path, 'w') as json_file:
                json.dump(credentials.to_dict(), json_file, indent=4)
            logger.info("Credentials successfully written to %s", file_path)
        except IOError as e:
            logger.error("Error writing to file %s: %s", file_path, e)
            raise
        except Exception as e:
            logger.error("Error serializing credentials: %s", e)
            raise

# Use the credentials to make API requests
# For example, using the Gmail API with the obtained credentials
