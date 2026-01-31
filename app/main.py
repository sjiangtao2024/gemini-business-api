"""
Gemini Business API - Main Application Entry

Multi-API compatibility layer for Gemini Business (OpenAI/Gemini/Claude formats)
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# App metadata
app = FastAPI(
    title="Gemini Business API",
    description="Multi-API compatibility layer for Gemini Business",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应该配置具体的域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "name": "Gemini Business API",
        "version": "0.1.0",
        "status": "active",
        "docs": "/docs",
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "gemini-business-api",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
