# Gemini Business Cookie Refresher

Standalone service to refresh Gemini Business cookies and update gemini-business-api via /admin/accounts.

## Quick Start

1. Copy `.env.example` to `.env` and fill values.
2. Create a virtual environment with uv:
   ```bash
   uv venv
   source .venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   uv pip install -e ".[dev]"
   ```
4. Run tests:
   ```bash
   pytest
   ```

## Configuration

Required env vars:
- `ADMIN_BASE_URL`
- `ADMIN_API_KEY`
- `IMAP_HOST`
- `IMAP_PORT`
- `IMAP_USER`
- `IMAP_PASS`
- `GEMINI_LOGIN_EMAIL`
- `XSRF_TOKEN` (optional, enables login/email flow)
- `GRECAPTCHA_TOKEN` (optional)

## Run Modes

- `--once`: run a single refresh cycle
- `--schedule`: run continuous scheduled refresh

## Docker Notes

The container includes Google Chrome + Xvfb. Set `DISPLAY=:99` for headed automation.

## Error Handling

- Login timeouts raise `RuntimeError("login timeout")`.
- Sign-in errors raise `RuntimeError("signin error")`.
- Challenge pages (challenge/denied/blocked) raise `RuntimeError("challenge detected")`.
- Verification page failures (`verify-oob-code`) raise `RuntimeError("verification failed")`.
- IMAP code fetch failures raise `ValueError("verification code not found")`.
