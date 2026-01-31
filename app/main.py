"""
Gemini Business API - Main Application Entry

Multi-API compatibility layer for Gemini Business (OpenAI/Gemini/Claude formats)
"""

import logging

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
import httpx

from app.config import ConfigLoader
from app.core.account_pool import AccountPool
from app.core.error_handlers import (
    general_exception_handler,
    http_exception_handler,
    httpx_exception_handler,
    validation_exception_handler,
)
from app.routes import chat, status

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# App metadata
app = FastAPI(
    title="Gemini Business API",
    description="Multi-API compatibility layer for Gemini Business",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Register exception handlers
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(httpx.HTTPStatusError, httpx_exception_handler)
app.add_exception_handler(httpx.RequestError, httpx_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应该配置具体的域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(chat.router)
app.include_router(status.router)


@app.on_event("startup")
async def startup_event():
    """Initialize application on startup"""
    logger.info("🚀 Starting Gemini Business API...")

    try:
        # Load configuration
        config_loader = ConfigLoader("config/accounts.json")
        accounts = config_loader.load_accounts()

        # Initialize account pool
        pool = AccountPool()
        for account in accounts:
            pool.add_account(account)

        # Set pool for routes
        chat.set_account_pool(pool)
        status.set_account_pool(pool)

        logger.info(f"✅ Initialized with {len(accounts)} account(s)")
        logger.info(f"📊 Pool status: {pool.get_pool_status()}")

        # Warn about expiring accounts
        pool.warn_expiring_accounts()

    except FileNotFoundError as e:
        logger.error(f"❌ Configuration file not found: {e}")
        logger.error("Please create config/accounts.json with your account credentials")
    except Exception as e:
        logger.error(f"❌ Startup failed: {e}")
        raise


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "name": "Gemini Business API",
        "version": "1.0.0",
        "status": "active",
        "docs": "/docs",
        "endpoints": {
            "chat": "/api/v1/chat/send",
            "upload": "/api/v1/chat/upload",
            "health": "/api/v1/status/health",
            "pool_status": "/api/v1/status/pool",
            "accounts": "/api/v1/status/accounts",
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
