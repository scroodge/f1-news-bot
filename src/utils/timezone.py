"""
Timezone utilities for F1 News Bot
"""
from datetime import datetime, timezone, timedelta
from typing import Optional
import pytz
from ..config import settings

def get_local_timezone():
    """Get the configured local timezone"""
    try:
        return pytz.timezone(settings.timezone)
    except Exception:
        # Fallback to UTC if timezone is invalid
        return pytz.UTC

def utc_now():
    """Get current UTC time"""
    return datetime.utcnow().replace(tzinfo=pytz.UTC)

def local_now():
    """Get current local time"""
    return datetime.now(get_local_timezone())

def utc_to_local(utc_dt: datetime) -> datetime:
    """Convert UTC datetime to local timezone"""
    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=pytz.UTC)
    
    local_tz = get_local_timezone()
    return utc_dt.astimezone(local_tz)

def local_to_utc(local_dt: datetime) -> datetime:
    """Convert local datetime to UTC"""
    if local_dt.tzinfo is None:
        local_tz = get_local_timezone()
        local_dt = local_tz.localize(local_dt)
    
    return local_dt.astimezone(pytz.UTC)

def get_hours_ago_utc(hours: int) -> datetime:
    """Get UTC datetime N hours ago"""
    return utc_now() - timedelta(hours=hours)

def get_hours_ago_local(hours: int) -> datetime:
    """Get local datetime N hours ago"""
    return local_now() - timedelta(hours=hours)

def format_datetime(dt: datetime, format_str: str = "%d.%m.%Y %H:%M") -> str:
    """Format datetime to string"""
    if dt.tzinfo is None:
        # Assume UTC if no timezone info
        dt = dt.replace(tzinfo=pytz.UTC)
    
    # Convert to local timezone for display
    local_dt = utc_to_local(dt)
    return local_dt.strftime(format_str)
