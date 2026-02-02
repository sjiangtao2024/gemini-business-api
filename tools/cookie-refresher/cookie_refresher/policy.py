from datetime import datetime, timedelta, timezone
from typing import Optional


def compute_expires_at(cookie_expiry: Optional[datetime]) -> datetime:
    if cookie_expiry is None:
        return datetime.now(timezone.utc) + timedelta(hours=12)
    return cookie_expiry - timedelta(hours=12)


def should_refresh(now: datetime, expires_at: datetime, forced: bool = False) -> bool:
    return forced or now >= expires_at
