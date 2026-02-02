from datetime import datetime, timezone
from typing import Callable

from cookie_refresher.scheduler import select_due_accounts
from cookie_refresher.refresh import refresh_account


def refresh_due_accounts(admin_client, engine, now_fn: Callable[[], datetime] | None = None) -> int:
    now_fn = now_fn or (lambda: datetime.now(timezone.utc))
    accounts = admin_client.list_accounts()
    due_accounts = select_due_accounts(accounts, now_fn())
    for account in due_accounts:
        refresh_account(account["email"], engine, admin_client, now_fn=now_fn)
    return len(due_accounts)
