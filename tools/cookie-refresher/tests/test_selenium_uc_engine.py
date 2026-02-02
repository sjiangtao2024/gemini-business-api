from cookie_refresher.engines.selenium_uc import SeleniumUCEngine


def test_login_and_extract_uses_code_provider():
    events = []

    class FakeElement:
        def __init__(self, name):
            self.name = name

        def send_keys(self, value):
            events.append((self.name, "send_keys", value))

    class FakeDriver:
        def __init__(self):
            self.current_url = "https://business.gemini.google/cid/team123?csesidx=777"

        def get(self, url):
            events.append(("get", url))

        def find_element(self, *_):
            if not any(e[0] == "email" for e in events):
                return FakeElement("email")
            return FakeElement("code")

        def get_cookies(self):
            return [
                {"name": "__Secure-C_SES", "value": "ses", "expiry": 1738492800},
                {"name": "__Host-C_OSES", "value": "oses"},
            ]

        def execute_script(self, _):
            return "UA"

        def quit(self):
            events.append(("quit",))

    def code_provider():
        events.append(("code_provider",))
        return "123456"

    engine = SeleniumUCEngine(code_provider, driver_factory=lambda: FakeDriver())
    payload = engine.login_and_extract("user@example.com")

    assert payload["team_id"] == "team123"
    assert payload["csesidx"] == "777"
    assert ("code_provider",) in events
