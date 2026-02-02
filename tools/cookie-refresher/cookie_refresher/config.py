from dataclasses import dataclass
import os
from typing import Optional


@dataclass
class Settings:
    admin_base_url: Optional[str] = None
    admin_api_key: Optional[str] = None
    imap_host: Optional[str] = None
    imap_port: Optional[int] = None
    imap_user: Optional[str] = None
    imap_pass: Optional[str] = None
    login_email: Optional[str] = None

    def __post_init__(self) -> None:
        self.admin_base_url = self.admin_base_url or os.getenv("ADMIN_BASE_URL", "http://localhost:8000")
        self.admin_api_key = self.admin_api_key or os.getenv("ADMIN_API_KEY", "")
        self.imap_host = self.imap_host or os.getenv("IMAP_HOST", "imap.2925.com")
        self.imap_port = self.imap_port or int(os.getenv("IMAP_PORT", "993"))
        self.imap_user = self.imap_user or os.getenv("IMAP_USER", "")
        self.imap_pass = self.imap_pass or os.getenv("IMAP_PASS", "")
        self.login_email = self.login_email or os.getenv("GEMINI_LOGIN_EMAIL", "")
