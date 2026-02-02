import pytest
from cookie_refresher.engines.selenium_uc import SeleniumUCEngine
from cookie_refresher.engines.drission import DrissionEngine


def test_selenium_engine_detects_verify_oob():
    class FakeDriver:
        current_url = "https://accountverification.business.gemini.google/v1/verify-oob-code"

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
    with pytest.raises(RuntimeError, match="verification failed"):
        engine.login_and_extract("user@example.com")


def test_drission_engine_detects_verify_oob():
    class FakePage:
        url = "https://accountverification.business.gemini.google/v1/verify-oob-code"

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
    with pytest.raises(RuntimeError, match="verification failed"):
        engine.login_and_extract("user@example.com")
