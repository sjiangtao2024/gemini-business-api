from typing import Dict, Any, Callable, Optional

from cookie_refresher.engines.base import build_account_payload


class SeleniumUCEngine:
    """Login engine using undetected-chromedriver (headed)."""

    def __init__(
        self,
        code_provider: Callable[[], str],
        driver_factory: Optional[Callable[[], Any]] = None,
        login_url: str = "https://auth.business.gemini.google/login",
    ):
        self.code_provider = code_provider
        self.driver_factory = driver_factory or self._default_driver_factory
        self.login_url = login_url

    def _default_driver_factory(self):
        import undetected_chromedriver as uc

        options = uc.ChromeOptions()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1280,800")
        return uc.Chrome(options=options)

    def login_and_extract(self, email: str) -> Dict[str, Any]:
        driver = self.driver_factory()
        try:
            self._login(driver, email)
            cookies = driver.get_cookies()
            user_agent = driver.execute_script("return navigator.userAgent")
            return build_account_payload(driver.current_url, cookies, user_agent)
        finally:
            try:
                driver.quit()
            except Exception:
                pass

    def _login(self, driver, email: str) -> None:
        driver.get(self.login_url)
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.common.keys import Keys
        except Exception:
            By = None
            Keys = None

        if By and Keys:
            email_input = driver.find_element(By.CSS_SELECTOR, 'input[type="email"]')
            email_input.send_keys(email)
            email_input.send_keys(Keys.ENTER)
            code = self.code_provider()
            code_input = driver.find_element(By.CSS_SELECTOR, 'input[name="code"]')
            code_input.send_keys(code)
            code_input.send_keys(Keys.ENTER)
        else:
            email_input = driver.find_element(None, None)
            email_input.send_keys(email)
            code = self.code_provider()
            code_input = driver.find_element(None, None)
            code_input.send_keys(code)
