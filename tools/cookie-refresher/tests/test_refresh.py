from datetime import datetime, timezone
from cookie_refresher.refresh import refresh_account


def test_refresh_account_calls_admin_client():
    called = {}

    class FakeEngine:
        def login_and_extract(self, _):
            return {
                "team_id": "t",
                "csesidx": "1",
                "secure_c_ses": "s",
                "host_c_oses": "h",
                "user_agent": "UA",
                "expires_at": "2025-02-01T12:00:00+00:00",
            }

    class FakeAdmin:
        def upsert_account(self, payload):
            called["payload"] = payload

    now = datetime(2026, 2, 2, 12, 0, tzinfo=timezone.utc)
    refresh_account(
        "user@example.com",
        FakeEngine(),
        FakeAdmin(),
        now_fn=lambda: now,
    )

    payload = called["payload"]
    assert payload["email"] == "user@example.com"
    assert payload["team_id"] == "t"
    assert payload["created_at"] == now.isoformat()
