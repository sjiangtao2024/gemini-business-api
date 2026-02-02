import re
import imaplib
import email

CODE_PATTERNS = [
    r"verification code is[:\s]+([A-Z0-9]{6})",
    r"验证码[：:\s]+([A-Z0-9]{6})",
    r"([A-Z0-9]{6})\s+is your verification code",
]


def extract_verification_code(body: str) -> str:
    for pattern in CODE_PATTERNS:
        match = re.search(pattern, body, re.IGNORECASE)
        if match:
            return match.group(1)
    raise ValueError("verification code not found")


def _get_email_body(message: email.message.Message) -> str:
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                return payload.decode(errors="ignore") if payload else ""
        return ""
    payload = message.get_payload(decode=True)
    return payload.decode(errors="ignore") if payload else ""


class Mail2925Handler:
    def __init__(self, host: str, port: int, user: str, password: str):
        self.host = host
        self.port = port
        self.user = user
        self.password = password

    def get_verification_code(self, criteria: str = "UNSEEN") -> str:
        client = imaplib.IMAP4_SSL(self.host, self.port)
        try:
            client.login(self.user, self.password)
            client.select("INBOX")
            _, messages = client.search(None, criteria)
            email_ids = messages[0].split() if messages and messages[0] else []
            for email_id in reversed(email_ids):
                _, msg_data = client.fetch(email_id, "(RFC822)")
                if not msg_data:
                    continue
                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)
                body = _get_email_body(msg)
                try:
                    return extract_verification_code(body)
                except ValueError:
                    continue
        finally:
            try:
                client.close()
            finally:
                client.logout()
        raise ValueError("verification code not found")
