from __future__ import annotations

import datetime as dt
from functools import lru_cache

import exchange_calendars as xcals


EXPECTED_EXCHANGE_CALENDARS_VERSION = "4.13.2"
if xcals.__version__ != EXPECTED_EXCHANGE_CALENDARS_VERSION:
    raise RuntimeError(
        "exchange_calendars runtime version mismatch: "
        f"expected {EXPECTED_EXCHANGE_CALENDARS_VERSION}, got {xcals.__version__}"
    )
CALENDAR_VERSION = f"exchange-calendars-{EXPECTED_EXCHANGE_CALENDARS_VERSION}"
MARKET_CALENDAR_IDS = {
    "a_share": "XSHG",
    "hk": "XHKG",
    "us": "XNYS",
}


def _as_date(value: dt.date | dt.datetime | str) -> dt.date:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value)[:10])


def _as_open_anchor(value: dt.date | dt.datetime | str) -> dt.datetime:
    """Normalize a decision time without silently guessing a datetime zone."""

    if isinstance(value, dt.datetime):
        parsed = value
    elif isinstance(value, dt.date):
        parsed = dt.datetime.combine(value, dt.time.min, tzinfo=dt.timezone.utc)
    else:
        text = str(value)
        if len(text) == 10:
            day = dt.date.fromisoformat(text)
            parsed = dt.datetime.combine(day, dt.time.min, tzinfo=dt.timezone.utc)
        else:
            parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("datetime value must be timezone-aware")
    return parsed.astimezone(dt.timezone.utc)


def calendar_id(market: str) -> str:
    try:
        return MARKET_CALENDAR_IDS[market]
    except KeyError as exc:
        raise ValueError(f"unsupported market: {market}") from exc


def market_local_date(market: str, value: dt.datetime | str) -> dt.date:
    """Return an aware decision moment's date in the exchange timezone."""

    return _as_open_anchor(value).astimezone(_calendar(market).tz).date()


@lru_cache(maxsize=3)
def _calendar(market: str):
    return xcals.get_calendar(calendar_id(market))


def is_market_session(market: str, value: dt.date | dt.datetime | str) -> bool:
    return bool(_calendar(market).is_session(_as_date(value).isoformat()))


def next_session(
    market: str,
    value: dt.date | dt.datetime | str,
    *,
    include_current: bool = True,
) -> dt.date:
    calendar = _calendar(market)
    day = _as_date(value)
    session = calendar.date_to_session(day.isoformat(), direction="next")
    if not include_current and calendar.is_session(day.isoformat()):
        session = calendar.sessions_window(session, 2)[-1]
    return session.date()


def nth_session(
    market: str,
    value: dt.date | dt.datetime | str,
    n: int,
    *,
    include_current: bool = True,
) -> dt.date:
    if not isinstance(n, int) or isinstance(n, bool) or n < 1:
        raise ValueError("n must be a positive integer")
    first = next_session(market, value, include_current=include_current)
    sessions = _calendar(market).sessions_window(first.isoformat(), n)
    return sessions[-1].date()


def session_dates(
    market: str,
    start: dt.date | dt.datetime | str,
    end: dt.date | dt.datetime | str,
) -> list[dt.date]:
    start_day = _as_date(start)
    end_day = _as_date(end)
    if end_day < start_day:
        return []
    return [session.date() for session in _calendar(market).sessions_in_range(start_day, end_day)]


def session_open_at(market: str, value: dt.date | dt.datetime | str) -> str:
    """Return the exchange's regular-session open as a timezone-aware timestamp."""

    session = _as_date(value).isoformat()
    return _calendar(market).session_open(session).to_pydatetime().isoformat()


def session_close_at(market: str, value: dt.date | dt.datetime | str) -> str:
    """Return the exchange's regular-session close as a timezone-aware timestamp."""

    session = _as_date(value).isoformat()
    return _calendar(market).session_close(session).to_pydatetime().isoformat()


def expected_quote_session(
    market: str,
    value: dt.datetime | str,
) -> dt.date:
    """Return the exchange session a current quote must cover.

    Before the next regular open this is the previous exchange session.  From
    the regular open onward (including the lunch break and after the close) it
    is the current session.  This deliberately uses the exchange calendar,
    rather than weekdays, so holidays do not make an old quote look fresh.
    """

    calendar = _calendar(market)
    anchor = _as_open_anchor(value)
    local_day = anchor.astimezone(calendar.tz).date()
    if calendar.is_session(local_day.isoformat()):
        session_open = calendar.session_open(local_day.isoformat()).to_pydatetime()
        if anchor >= session_open:
            return local_day
        return calendar.previous_session(local_day.isoformat()).date()
    return calendar.date_to_session(local_day.isoformat(), direction="previous").date()


def quote_session_phase(market: str, value: dt.datetime | str) -> str:
    """Return pre, regular, break, post, or closed for an exchange clock."""

    calendar = _calendar(market)
    anchor = _as_open_anchor(value)
    local_day = anchor.astimezone(calendar.tz).date()
    if not calendar.is_session(local_day.isoformat()):
        return "closed"
    session_open = calendar.session_open(local_day.isoformat()).to_pydatetime()
    session_close = calendar.session_close(local_day.isoformat()).to_pydatetime()
    if anchor < session_open:
        return "pre"
    if anchor > session_close:
        return "post"
    if calendar.is_open_on_minute(anchor, ignore_breaks=False):
        return "regular"
    return "break"


def market_trade_window(
    market: str,
    value: dt.date | dt.datetime | str,
    *,
    horizon_sessions: int = 10,
) -> dict:
    calendar = _calendar(market)
    anchor = _as_open_anchor(value)
    # exchange_calendars.next_open is strictly greater than the supplied
    # instant. This prevents an intraday signal from being settled against an
    # already-observed session open.
    entry_open = calendar.next_open(anchor)
    entry = calendar.minute_to_session(entry_open, direction="none").date()
    forecast_end = nth_session(market, entry, horizon_sessions, include_current=True)
    forecast_end_close = calendar.session_close(forecast_end.isoformat())
    return {
        "calendar_id": calendar_id(market),
        "calendar_version": CALENDAR_VERSION,
        "decision_time": anchor.isoformat(),
        "entry_session_open_at": entry_open.to_pydatetime().isoformat(),
        "entry_trade_date": entry.isoformat(),
        "forecast_end_trade_date": forecast_end.isoformat(),
        "forecast_end_session_close_at": forecast_end_close.to_pydatetime().isoformat(),
        "horizon_sessions": horizon_sessions,
    }


def market_trade_windows(
    value: dt.date | dt.datetime | str,
    *,
    horizon_sessions: int = 10,
) -> dict[str, dict]:
    return {
        market: market_trade_window(market, value, horizon_sessions=horizon_sessions)
        for market in MARKET_CALENDAR_IDS
    }


# Descriptive aliases used by the selector and contract tests.
session_on_or_after = next_session
sessions_in_window = session_dates
