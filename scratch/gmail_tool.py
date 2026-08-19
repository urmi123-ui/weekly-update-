import base64
from email.message import EmailMessage
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

def create_email_draft(creds, to: str, subject: str, body: str):
    try:
        service = build("gmail", "v1", credentials=creds)

        message = EmailMessage()
        message.set_content(body)
        message["To"] = to
        message["Subject"] = subject

        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        create_message = {"message": {"raw": encoded_message}}
        
        draft = service.users().drafts().create(
            userId="me", body=create_message
        ).execute()

        return {"status": "success", "draft_id": draft["id"]}
    except HttpError as err:
        return {"status": "error", "error": str(err)}
