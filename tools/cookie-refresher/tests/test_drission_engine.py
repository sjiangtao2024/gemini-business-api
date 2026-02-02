from cookie_refresher.engines.drission import DrissionEngine


def test_drission_engine_login_and_extract():
    events = []

    class FakePage:
        url = "https://business.gemini.google/cid/team123?csesidx=777"

        def get(self, url):
            events.append(("get", url))

        def get_cookies(self):
            return [
                {"name": "__Secure-C_SES", "value": "ses", "expiry": 1738492800},
                {"name": "__Host-C_OSES", "value": "oses"},
            ]

        def run_js(self, _):
            return "UA"

        def close(self):
            events.append(("close",))

        def ele(self, *_):
            class FakeEl:
                def input(self, value):
                    events.append(("input", value))
            return FakeEl()

    def code_provider():
        events.append(("code_provider",))
        return "123456"

    engine = DrissionEngine(code_provider, page_factory=lambda: FakePage())
    payload = engine.login_and_extract("user@example.com")
    assert payload["team_id"] == "team123"
    assert ("code_provider",) in events
