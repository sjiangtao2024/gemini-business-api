import pytest
from cookie_refresher.engines.selenium_uc import SeleniumUCEngine
from cookie_refresher.engines.drission import DrissionEngine


def test_selenium_engine_detects_challenge_page():
    class FakeDriver:
        current_url = "https://auth.business.gemini.google/challenge"

        def get(self, _):
            pass

        def find_element(self, *_):
            class Fake:
                def send_keys(self, _):
                    pass
            return Fake()

        def quit(self):
            pass

    engine = SeleniumUCEngine(lambda: "123456", driver_factory=lambda: FakeDriver())
    with pytest.raises(RuntimeError, match="challenge detected"):
        engine.login_and_extract("user@example.com")


def test_drission_engine_detects_challenge_page():
    class FakePage:
        url = "https://auth.business.gemini.google/challenge"

        def get(self, _):
            pass

        def ele(self, *_):
            class Fake:
                def input(self, _):
                    pass
            return Fake()

        def close(self):
            pass

    engine = DrissionEngine(lambda: "123456", page_factory=lambda: FakePage())
    with pytest.raises(RuntimeError, match="challenge detected"):
        engine.login_and_extract("user@example.com")
