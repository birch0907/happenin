"""Reusable public ICS collector for Happenin'.

Dependencies: requests, icalendar, recurring-ical-events.
Does not change the existing ingestion workflow.
"""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
import hashlib
import requests
from icalendar import Calendar
import recurring_ical_events

EASTERN = ZoneInfo('America/New_York')


def collect_ics_events(*, calendar_url, venue, address, source_name=None,
                       event_url=None, days_ahead=14, now=None,
                       exclude_title_terms=('closed',), timeout=30):
    """Return normalized events from a public ICS feed, including recurring instances.

    `now` is injectable for offline testing. Only timed events are included.
    """
    if not calendar_url.startswith(('https://', 'http://')):
        raise ValueError('calendar_url must be an HTTP(S) URL')
    response = requests.get(calendar_url, timeout=timeout)
    response.raise_for_status()
    return parse_ics_events(response.content, calendar_url=calendar_url,
                            venue=venue, address=address, source_name=source_name,
                            event_url=event_url, days_ahead=days_ahead, now=now,
                            exclude_title_terms=exclude_title_terms)


def parse_ics_events(content, *, calendar_url, venue, address, source_name=None,
                     event_url=None, days_ahead=14, now=None,
                     exclude_title_terms=('closed',)):
    """Parse ICS bytes without network access; useful for tests and saved snapshots."""
    now = now or datetime.now(EASTERN)
    if now.tzinfo is None:
        raise ValueError('now must be timezone-aware')
    now = now.astimezone(EASTERN)
    end_window = now + timedelta(days=days_ahead)
    calendar = Calendar.from_ical(content)
    # Query a generous lookback because recurrence libraries can omit zero-duration
    # occurrences without DTEND when they are near the query boundary.
    # The final overlap test below determines which occurrences qualify.
    query_start = now - timedelta(days=2)
    occurrences = recurring_ical_events.of(calendar).between(query_start, end_window)
    source = source_name or venue
    events, seen = [], set()
    for item in occurrences:
        if str(item.get('STATUS', '')).upper() == 'CANCELLED':
            continue
        title = str(item.get('SUMMARY', '')).strip()
        if not title or any(term.lower() in title.lower() for term in exclude_title_terms):
            continue
        try:
            start = item.decoded('DTSTART')
        except (KeyError, ValueError, TypeError):
            continue
        if not isinstance(start, datetime):
            continue  # All-day entries are not nightlife time slots.
        if start.tzinfo is None:
            start = start.replace(tzinfo=EASTERN)
        start = start.astimezone(EASTERN)
        end = None
        if item.get('DTEND'):
            try:
                value = item.decoded('DTEND')
                if isinstance(value, datetime):
                    if value.tzinfo is None:
                        value = value.replace(tzinfo=EASTERN)
                    end = value.astimezone(EASTERN)
            except (ValueError, TypeError):
                pass
        # An absent end is estimated at four hours, matching the app's fallback.
        # A published end time is preserved unchanged.
        effective_end = end if end is not None else start + timedelta(hours=4)
        if not (start < end_window and effective_end > now):
            continue
        uid = str(item.get('UID', '')).strip()
        # Fallback identity is deterministic if the source omitted UID.
        if not uid:
            uid = hashlib.sha256((title + '|' + venue).encode()).hexdigest()[:16]
        event_id = f'ics:{source}:{uid}:{start.isoformat()}'
        if event_id in seen:
            continue
        seen.add(event_id)
        description = str(item.get('DESCRIPTION', '')).strip()
        events.append({
            'id': event_id,
            'title': title,
            'venue': venue,
            'address': address,
            'start': start.isoformat(),
            'end': end.isoformat() if end else None,
            'description': description,
            'source_name': source,
            'url': event_url or calendar_url,
        })
    return sorted(events, key=lambda e: e['start'])
