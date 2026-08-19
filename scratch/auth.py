import os.path
import os
import json
import base64
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# If modifying these scopes, delete the file token.json.
SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/gmail.compose"
]

def get_credentials():
    creds = None
    
    # 1. Check for token in environment variable
    token_b64 = os.environ.get("GOOGLE_TOKEN_B64")
    if token_b64:
        token_info = json.loads(base64.b64decode(token_b64).decode('utf-8'))
        creds = Credentials.from_authorized_user_info(token_info, SCOPES)
    # 2. Check for token in file
    elif os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        refreshed = False
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                refreshed = True
            except Exception as e:
                print(f"Failed to refresh token: {e}. Re-authenticating...")

        if not refreshed:
            # 3. Check for client secrets in environment variable
            creds_b64 = os.environ.get("GOOGLE_CREDENTIALS_B64")
            if creds_b64:
                client_config = json.loads(base64.b64decode(creds_b64).decode('utf-8'))
                flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
            else:
                if not os.path.exists("credentials.json"):
                    raise FileNotFoundError("credentials.json not found, and GOOGLE_CREDENTIALS_B64 is not set.")
                flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            
            if os.environ.get("ENVIRONMENT", "development").lower() == "production":
                raise RuntimeError(
                    "Credentials expired/invalid. Running in production environment, "
                    "cannot run local server for browser authentication. "
                    "Please run locally first and update GOOGLE_TOKEN_B64."
                )

            creds = flow.run_local_server(port=0)
            
        # Save the credentials for the next run (only if not loaded from env)
        if not token_b64:
            with open("token.json", "w") as token:
                token.write(creds.to_json())
    return creds
