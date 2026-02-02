from cookie_refresher.engines.drission import DrissionEngine


def test_drission_login_uses_xsrf_flow():
    calls = []

    class FakeSetter:
        def cookies(self, cookie):
            calls.append(("cookie", cookie["name"]))

    class FakePage:
        url = "https://auth.business.gemini.google/login"
        set = FakeSetter()

        def get(self, url):
            calls.append(("get", url))

        def ele(self, *_):
            class Fake:
                def input(self, _):
                    pass
            return Fake()

        def get_cookies(self):
            return []

        def run_js(self, _):
            return "UA"

        def close(self):
            pass

    engine = DrissionEngine(
        lambda: "123456",
        page_factory=lambda: FakePage(),
        xsrf_token="xsrf",
        grecaptcha_token="gcap",
    )
    engine.login_and_extract("user@example.com")

    assert calls[0] == ("get", "https://auth.business.gemini.google/")
    assert ("cookie", "__Host-AP_SignInXsrf") in calls
    assert ("cookie", "_GRECAPTCHA") in calls
    assert any("login/email" in call[1] for call in calls if call[0] == "get")
