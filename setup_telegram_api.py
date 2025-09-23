#!/usr/bin/env python3
"""
Script to help setup Telegram API credentials for channel monitoring
"""
import os
import sys
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

def setup_telegram_api():
    """Setup Telegram API credentials"""
    print("🔧 Telegram API Setup for F1 News Bot")
    print("=" * 50)
    
    # Get API credentials
    api_id = input("Enter your Telegram API ID: ").strip()
    api_hash = input("Enter your Telegram API Hash: ").strip()
    phone = input("Enter your phone number (with country code, e.g., +1234567890): ").strip()
    
    if not all([api_id, api_hash, phone]):
        print("❌ All fields are required!")
        return False
    
    try:
        # Create client
        client = TelegramClient("f1_news_bot", api_id, api_hash)
        
        print("\n📱 Starting authentication...")
        client.start(phone=phone)
        
        if not client.is_user_authorized():
            print("❌ Authentication failed!")
            return False
        
        print("✅ Authentication successful!")
        
        # Test channel access
        print("\n🔍 Testing channel access...")
        test_channels = ["@first_places", "@f1kekw"]
        
        for channel in test_channels:
            try:
                entity = client.get_entity(channel)
                print(f"✅ Can access {channel}: {entity.title}")
            except Exception as e:
                print(f"❌ Cannot access {channel}: {e}")
        
        client.disconnect()
        
        # Update .env file
        print("\n📝 Updating .env file...")
        update_env_file(api_id, api_hash, phone)
        
        print("\n🎉 Setup complete! Telegram collector is now enabled.")
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def update_env_file(api_id, api_hash, phone):
    """Update .env file with API credentials"""
    env_file = ".env"
    
    # Read current .env
    lines = []
    if os.path.exists(env_file):
        with open(env_file, 'r') as f:
            lines = f.readlines()
    
    # Update or add credentials
    updated = False
    for i, line in enumerate(lines):
        if line.startswith("TELEGRAM_API_ID="):
            lines[i] = f"TELEGRAM_API_ID={api_id}\n"
            updated = True
        elif line.startswith("TELEGRAM_API_HASH="):
            lines[i] = f"TELEGRAM_API_HASH={api_hash}\n"
            updated = True
        elif line.startswith("TELEGRAM_PHONE="):
            lines[i] = f"TELEGRAM_PHONE={phone}\n"
            updated = True
    
    # Add if not found
    if not updated:
        lines.extend([
            f"TELEGRAM_API_ID={api_id}\n",
            f"TELEGRAM_API_HASH={api_hash}\n",
            f"TELEGRAM_PHONE={phone}\n"
        ])
    
    # Write back
    with open(env_file, 'w') as f:
        f.writelines(lines)
    
    print(f"✅ Updated {env_file}")

if __name__ == "__main__":
    print("To get Telegram API credentials:")
    print("1. Go to https://my.telegram.org/apps")
    print("2. Create a new application")
    print("3. Copy API ID and API Hash")
    print("4. Use your phone number for authentication")
    print()
    
    if setup_telegram_api():
        sys.exit(0)
    else:
        sys.exit(1)
