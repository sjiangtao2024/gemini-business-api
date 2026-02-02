from datetime import datetime, timezone, timedelta
from cookie_refresher.scheduler import select_due_accounts


def test_select_due_accounts():
    now = datetime(2026, 2, 2, 12, 0, tzinfo=timezone.utc)
    accounts = [
        {"email": "a", "expires_at": (now - timedelta(hours=1)).isoformat()},
        {"email": "b", "expires_at": (now + timedelta(days=2)).isoformat()},
    ]
    due = select_due_accounts(accounts, now)
    assert [a["email"] for a in due] == ["a"]
