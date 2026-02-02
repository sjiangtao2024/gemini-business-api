from dataclasses import dataclass
import os


@dataclass
class Settings:
    admin_base_url: str = os.getenv("ADMIN_BASE_URL", "http://localhost:8000")
    admin_api_key: str = os.getenv("ADMIN_API_KEY", "")
    imap_host: str = os.getenv("IMAP_HOST", "imap.2925.com")
    imap_port: int = int(os.getenv("IMAP_PORT", "993"))
