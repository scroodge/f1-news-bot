"""Tests for Telegram Mini App initData validation"""

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

from src.webapp.auth import validate_init_data

BOT_TOKEN = "123456:TEST-TOKEN"


def make_init_data(user_id: int = 42, auth_date: int | None = None, token: str = BOT_TOKEN) -> str:
    """Build a correctly signed initData string the way Telegram does"""
    pairs = {
        "auth_date": str(auth_date if auth_date is not None else int(time.time())),
        "query_id": "AAE-test",
        "user": json.dumps({"id": user_id, "first_name": "Way"}),
    }
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret_key = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    signature = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode({**pairs, "hash": signature})


def test_valid_init_data_passes():
    data = validate_init_data(make_init_data(user_id=42), BOT_TOKEN)
    assert data is not None
    assert data["user"]["id"] == 42


def test_tampered_user_rejected():
    init_data = make_init_data(user_id=42)
    tampered = init_data.replace("42", "43")
    assert validate_init_data(tampered, BOT_TOKEN) is None


def test_wrong_bot_token_rejected():
    init_data = make_init_data()
    assert validate_init_data(init_data, "999999:OTHER-TOKEN") is None


def test_missing_hash_rejected():
    assert validate_init_data("auth_date=123&user=%7B%7D", BOT_TOKEN) is None


def test_expired_auth_date_rejected():
    two_days_ago = int(time.time()) - 2 * 86400
    init_data = make_init_data(auth_date=two_days_ago)
    assert validate_init_data(init_data, BOT_TOKEN) is None


def test_garbage_rejected():
    assert validate_init_data("not-a-querystring", BOT_TOKEN) is None
    assert validate_init_data("", BOT_TOKEN) is None
