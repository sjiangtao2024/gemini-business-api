from typing import Dict, Any


class SeleniumUCEngine:
    """Login engine using undetected-chromedriver (headed)."""

    def login_and_extract(self, email: str) -> Dict[str, Any]:
        raise NotImplementedError("Selenium U-C engine not implemented yet")
