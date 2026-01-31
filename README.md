# Gemini Business API

Multi-API compatibility layer for Gemini Business (OpenAI/Gemini/Claude formats)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

## 🎯 Features

- **Multi-API Compatibility**: OpenAI, Gemini, Claude API formats
- **Smart Account Pool**: Automatic rotation, cooldown management, failover
- **30-Day Lifecycle**: Automatic account expiry detection and warnings
- **Hot Reload**: Configuration changes without service restart
- **Streaming SSE**: Real-time response streaming
- **Multimodal Support**: Image/video input (URL + Base64)
- **Web Management UI**: Real-time monitoring and account management
- **Docker Ready**: Optimized for Raspberry Pi 5

## 📋 Requirements

- Python 3.11+
- uv (package manager)
- Docker + docker-compose (optional)

## 🚀 Quick Start

### Local Development

```bash
# Clone repository
git clone git@github.com:sjiangtao2024/gemini-business-api.git
cd gemini-business-api

# Create virtual environment with uv
uv venv

# Activate virtual environment
source .venv/bin/activate

# Install dependencies
uv pip install -e ".[dev]"

# Create configuration
cp config/accounts.json.example config/accounts.json
# Edit config/accounts.json with your Gemini Business accounts

# Run development server
uvicorn app.main:app --reload --port 8000
```

### Access Services

- **API Documentation**: http://localhost:8000/docs
- **Management UI**: http://localhost:8000/static/admin.html
- **Health Check**: http://localhost:8000/health

### Docker Deployment

```bash
# Build and start
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

## 📝 Configuration

### accounts.json Format

```json
{
  "accounts": [
    {
      "email": "your-email@example.com",
      "team_id": "your-team-id",
      "secure_c_ses": "CSE.xxx...",
      "host_c_oses": "COS.xxx...",
      "csesidx": "123456",
      "user_agent": "Mozilla/5.0...",
      "created_at": "2025-01-31T10:00:00Z",
      "expires_at": "2025-03-02T10:00:00Z"
    }
  ],
  "settings": {
    "account_expiry_days": 30,
    "expiry_warning_days": 3,
    "cooldown_401_seconds": 7200,
    "cooldown_429_seconds": 14400
  }
}
```

### How to Get Configuration

1. Login to [Gemini Business](https://business.gemini.google/)
2. Open DevTools (F12)
3. **Get Cookies**: Application → Cookies → Copy `__Secure-c-SES`, `__Host-c-OSES`, `csesidx`
4. **Get team_id**: Network → Find any request → Copy `configId` UUID
5. **Get User-Agent**: Console → `navigator.userAgent`

## 🔧 Development

### Run Tests

```bash
# All tests
pytest

# Unit tests only
pytest tests/unit -v

# With coverage
pytest --cov=app --cov-report=html
```

### Code Quality

```bash
# Format code
ruff format .

# Lint code
ruff check .

# Type check
mypy app/
```

## 📚 API Endpoints

### OpenAI Compatible

```bash
# Chat completions (streaming/non-streaming)
POST /v1/chat/completions

# List available models
GET /v1/models
```

### Gemini Native API

```bash
# Generate content
POST /v1beta/models/{model}:generateContent

# List models
GET /v1beta/models
```

### Claude Compatible

```bash
# Create messages (streaming/non-streaming)
POST /v1/messages
```

### Admin Management API

```bash
# Account management
GET /admin/accounts          # List all accounts with status
POST /admin/accounts         # Add new account
DELETE /admin/accounts/{email}  # Delete account

# Statistics
GET /admin/stats             # Get pool statistics

# Real-time logs
GET /admin/logs/stream       # SSE log streaming
```

### Health Check

```bash
GET /health
GET /
```

## 🏗️ Architecture

- **Token Manager**: Local JWT generation (HMAC-SHA256, 5-min validity)
- **Account Pool**: Round-robin rotation with cooldown (401/403: 2h, 429: 4h)
- **30-Day Lifecycle**: Auto-detect trial expiry, < 3 days warning
- **Hot Reload**: Watchdog-based config monitoring

## 🖥️ Management Interface

Access the web-based management UI at: `http://localhost:8000/static/admin.html`

### Features

**Dashboard**
- Real-time statistics (total/active/cooldown/expired accounts)
- Visual charts (account status distribution, success rate)
- Auto-refresh every 5 seconds

**Accounts Management**
- View all accounts with status and remaining days
- Add new accounts (modal form with validation)
- Delete accounts (with confirmation)
- Status indicators: 🟢 Active / 🟡 Cooldown / 🔴 Expired
- Expiry warnings: Red (<3 days), Yellow (<7 days)

**Real-time Logs**
- Live log streaming via Server-Sent Events (SSE)
- Log level filtering (ALL/INFO/WARNING/ERROR)
- Auto-scroll to latest entries
- Color-coded by severity

### Tech Stack

- **Frontend**: Vanilla JavaScript (no build tools required)
- **Styling**: Tailwind CSS (CDN)
- **Charts**: Chart.js (CDN)
- **Real-time**: Server-Sent Events (SSE)

## 📖 Documentation

See `docs/` directory for detailed design documents:

1. `01-architecture-design.md` - Core architecture and JWT mechanism
2. `02-api-compatibility-layer.md` - API format conversions
3. `03-config-hot-reload.md` - Hot reload implementation
4. `04-deployment-and-operations.md` - Deployment guide
5. `05-testing-strategy.md` - Testing approach
6. `06-implementation-plan.md` - Phase-by-phase plan
7. `07-account-lifecycle-management.md` - 30-day lifecycle details

## 🗺️ Roadmap

- [x] **Phase 1**: Core API (Token Manager, Account Pool, OpenAI compatibility) ✅
- [x] **Phase 2**: Streaming SSE + Multimodal (image/video input, multi-API formats) ✅
- [x] **Phase 3**: Frontend management interface (real-time monitoring, account CRUD) ✅
- [ ] **Phase 4**: Image/video generation (optional)

## 📄 License

MIT License - see LICENSE file for details

## 🤝 Contributing

This is a personal project. For issues or suggestions, please open an issue.

## ⚠️ Important Notes

- **JWT is generated locally**, NOT returned from server
- **30-day trial period** - accounts expire after 30 days
- **Cookie validity** - 30 days from account creation
- **Always use virtual environment** - Never install globally
