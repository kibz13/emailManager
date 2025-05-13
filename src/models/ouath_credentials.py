from pydantic import BaseModel
from typing import List, Optional
import json
from google.oauth2.credentials import Credentials


class OAuthCredentials(BaseModel):
    token: str
    refresh_token: str
    token_uri: str
    client_id: str
    client_secret: str
    scopes: List[str]

    def __repr__(self):
        return (f"Credentials(token='{self.token}', "
                f"refresh_token='{self.refresh_token}', "
                f"token_uri='{self.token_uri}', "
                f"client_id='{self.client_id}', "
                f"scopes={self.scopes})")

    def to_dict(self):
        return {
            'token': self.token,
            'refresh_token': self.refresh_token,
            'token_uri': self.token_uri,
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'scopes': self.scopes
        }

    def to_json(self):
        return json.dumps(self.to_dict())

    def to_google_credentials(self):
        return Credentials.from_authorized_user_info(self.to_dict(), self.scopes)
