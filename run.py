#!/usr/bin/env python3
"""
F1 News Bot - Main entry point
"""
import asyncio
import sys
import os
from pathlib import Path

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.main import app
import uvicorn

if __name__ == "__main__":
    # Run the FastAPI application
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
