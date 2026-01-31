# Findings: Gemini Business API Development

**Project**: Gemini Business API
**Last Updated**: 2025-01-31

---

## 🔍 Research Findings

### JWT Token Refresh Mechanism (CRITICAL)

**Date**: 2025-01-31
**Source**: Analysis of 4 GitHub repositories

**Key Discovery**: JWT is generated **locally**, NOT returned from Google's server.

**Verified Implementation** (from `gemini-business2api/core/jwt.py`):
```python
# Step 1: Request signing key from Google
GET https://business.gemini.google/auth/getoxsrf?csesidx={csesidx}
Headers: Cookie: __Secure-c-SES={secure_c_ses}

# Step 2: Server returns signing key (NOT JWT!)
Response: {
  "xsrfToken": "base64_encoded_key",
  "keyId": "key_identifier"
}

# Step 3: Generate JWT locally using HMAC-SHA256
key_bytes = base64.decode(xsrfToken)
jwt = hmac_sha256(key_bytes, payload)
# payload: iss, aud, sub, iat, exp (now+300s), nbf
```

**Critical Parameters**:
- JWT validity: 300 seconds (5 minutes)
- Refresh timing: 270 seconds (4.5 minutes before expiry)
- Algorithm: HMAC-SHA256
- Refresh strategy: Passive (check on each use)

**Reference Repos**:
1. `gemini-business2api` (Python) - Confirmed local JWT generation
2. `business-gemini-pool` (Python) - Same implementation
3. `linlee996/gemini-business` (Python) - Same pattern
4. `business2api` (Go) - 404 errors, couldn't verify

---

### Account Lifecycle (30-Day Trial)

**Date**: 2025-01-31
**Source**: User clarification + design docs

**Key Discovery**: Gemini Business accounts expire after 30 days of trial period.

**Timeline**:
- Day 0: Register account, get cookies (valid 30 days)
- Day 1-27: Normal usage, token refreshes every 5 minutes
- Day 28-29: Warning period (< 3 days remaining)
- Day 30: Trial expires, cookies invalid
- Day 30+: Must register new account

**Detection Logic**:
```python
def is_expired(account) -> bool:
    age_days = (time.time() - account.created_at) / 86400
    return age_days >= 30

def should_warn_expiry(account) -> bool:
    remaining_days = get_remaining_days(account)
    return 0 < remaining_days < 3
```

**Implications**:
- Need `created_at` field in account config
- Need background task for expiry warnings
- Need automatic cleanup of expired accounts
- Consider auto-registration with 2925 email (optional)

---

### Configuration Format

**Date**: 2025-01-31
**Source**: Design docs

**Required Account Fields**:
```json
{
  "email": "xxx@goodcv.fun",
  "team_id": "uuid",  // Also used as config_id
  "secure_c_ses": "Cookie value",
  "host_c_oses": "Cookie value",
  "csesidx": "Cookie value",
  "user_agent": "Browser UA",
  "created_at": "2025-01-31T10:00:00Z",  // ISO 8601
  "expires_at": "2025-03-02T10:00:00Z"   // Optional
}
```

**Note**: No separate `config_id` field - use `team_id` directly to avoid redundancy.

---

### Account Pool Strategy

**Date**: 2025-01-31
**Source**: Design docs

**Rotation**: Round-robin across all active accounts

**Cooldown Periods**:
- 401/403 (Auth errors): 7200 seconds (2 hours)
- 429 (Rate limit): 14400 seconds (4 hours)

**Account States**:
- `active` - Normal usage
- `cooldown_401` - Auth error cooldown
- `cooldown_429` - Rate limit cooldown
- `expired` - 30-day trial ended
- `expiring_soon` - < 3 days remaining
- `error` - Multiple consecutive failures

---

### Technology Stack Decisions

**Date**: 2025-01-31
**Source**: User requirements + agent-rules

**Package Manager**: uv (NOT pip)
- Faster dependency resolution
- Better reproducibility
- PEP 621 compliance

**Dependency Management**: pyproject.toml
- Modern Python standard
- Unified configuration (dependencies + tool config)
- Supports optional dependency groups ([dev], [test])

**Virtual Environment**: MANDATORY
- NEVER install packages globally
- Always use `.venv/` directory
- Lock Python version with `.python-version` file

**Testing Framework**: pytest
- Async support (pytest-asyncio)
- Coverage reporting (pytest-cov)
- Fixtures for reusable test setup

---

### Docker Deployment Constraints

**Date**: 2025-01-31
**Source**: Design docs

**Target Platform**: Raspberry Pi 5 (ARM64)

**Resource Limits**:
- Memory: 1GB max (container limit)
- CPU: 2.0 cores max
- Reserved: 256MB memory, 0.5 cores

**Requirements**:
- Base image: `python:3.11-slim` (ARM64 compatible)
- Health check: `curl -f http://localhost:8000/health`
- Volume mount: `./config:/app/config` (for hot reload)
- Log rotation: 10MB max size, 3 files

---

### 2925 Email Integration (Optional)

**Date**: 2025-01-31
**Source**: Design docs

**Email Setup**:
- Custom domain: xxx@goodcv.fun
- Forwards to: sjiangtao@2925.com
- IMAP server: imap.2925.com:993

**Use Case**: Automated account registration
- Playwright: Navigate signup flow
- 2925 IMAP: Retrieve verification code
- Extract 6-digit code from Google email
- Complete registration automatically

**Status**: Marked as Phase 3 optional feature (not Phase 1 priority)

---

## 📖 Code Examples

### Example: Local JWT Generation

```python
import hmac
import hashlib
import base64
import json
import time

def generate_jwt(xsrf_token: str, team_id: str) -> str:
    """Generate JWT locally using HMAC-SHA256"""
    # Decode signing key
    key_bytes = base64.b64decode(xsrf_token)

    # Build payload
    now = int(time.time())
    payload = {
        "iss": "gemini-business",
        "aud": "gemini-business-api",
        "sub": team_id,
        "iat": now,
        "exp": now + 300,  # 5 minutes
        "nbf": now
    }

    # Encode payload
    header = {"alg": "HS256", "typ": "JWT"}
    header_b64 = base64.urlsafe_b64encode(
        json.dumps(header).encode()
    ).decode().rstrip("=")
    payload_b64 = base64.urlsafe_b64encode(
        json.dumps(payload).encode()
    ).decode().rstrip("=")

    # Sign with HMAC-SHA256
    message = f"{header_b64}.{payload_b64}"
    signature = hmac.new(
        key_bytes,
        message.encode(),
        hashlib.sha256
    ).digest()
    signature_b64 = base64.urlsafe_b64encode(signature).decode().rstrip("=")

    return f"{message}.{signature_b64}"
```

---

## 🤔 Open Questions

### Q1: How to handle concurrent token refresh?
**Answer**: Use `asyncio.Lock` to ensure only one refresh happens at a time.

### Q2: Should we cache Gemini session IDs?
**Decision**: Not in Phase 1. Create new session per request for simplicity.

### Q3: How to test hot reload without manual file editing?
**Answer**: Integration test can programmatically modify `accounts.json` and verify reload.

---

## 🔗 Useful References

- Reference implementation: `/home/yukun/dev/gemini-business-automation/gemini-business2api/core/jwt.py`
- Design docs: `docs/` directory (7 files)
- Agent rules: `agent-rules/` directory
- Python/uv workflow: `agent-rules/04-python-uv-workflow.md`

---

## 📊 Statistics

**Design Documents Reviewed**: 7
- 01-architecture-design.md
- 02-api-compatibility-layer.md
- 03-config-hot-reload.md
- 04-deployment-and-operations.md
- 05-testing-strategy.md
- 06-implementation-plan.md
- 07-account-lifecycle-management.md

**Reference Repos Analyzed**: 4
- gemini-business2api ✅
- business-gemini-pool ✅
- linlee996/gemini-business ✅
- business2api (Go) ❌ (404 errors)

**Total Estimated Time (Phase 1)**: 17-25 days (3-4 weeks)
