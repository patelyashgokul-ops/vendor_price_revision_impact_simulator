"""Explicit UTC approval/delegation instants; no operational pricing operations."""
from datetime import datetime, time, timedelta
import pytz


def within(now, start, end=None):
    """All workflow windows are [start, end), stored as naive UTC in Odoo."""
    return bool(start and now >= start and (end is None or now < end))


def expiry(approved_at, mode, days=0, local_date=None, zone=None):
    if mode == 'source_only':
        return None
    if mode == 'days':
        if type(days) is not int or days <= 0:
            raise ValueError('A positive policy duration is required.')
        return approved_at + timedelta(days=days)
    if mode != 'date' or local_date is None or not zone:
        raise ValueError('An explicit expiry date and business timezone are required.')
    try:
        tz = pytz.timezone(zone)
        # End of the selected local business date, expressed as exclusive next
        # midnight. Reject ambiguous/nonexistent instants instead of guessing.
        instant = tz.localize(datetime.combine(local_date + timedelta(days=1), time.min), is_dst=None)
    except (pytz.UnknownTimeZoneError, pytz.AmbiguousTimeError, pytz.NonExistentTimeError) as exc:
        raise ValueError('The configured local expiry boundary is not unambiguous.') from exc
    return instant.astimezone(pytz.UTC).replace(tzinfo=None)
