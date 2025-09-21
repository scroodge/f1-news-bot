#!/usr/bin/env python3
"""
Local startup script for F1 News Bot
"""
import os
import sys
import asyncio
from pathlib import Path

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def setup_environment():
    """Setup environment variables for local development"""
    # Set default values for required environment variables
    os.environ.setdefault('TELEGRAM_BOT_TOKEN', 'your_bot_token_here')
    os.environ.setdefault('TELEGRAM_CHANNEL_ID', 'your_channel_id_here')
    os.environ.setdefault('DATABASE_URL', 'postgresql://f1_user:f1_password@localhost:5432/f1_news')
    os.environ.setdefault('REDIS_URL', 'redis://localhost:6379/0')
    os.environ.setdefault('OLLAMA_BASE_URL', 'http://localhost:11434')
    os.environ.setdefault('OLLAMA_MODEL', 'llama2')
    os.environ.setdefault('LOG_LEVEL', 'INFO')
    os.environ.setdefault('DEBUG', 'true')

def main():
    """Main function"""
    print("🚀 Starting F1 News Bot locally...")
    
    # Setup environment
    setup_environment()
    
    try:
        # Import and run the application
        from src.main import app
        import uvicorn
        
        print("✅ Application loaded successfully!")
        print("🌐 Starting FastAPI server on http://localhost:8000")
        print("📚 API documentation available at http://localhost:8000/docs")
        print("🛑 Press Ctrl+C to stop the server")
        
        # Run the server
        uvicorn.run(
            "src.main:app",
            host="0.0.0.0",
            port=8000,
            reload=True,
            log_level="info"
        )
        
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user")
    except Exception as e:
        print(f"❌ Error starting server: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
