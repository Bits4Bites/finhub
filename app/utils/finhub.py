import uuid
from datetime import datetime
from zoneinfo import ZoneInfo


def generate_demo_item_id():
    return str(uuid.uuid4())


def tz_from_yf_ticker(yf_ticker: str) -> ZoneInfo:
    """
    Gets the timezone for a Yahoo Finance ticker.
    """
    yf_ticker = yf_ticker.upper()
    if yf_ticker.endswith(".AX"):
        return ZoneInfo("Australia/Sydney")
    elif yf_ticker.endswith(".VN"):
        return ZoneInfo("Asia/Ho_Chi_Minh")
    else:
        return ZoneInfo("America/New_York")


def yyyy_mm_dd_to_iso(yyyy_mm_dd: str, tz: ZoneInfo = None, tz_name: str = None) -> str | None:
    """
    Converts a date string in the format 'YYYY-MM-DD' to ISO format 'YYYY-MM-DD 00:00:00+hh:mm'.
    """
    tz = tz or (ZoneInfo(tz_name) if tz_name else ZoneInfo("UTC"))
    try:
        return datetime.strptime(yyyy_mm_dd, "%Y-%m-%d").replace(tzinfo=tz).isoformat(sep=" ", timespec="seconds")
    except ValueError:
        return None
