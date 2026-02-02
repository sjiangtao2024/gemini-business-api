from datetime import datetime, timezone
from typing import Callable


def refresh_account(email: str, engine, admin_client, now_fn: Callable[[], datetime] | None = None) -> None:
    now_fn = now_fn or (lambda: datetime.now(timezone.utc))
    payload = engine.login_and_extract(email)
    payload.update({
        "email": email,
        "created_at": now_fn().isoformat(),
    })
    admin_client.upsert_account(payload)
