# Cookie Refresher Service Design

**Goal:** Build an external, automated service that logs into Gemini Business, reads 2925 email verification codes, extracts cookies/session info, and updates `gemini-business-api` via `/admin/accounts` to avoid manual refresh.

**Architecture (high level):** A standalone service runs on a schedule and on-demand. It uses a dual-engine browser automation strategy: primary path with Selenium + undetected-chromedriver (headed), fallback with DrissionPage (ChromiumPage). A 2925 IMAP handler fetches verification codes. After login, a cookie extractor collects `__Secure-C_SES`, `__Host-C_OSES`, `csesidx`, `team_id`, and user-agent. An account updater pushes data to `/admin/accounts`. Failures are retried and surfaced for manual attention.

**Components:**
- Scheduler: selects accounts to refresh based on `expires_at` and error signals.
- Login Orchestrator: runs primary engine then fallback on failure.
- Mail2925Handler: IMAP login to `imap.2925.com:993`, filters Google verification emails, extracts 6-digit code.
- Cookie Extractor: parses current URL for `csesidx` + `team_id` (cid/configId) and browser cookies for `__Secure-C_SES` / `__Host-C_OSES`.
- Account Updater: calls `/admin/accounts` with updated fields; deletes first if upsert not supported.
- Observability: structured logs, per-account status, backoff, and optional alert hooks.

**Refresh strategy:**
- Compute `expires_at` from cookie expiry (UTC) minus 12 hours (safety window). If no expiry, set `expires_at = now + 12h`.
- Scheduler refreshes accounts before `expires_at` and on any 401/403 signals from API usage.
- 401/403 is treated as "cookie invalid" and triggers immediate refresh.

**Security & ops:**
- Run in a separate container with Chrome + Xvfb.
- Keep admin API key in environment secrets; only allow outbound to Gemini Business + 2925 IMAP + API.
- Rate-limit logins and add jitter to reduce bot detection.
