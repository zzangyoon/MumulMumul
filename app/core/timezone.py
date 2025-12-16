from datetime import datetime
from app.config import settings

def get_current_timestamp() -> int:
    """현재 타임스탬프 (ms, Asia/Seoul)"""
    return int(datetime.now(settings.TIMEZONE).timestamp() * 1000)


def get_current_datetime() -> datetime:
    """현재 datetime (timezone-aware)"""
    return datetime.now(settings.TIMEZONE)


def timestamp_to_datetime(timestamp_ms: int) -> datetime:
    """타임스탬프 → datetime (timezone-aware)"""
    return datetime.fromtimestamp(timestamp_ms / 1000, settings.TIMEZONE)


def datetime_to_timestamp(dt: datetime) -> int:
    """datetime → 타임스탬프 (ms)"""
    if dt.tzinfo is None:
        dt = settings.TIMEZONE.localize(dt)
    return int(dt.timestamp() * 1000)


def format_datetime(dt: datetime, format_str: str = "%Y-%m-%d %H:%M:%S") -> str:
    """datetime 포맷팅"""
    if dt.tzinfo is None:
        dt = settings.TIMEZONE.localize(dt)
    return dt.strftime(format_str)

def datetime_to_custom_str(dt: datetime) -> str:
    """
    datetime 객체를 특정 포맷의 문자열로 변환 > 2025년 12월 31일 오후 11:59분 59초)"""
    return dt.strftime("%Y년 %m월 %d일 %p %I:%M")

def datetime_to_iso_milliseconds(dt: datetime) -> str:
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")
