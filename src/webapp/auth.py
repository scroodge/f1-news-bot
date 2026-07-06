"""
Telegram Mini App authentication.

The web app sends `Authorization: tma <initData>` on every request.
initData is validated per Telegram's spec: HMAC-SHA256 over the sorted
key=value pairs, keyed with HMAC("WebAppData", bot_token). Then the user id
must match TELEGRAM_ADMIN_ID. No separate login exists.
"""

import hashlib
import hmac
import json
import logging
import time
from urllib.parse import parse_qsl

from fastapi import Header, HTTPException

from ..config import settings

logger = logging.getLogger(__name__)

MAX_INIT_DATA_AGE_SECONDS = 24 * 3600


def validate_init_data(
    init_data: str, bot_token: str, max_age_seconds: int = MAX_INIT_DATA_AGE_SECONDS
) -> dict | None:
    """Validate Telegram WebApp initData; returns {'user': ..., 'auth_date': ...} or None"""
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True))
        received_hash = pairs.pop("hash", None)
        if not received_hash:
            return None

        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
        secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        computed = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(computed, received_hash):
            return None

        auth_date = int(pairs.get("auth_date", "0"))
        if max_age_seconds and time.time() - auth_date > max_age_seconds:
            return None

        user = json.loads(pairs.get("user", "{}"))
        return {"user": user, "auth_date": auth_date}
    except Exception:
        return None


async def require_admin(authorization: str = Header(default="")) -> dict:
    """FastAPI dependency: authenticated Telegram admin (or dev-mode bypass)"""
    if settings.miniapp_dev_mode:
        # Local browser testing without Telegram. NEVER enable in production.
        return {"id": 0, "first_name": "dev-mode"}

    scheme, _, init_data = authorization.partition(" ")
    if scheme.lower() != "tma" or not init_data:
        raise HTTPException(status_code=401, detail="Missing Telegram init data")

    data = validate_init_data(init_data, settings.telegram_bot_token)
    if data is None:
        raise HTTPException(status_code=401, detail="Invalid Telegram init data")

    user = data["user"]
    if not settings.telegram_admin_id or str(user.get("id")) != str(settings.telegram_admin_id):
        logger.warning(f"Mini App access denied for user {user.get('id')}")
        raise HTTPException(status_code=403, detail="Not an admin")

    return user
