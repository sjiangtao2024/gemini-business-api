from cookie_refresher.orchestrator import run_with_fallback
from cookie_refresher.service import refresh_due_accounts


def test_orchestrated_refresh_uses_fallback():
    class Primary:
        def login_and_extract(self, *_):
            raise RuntimeError("fail")

    class Fallback:
        def login_and_extract(self, *_):
            return {
                "team_id": "t",
                "csesidx": "1",
                "secure_c_ses": "s",
                "host_c_oses": "h",
                "user_agent": "UA",
                "expires_at": "2025-02-01T12:00:00+00:00",
            }

    class FakeAdmin:
        def __init__(self):
            self.payloads = []

        def list_accounts(self):
            return [{"email": "a", "expires_at": "2000-01-01T00:00:00+00:00"}]

        def upsert_account(self, payload):
            self.payloads.append(payload)

    admin = FakeAdmin()
    engine = type("Engine", (), {"login_and_extract": lambda _, email: run_with_fallback(Primary(), Fallback(), email)})()

    refresh_due_accounts(admin, engine)
    assert admin.payloads[0]["email"] == "a"
