from cookie_refresher.engines.selenium_uc import SeleniumUCEngine


def test_selenium_login_uses_xsrf_flow():
    calls = []

    class FakeDriver:
        current_url = "https://auth.business.gemini.google/login"

        def get(self, url):
            calls.append(("get", url))

        def add_cookie(self, cookie):
            calls.append(("cookie", cookie["name"]))

        def find_element(self, *_):
            class Fake:
                def send_keys(self, _):
                    pass
            return Fake()

        def get_cookies(self):
            return []

        def execute_script(self, _):
            return "UA"

        def quit(self):
            pass

    engine = SeleniumUCEngine(
        lambda: "123456",
        driver_factory=lambda: FakeDriver(),
        xsrf_token="xsrf",
        grecaptcha_token="gcap",
    )
    engine.login_and_extract("user@example.com")

    assert calls[0] == ("get", "https://auth.business.gemini.google/")
    assert ("cookie", "__Host-AP_SignInXsrf") in calls
    assert ("cookie", "_GRECAPTCHA") in calls
    assert any("login/email" in call[1] for call in calls if call[0] == "get")
