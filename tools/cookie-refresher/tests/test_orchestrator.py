from cookie_refresher.orchestrator import run_with_fallback


class Primary:
    def login_and_extract(self, *_):
        raise RuntimeError("fail")


class Fallback:
    def login_and_extract(self, *_):
        return {"team_id": "t", "csesidx": "1", "secure_c_ses": "s", "host_c_oses": "h"}


def test_fallback_on_failure():
    result = run_with_fallback(Primary(), Fallback(), "email")
    assert result["csesidx"] == "1"
