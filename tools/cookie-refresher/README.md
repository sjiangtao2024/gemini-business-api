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
