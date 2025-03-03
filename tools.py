import base64
import logging
import os
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, TypedDict

import markdownify
from dateutil import parser
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# --- Schemas ---
class EmailData(TypedDict):
    id: str
    thread_id: str
    from_email: str
    subject: str
    page_content: str
    send_time: str
    to_email: str
    is_read: bool
    attachments: List[Dict]

class EmailType(Enum):
    ALL = "all"
    READ = "read"
    UNREAD = "unread"

# --- Constants ---
_SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
_SECRETS_DIR = Path(".secrets")
_SECRETS_PATH = str(_SECRETS_DIR / "secrets.json")
_TOKEN_PATH = str(_SECRETS_DIR / "token.json")
_PORT = 54191
_ATTACHMENTS_DIR = Path(".attachments")
_ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)

# --- Gmail Client ---
class GmailClient:
    def __init__(
        self,
        gmail_token: Optional[str] = None,
        gmail_secret: Optional[str] = None,
        attachments_dir: Path = _ATTACHMENTS_DIR,
    ):
        """Initialize the Gmail client."""
        self.logger = logging.getLogger(__name__)
        logging.basicConfig(level=logging.INFO)
        self.creds = self._get_credentials(gmail_token, gmail_secret)
        self.gmail_service = build("gmail", "v1", credentials=self.creds)
        self.attachments_dir = attachments_dir
        self.attachments_dir.mkdir(parents=True, exist_ok=True)

    # --- Authentication ---
    def _get_credentials(self, gmail_token: Optional[str], gmail_secret: Optional[str]) -> Credentials:
        creds = None
        _SECRETS_DIR.mkdir(parents=True, exist_ok=True)
        gmail_token = gmail_token or os.getenv("GMAIL_TOKEN")
        if gmail_token:
            with open(_TOKEN_PATH, "w") as token:
                token.write(gmail_token)
        gmail_secret = gmail_secret or os.getenv("GMAIL_SECRET")
        if gmail_secret:
            with open(_SECRETS_PATH, "w") as secret:
                secret.write(gmail_secret)
        if os.path.exists(_TOKEN_PATH):
            creds = Credentials.from_authorized_user_file(_TOKEN_PATH)

        if not creds or not creds.valid or not creds.has_scopes(_SCOPES):
            if creds and creds.expired and creds.refresh_token and creds.has_scopes(_SCOPES):
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(_SECRETS_PATH, _SCOPES)
                creds = flow.run_local_server(port=_PORT)
            with open(_TOKEN_PATH, "w") as token:
                token.write(creds.to_json())
        return creds

    def _download_attachment(self, user_id: str, msg_id: str, attachment: Dict) -> Optional[bytes]:
        try:
            attachment_data = (
                self.gmail_service.users()
                .messages()
                .attachments()
                .get(userId=user_id, messageId=msg_id, id=attachment["id"])
                .execute()
            )
            file_data = base64.urlsafe_b64decode(attachment_data["data"].encode("UTF-8"))
            return file_data
        except HttpError as error:
            self.logger.error(f"An error occurred downloading attachment: {error}")
            return None

    # --- Email Parsing ---
    def _extract_message_part(self, msg: Dict) -> Optional[str]:
        if msg["mimeType"] == "text/plain":
            body_data = msg.get("body", {}).get("data")
            if body_data:
                return base64.urlsafe_b64decode(body_data).decode("utf-8")
        elif msg["mimeType"] == "text/html":
            body_data = msg.get("body", {}).get("data")
            if body_data:
                html_content = base64.urlsafe_b64decode(body_data).decode("utf-8")
                return markdownify.markdownify(html_content, heading_style="ATX")
        if "parts" in msg:
            for part in msg["parts"]:
                body = self._extract_message_part(part)
                if body:
                    return body
        return None

    def _parse_time(self, send_time: str) -> datetime:
        try:
            return parser.parse(send_time)
        except (ValueError, TypeError) as e:
            raise ValueError(f"Error parsing time: {send_time} - {e}")

    # --- Email Fetching ---
    def fetch_emails(
        self,
        email_address: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        email_type: EmailType = EmailType.ALL,
        query: Optional[str] = None,
        download_attachments: bool = True,
    ) -> List[EmailData]:
        today = date.today()
        start_time = start_time or datetime.combine(today, datetime.min.time())
        end_time = end_time or datetime.combine(today, datetime.max.time())

        time_query = f"after:{int(start_time.timestamp())} before:{int(end_time.timestamp())}"
        base_query = f"(to:{email_address} OR from:{email_address}) {time_query}"
        full_query = f"{base_query} {query}" if query else base_query

        messages = []
        next_page_token = None
        while True:
            results = (
                self.gmail_service.users()
                .messages()
                .list(userId="me", q=full_query, pageToken=next_page_token)
                .execute()
            )
            if "messages" in results:
                messages.extend(results["messages"])
            next_page_token = results.get("nextPageToken")
            if not next_page_token:
                break

        threads: Dict[str, EmailData] = {}
        for message in messages:
            try:
                msg = self.gmail_service.users().messages().get(userId="me", id=message["id"]).execute()
                thread_id = msg["threadId"]
                payload = msg["payload"]
                headers = payload.get("headers", [])

                subject = next((h["value"] for h in headers if h["name"] == "Subject"), "")
                from_email = next((h["value"] for h in headers if h["name"] == "From"), "").strip()
                to_email = next((h["value"] for h in headers if h["name"] == "To"), "").strip()
                if reply_to := next((h["value"] for h in headers if h["name"] == "Reply-To"), "").strip():
                    from_email = reply_to
                send_time = next((h["value"] for h in headers if h["name"] == "Date"), "")
                parsed_time = self._parse_time(send_time)
                body = self._extract_message_part(payload) or "No message body available."
                is_read = "UNREAD" not in msg.get("labelIds", [])
                attachments: List[Dict] = []

                if download_attachments and "parts" in payload:
                    for part in payload["parts"]:
                        if part.get("filename"):
                            attachment = {"filename": part["filename"], "id": part["body"]["attachmentId"]}
                            attachments.append(attachment)
                            file_data = self._download_attachment("me", msg["id"], attachment)
                            if file_data:
                                filepath = self.attachments_dir / f"{msg['id']}_{attachment['filename']}"
                                with open(filepath, "wb") as f:
                                    f.write(file_data)
                                self.logger.info(f"Downloaded attachment: {attachment['filename']} to {filepath}")

                if thread_id in threads:
                    existing_email = threads[thread_id]
                    existing_email["page_content"] += "\n\n--- New Message in Thread ---\n\n" + body
                    for attachment in attachments:
                        if attachment not in existing_email["attachments"]:
                            existing_email["attachments"].append(attachment)
                    existing_email["is_read"] = existing_email["is_read"] and is_read
                    if parsed_time > parser.parse(existing_email["send_time"]):
                        existing_email["send_time"] = parsed_time.isoformat()
                    existing_email["from_email"] = ", ".join(set(existing_email["from_email"].split(", ") + [from_email]))
                    existing_email["to_email"] = ", ".join(set(existing_email["to_email"].split(", ") + [to_email]))
                else:
                    threads[thread_id] = EmailData(
                        from_email=from_email,
                        to_email=to_email,
                        subject=subject,
                        page_content=body,
                        id=message["id"],
                        thread_id=thread_id,
                        send_time=parsed_time.isoformat(),
                        is_read=is_read,
                        attachments=attachments,
                    )
            except Exception as e:
                self.logger.error(f"Failed processing message {message}: {e}")

        result = [t for t in threads.values() if email_type == EmailType.ALL or
                  (email_type == EmailType.READ and t["is_read"]) or
                  (email_type == EmailType.UNREAD and not t["is_read"])]
        self.logger.info(f"Found {len(result)} threads matching criteria.")
        return result