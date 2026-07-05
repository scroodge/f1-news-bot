#!/usr/bin/env python3
"""
Script to run both main application and Telegram bot
"""

import signal
import subprocess
import sys
import time
from pathlib import Path


def signal_handler(signum, frame):
    """Handle Ctrl+C gracefully"""
    print("\n🛑 Stopping all processes...")
    sys.exit(0)


def main():
    """Main function"""
    print("🚀 Starting F1 News Bot System...")
    print("📱 Main app: http://localhost:8000")
    print("🤖 Telegram bot: Running separately")
    print("🛑 Press Ctrl+C to stop all processes")

    # Setup signal handler
    signal.signal(signal.SIGINT, signal_handler)

    try:
        # Start main application
        print("\n1️⃣ Starting main application...")
        main_process = subprocess.Popen(
            [sys.executable, "start_local.py"], cwd=Path(__file__).parent
        )

        # Wait a bit for main app to start
        time.sleep(3)

        # Start Telegram bot
        print("2️⃣ Starting Telegram bot...")
        bot_process = subprocess.Popen(
            [sys.executable, "telegram_bot_standalone.py"], cwd=Path(__file__).parent
        )

        print("\n✅ Both processes started!")
        print("🌐 Main app: http://localhost:8000")
        print("📚 API docs: http://localhost:8000/docs")
        print("🤖 Telegram bot: Check your bot for commands")

        # Wait for processes
        try:
            main_process.wait()
        except KeyboardInterrupt:
            print("\n🛑 Stopping processes...")
            main_process.terminate()
            bot_process.terminate()

            # Wait for graceful shutdown
            try:
                main_process.wait(timeout=5)
                bot_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                print("⚠️  Force killing processes...")
                main_process.kill()
                bot_process.kill()

            print("✅ All processes stopped")

    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
