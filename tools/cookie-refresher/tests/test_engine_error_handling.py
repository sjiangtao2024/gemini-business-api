import pytest
from cookie_refresher.engines.selenium_uc import SeleniumUCEngine
from cookie_refresher.engines.drission import DrissionEngine


def test_selenium_engine_raises_on_timeout():
    class FakeDriver:
        def get(self, _):
            pass

        def find_element(self, *_):
            raise Exception("timeout")

        def quit(self):
            pass

    engine = SeleniumUCEngine(lambda: "123456", driver_factory=lambda: FakeDriver())
    with pytest.raises(RuntimeError, match="login timeout"):
        engine.login_and_extract("user@example.com")


def test_drission_engine_raises_on_timeout():
    class FakePage:
        def get(self, _):
            pass

        def ele(self, *_):
            raise Exception("timeout")

        def close(self):
            pass

    engine = DrissionEngine(lambda: "123456", page_factory=lambda: FakePage())
    with pytest.raises(RuntimeError, match="login timeout"):
        engine.login_and_extract("user@example.com")
