"""Read-only ManRay calendar comparison diagnostic.

Place beside manray.py and calendar_collector.py. Run:
    python diagnose_manray_window.py
Downloads the calendar once. Does not modify project files.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from icalendar import Calendar
import recurring_ical_events

from manray import CALENDAR_URL
from calendar_collector import parse_ics_events

EASTERN = ZoneInfo('America/New_York')


def main():
    now = datetime.now(EASTERN)
    end = now + timedelta(days=14)
    print('Window start:', now.isoformat())
    print('Window end:  ', end.isoformat())
    response = requests.get(CALENDAR_URL, timeout=30)
    response.raise_for_status()
    content = response.content
    calendar = Calendar.from_ical(content)
    occurrences = recurring_ical_events.of(calendar).between(now, end)

    original_style = []
    for event in occurrences:
        if str(event.get('STATUS', '')).upper() == 'CANCELLED':
            continue
        title = str(event.get('SUMMARY', '')).strip()
        if not title or 'closed' in title.lower():
            continue
        start = event.decoded('DTSTART')
        if not isinstance(start, datetime):
            continue
        if start.tzinfo is None:
            start = start.replace(tzinfo=EASTERN)
        start = start.astimezone(EASTERN)
        original_style.append((title, start))

    reusable = parse_ics_events(
        content,
        calendar_url=CALENDAR_URL,
        venue='ManRay',
        address='40 Prospect Street, Cambridge, MA 02139',
        source_name='ManRay',
        event_url='https://manrayclub.com/monthly-calendar/',
        now=now,
    )
    original_set = set(original_style)
    reusable_set = {(e['title'], datetime.fromisoformat(e['start'])) for e in reusable}
    print('Original-style count:', len(original_set))
    print('Reusable count:      ', len(reusable_set))
    print('\nOriginal-only entries:')
    for title, start in sorted(original_set - reusable_set, key=lambda x: x[1]):
        print(' ', start.isoformat(), '|', title)
        print('   before window:', start < now)
        print('   at/after end: ', start >= end)
    print('\nReusable-only entries:')
    for title, start in sorted(reusable_set - original_set, key=lambda x: x[1]):
        print(' ', start.isoformat(), '|', title)
    print('\nThis diagnostic does not change any event files.')


if __name__ == '__main__':
    main()
