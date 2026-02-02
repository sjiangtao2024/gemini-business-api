# Cookie Refresher Service Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a standalone cookie refresher service that logs into Gemini Business with 2925 email verification, extracts cookies/session data, and updates `gemini-business-api` via `/admin/accounts`.

**Architecture:** A separate Python service with a scheduler and a login orchestrator. The orchestrator runs Selenium + undetected-chromedriver (headed) as the primary engine and DrissionPage as fallback. A 2925 IMAP handler fetches verification codes. A policy module computes `expires_at` using cookie expiry minus 12 hours and triggers refresh before expiry or on 401/403 signals. Updates are pushed to `/admin/accounts` (delete + add if needed).

**Tech Stack:** Python 3.11, httpx, selenium + undetected-chromedriver, DrissionPage, imaplib, pytest.

### Task 1: Create the cookie refresher service scaffold

**Files:**
- Create: `tools/cookie-refresher/README.md`
- Create: `tools/cookie-refresher/pyproject.toml`
- Create: `tools/cookie-refresher/.env.example`
- Create: `tools/cookie-refresher/cookie_refresher/__init__.py`
- Create: `tools/cookie-refresher/cookie_refresher/config.py`
- Test: `tools/cookie-refresher/tests/test_config.py`

**Step 1: Write the failing test**

```python
from cookie_refresher.config import Settings

def test_settings_defaults():
    settings = Settings()
    assert settings.admin_base_url == "http://localhost:8000"
```

**Step 2: Run test to verify it fails**

Run: `pytest tools/cookie-refresher/tests/test_config.py -v`
Expected: FAIL with "ModuleNotFoundError" or missing Settings.

**Step 3: Write minimal implementation**

```python
# tools/cookie-refresher/cookie_refresher/config.py
from dataclasses import dataclass
import os

@dataclass
class Settings:
    admin_base_url: str = os.getenv("ADMIN_BASE_URL", "http://localhost:8000")
    admin_api_key: str = os.getenv("ADMIN_API_KEY", "")
    imap_host: str = os.getenv("IMAP_HOST", "imap.2925.com")
    imap_port: int = int(os.getenv("IMAP_PORT", "993"))
```

**Step 4: Run test to verify it passes**

Run: `pytest tools/cookie-refresher/tests/test_config.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tools/cookie-refresher/README.md tools/cookie-refresher/pyproject.toml tools/cookie-refresher/.env.example tools/cookie-refresher/cookie_refresher/__init__.py tools/cookie-refresher/cookie_refresher/config.py tools/cookie-refresher/tests/test_config.py
git commit -m "feat: scaffold cookie refresher service"
```

### Task 2: Implement refresh policy (expires_at and refresh decisions)

**Files:**
- Create: `tools/cookie-refresher/cookie_refresher/policy.py`
- Test: `tools/cookie-refresher/tests/test_policy.py`

**Step 1: Write the failing test**

```python
from datetime import datetime, timezone
from cookie_refresher.policy import compute_expires_at, should_refresh

def test_expires_at_is_cookie_expiry_minus_12h():
    expiry = datetime(2026, 2, 2, 12, 0, tzinfo=timezone.utc)
    expires_at = compute_expires_at(expiry)
    assert expires_at == datetime(2026, 2, 2, 0, 0, tzinfo=timezone.utc)

def test_should_refresh_when_expired():
    now = datetime(2026, 2, 2, 12, 0, tzinfo=timezone.utc)
    assert should_refresh(now, now) is True
```

**Step 2: Run test to verify it fails**

Run: `pytest tools/cookie-refresher/tests/test_policy.py -v`
Expected: FAIL with missing functions.

**Step 3: Write minimal implementation**

```python
# tools/cookie-refresher/cookie_refresher/policy.py
from datetime import datetime, timedelta, timezone
from typing import Optional

def compute_expires_at(cookie_expiry: Optional[datetime]) -> datetime:
    if cookie_expiry is None:
        return datetime.now(timezone.utc) + timedelta(hours=12)
    return cookie_expiry - timedelta(hours=12)

def should_refresh(now: datetime, expires_at: datetime, forced: bool = False) -> bool:
    return forced or now >= expires_at
```

**Step 4: Run test to verify it passes**

Run: `pytest tools/cookie-refresher/tests/test_policy.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tools/cookie-refresher/cookie_refresher/policy.py tools/cookie-refresher/tests/test_policy.py
git commit -m "feat: add cookie refresh policy"
```

### Task 3: Add 2925 IMAP verification code parser

**Files:**
- Create: `tools/cookie-refresher/cookie_refresher/mail_2925.py`
- Test: `tools/cookie-refresher/tests/test_mail_2925.py`

**Step 1: Write the failing test**

```python
from cookie_refresher.mail_2925 import extract_verification_code

def test_extract_verification_code():
    body = "Your verification code is 123456."
    assert extract_verification_code(body) == "123456"
```

**Step 2: Run test to verify it fails**

Run: `pytest tools/cookie-refresher/tests/test_mail_2925.py -v`
Expected: FAIL with missing function.

**Step 3: Write minimal implementation**

```python
# tools/cookie-refresher/cookie_refresher/mail_2925.py
import re

CODE_PATTERNS = [
    r"verification code is[:\\s]+([A-Z0-9]{6})",
    r"验证码[：:\\s]+([A-Z0-9]{6})",
    r"([A-Z0-9]{6})\\s+is your verification code",
]

def extract_verification_code(body: str) -> str:
    for pattern in CODE_PATTERNS:
        match = re.search(pattern, body, re.IGNORECASE)
        if match:
            return match.group(1)
    raise ValueError("verification code not found")
```

**Step 4: Run test to verify it passes**

Run: `pytest tools/cookie-refresher/tests/test_mail_2925.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tools/cookie-refresher/cookie_refresher/mail_2925.py tools/cookie-refresher/tests/test_mail_2925.py
git commit -m "feat: add 2925 mail code parser"
```

### Task 4: Implement browser engine interface and Selenium (uc) engine

**Files:**
- Create: `tools/cookie-refresher/cookie_refresher/engines/base.py`
- Create: `tools/cookie-refresher/cookie_refresher/engines/selenium_uc.py`
- Test: `tools/cookie-refresher/tests/test_extractors.py`

**Step 1: Write the failing test**

```python
from cookie_refresher.engines.base import extract_session_info

def test_extract_session_info_from_url_and_cookies():
    url = "https://business.gemini.google/cid/abc123?csesidx=999"
    cookies = {
        "__Secure-C_SES": {"value": "ses"},
        "__Host-C_OSES": {"value": "oses"},
    }
    info = extract_session_info(url, cookies)
    assert info["team_id"] == "abc123"
    assert info["csesidx"] == "999"
```

**Step 2: Run test to verify it fails**

Run: `pytest tools/cookie-refresher/tests/test_extractors.py -v`
Expected: FAIL with missing function.

**Step 3: Write minimal implementation**

```python
# tools/cookie-refresher/cookie_refresher/engines/base.py
from typing import Dict, Any
from urllib.parse import urlparse, parse_qs

def extract_session_info(url: str, cookies: Dict[str, Dict[str, Any]]) -> Dict[str, str]:
    parsed = urlparse(url)
    parts = url.split("/cid/")
    team_id = parts[1].split("?")[0].split("/")[0] if len(parts) > 1 else ""
    csesidx = parse_qs(parsed.query).get("csesidx", [""])[0]
    return {
        "team_id": team_id,
        "csesidx": csesidx,
        "secure_c_ses": cookies.get("__Secure-C_SES", {}).get("value", ""),
        "host_c_oses": cookies.get("__Host-C_OSES", {}).get("value", ""),
    }
```

**Step 4: Run test to verify it passes**

Run: `pytest tools/cookie-refresher/tests/test_extractors.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tools/cookie-refresher/cookie_refresher/engines/base.py tools/cookie-refresher/tests/test_extractors.py
git commit -m "feat: add session extraction helpers"
```

### Task 5: Add orchestrator with fallback (Selenium -> DrissionPage)

**Files:**
- Create: `tools/cookie-refresher/cookie_refresher/orchestrator.py`
- Test: `tools/cookie-refresher/tests/test_orchestrator.py`

**Step 1: Write the failing test**

```python
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
```

**Step 2: Run test to verify it fails**

Run: `pytest tools/cookie-refresher/tests/test_orchestrator.py -v`
Expected: FAIL with missing function.

**Step 3: Write minimal implementation**

```python
# tools/cookie-refresher/cookie_refresher/orchestrator.py
def run_with_fallback(primary, fallback, email: str):
    try:
        return primary.login_and_extract(email)
    except Exception:
        return fallback.login_and_extract(email)
```

**Step 4: Run test to verify it passes**

Run: `pytest tools/cookie-refresher/tests/test_orchestrator.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tools/cookie-refresher/cookie_refresher/orchestrator.py tools/cookie-refresher/tests/test_orchestrator.py
git commit -m "feat: add login orchestrator with fallback"
```

### Task 6: Implement admin API client (delete + add)

**Files:**
- Create: `tools/cookie-refresher/cookie_refresher/admin_client.py`
- Test: `tools/cookie-refresher/tests/test_admin_client.py`

**Step 1: Write the failing test**

```python
import httpx
from cookie_refresher.admin_client import AdminClient

def test_add_account_delete_then_add_on_400(monkeypatch):
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path))
        if request.method == "POST":
            return httpx.Response(400, json={"detail": "exists"})
        if request.method == "DELETE":
            return httpx.Response(200, json={"message": "deleted"})
        return httpx.Response(200, json={"message": "added"})

    transport = httpx.MockTransport(handler)
    client = AdminClient("http://localhost:8000", transport=transport)
    client.upsert_account({"email": "a@b.com"})
    assert calls[0] == ("POST", "/admin/accounts")
    assert calls[1] == ("DELETE", "/admin/accounts/a@b.com")
```

**Step 2: Run test to verify it fails**

Run: `pytest tools/cookie-refresher/tests/test_admin_client.py -v`
Expected: FAIL with missing client.

**Step 3: Write minimal implementation**

```python
# tools/cookie-refresher/cookie_refresher/admin_client.py
import httpx
from typing import Optional, Dict, Any

class AdminClient:
    def __init__(self, base_url: str, api_key: str = "", transport: Optional[httpx.BaseTransport] = None):
        self.base_url = base_url.rstrip("/")
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self.client = httpx.Client(base_url=self.base_url, headers=headers, transport=transport)

    def upsert_account(self, payload: Dict[str, Any]) -> None:
        resp = self.client.post("/admin/accounts", json=payload)
        if resp.status_code == 400 and "exists" in resp.text:
            email = payload["email"]
            self.client.delete(f"/admin/accounts/{email}")
            self.client.post("/admin/accounts", json=payload)
        resp.raise_for_status()
```

**Step 4: Run test to verify it passes**

Run: `pytest tools/cookie-refresher/tests/test_admin_client.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tools/cookie-refresher/cookie_refresher/admin_client.py tools/cookie-refresher/tests/test_admin_client.py
git commit -m "feat: add admin API client with upsert"
```

### Task 7: Add scheduler + CLI entrypoint

**Files:**
- Create: `tools/cookie-refresher/cookie_refresher/cli.py`
- Create: `tools/cookie-refresher/cookie_refresher/scheduler.py`
- Test: `tools/cookie-refresher/tests/test_scheduler.py`

**Step 1: Write the failing test**

```python
from datetime import datetime, timezone, timedelta
from cookie_refresher.scheduler import select_due_accounts

def test_select_due_accounts():
    now = datetime(2026, 2, 2, 12, 0, tzinfo=timezone.utc)
    accounts = [
        {"email": "a", "expires_at": (now - timedelta(hours=1)).isoformat()},
        {"email": "b", "expires_at": (now + timedelta(days=2)).isoformat()},
    ]
    due = select_due_accounts(accounts, now)
    assert [a["email"] for a in due] == ["a"]
```

**Step 2: Run test to verify it fails**

Run: `pytest tools/cookie-refresher/tests/test_scheduler.py -v`
Expected: FAIL with missing function.

**Step 3: Write minimal implementation**

```python
# tools/cookie-refresher/cookie_refresher/scheduler.py
from datetime import datetime
from typing import List, Dict, Any

def select_due_accounts(accounts: List[Dict[str, Any]], now: datetime) -> List[Dict[str, Any]]:
    due = []
    for acc in accounts:
        expires_at = acc.get("expires_at")
        if not expires_at:
            continue
        if now >= datetime.fromisoformat(expires_at.replace("Z", "+00:00")):
            due.append(acc)
    return due
```

**Step 4: Run test to verify it passes**

Run: `pytest tools/cookie-refresher/tests/test_scheduler.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tools/cookie-refresher/cookie_refresher/scheduler.py tools/cookie-refresher/tests/test_scheduler.py tools/cookie-refresher/cookie_refresher/cli.py
git commit -m "feat: add scheduler and cli"
```

### Task 8: Document deployment and env vars

**Files:**
- Modify: `tools/cookie-refresher/README.md`
- Create: `tools/cookie-refresher/Dockerfile`
- Create: `tools/cookie-refresher/docker-compose.yml`

**Step 1: Write the failing doc test (optional)**

Skip automated tests; validate by manual review.

**Step 2: Write minimal documentation**

Include:
- Required env vars: `ADMIN_BASE_URL`, `ADMIN_API_KEY`, `IMAP_HOST`, `IMAP_PORT`, `IMAP_USER`, `IMAP_PASS`, `GEMINI_LOGIN_EMAIL`
- Run modes: `--once`, `--schedule`
- Note: 401/403 triggers manual refresh or scheduler run

**Step 3: Commit**

```bash
git add tools/cookie-refresher/README.md tools/cookie-refresher/Dockerfile tools/cookie-refresher/docker-compose.yml
git commit -m "docs: add cookie refresher deployment instructions"
```
