from datetime import datetime, timezone, timedelta
from cookie_refresher.service import refresh_due_accounts


def test_refresh_due_accounts_selects_expired_and_calls_admin():
    now = datetime(2026, 2, 2, 12, 0, tzinfo=timezone.utc)
    accounts = [
        {"email": "a", "expires_at": (now - timedelta(hours=1)).isoformat()},
        {"email": "b", "expires_at": (now + timedelta(days=1)).isoformat()},
    ]

    class FakeAdmin:
        def list_accounts(self):
            return accounts

        def upsert_account(self, payload):
            payloads.append(payload)

    class FakeEngine:
        def login_and_extract(self, email):
            return {
                "team_id": "t",
                "csesidx": "1",
                "secure_c_ses": "s",
                "host_c_oses": "h",
                "user_agent": "UA",
                "expires_at": "2025-02-01T12:00:00+00:00",
            }

    payloads = []
    refresh_due_accounts(FakeAdmin(), FakeEngine(), now_fn=lambda: now)

    assert len(payloads) == 1
    assert payloads[0]["email"] == "a"
