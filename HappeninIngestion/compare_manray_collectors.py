"""Compare existing ManRay collector with reusable ICS parser on one live feed.
Run in HappeninIngestion: python compare_manray_collectors.py
Read-only: does not change ingestion, feeds, or event databases.
"""
from collections import Counter
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo
import requests
import manray
from calendar_collector import parse_ics_events


def signature(event):
    return (event.get('title'), event.get('start'), event.get('end'),
            event.get('venue'), event.get('address'), event.get('description'),
            event.get('source_name'), event.get('url'))


def main():
    print('Downloading ManRay calendar once...')
    response = requests.get(manray.CALENDAR_URL, timeout=30)
    response.raise_for_status()
    content = response.content
    print(f'Fetched {len(content)} bytes')
    # Ensure both collectors use the same ICS bytes. The legacy collector fetches
    # internally, so replace just that fetch with the response already downloaded.
    with patch.object(manray.requests, 'get', return_value=response):
        old = manray.collect_manray_events()
    new = parse_ics_events(
        content, calendar_url=manray.CALENDAR_URL,
        venue=manray.VENUE, address=manray.ADDRESS,
        source_name='ManRay', event_url='https://manrayclub.com/monthly-calendar/',
        now=datetime.now(ZoneInfo('America/New_York')),
    )
    a, b = Counter(map(signature, old)), Counter(map(signature, new))
    old_only = list((a - b).elements())
    new_only = list((b - a).elements())
    print(f'Existing ManRay: {len(old)} events')
    print(f'Reusable ICS:    {len(new)} events')
    print(f'Existing-only:   {len(old_only)} events')
    print(f'New-only:        {len(new_only)} events')
    if old_only:
        print('\nEXISTING-ONLY (up to 10):')
        for event in old_only[:10]:
            print(' ', event[1], '|', event[0])
    if new_only:
        print('\nNEW-ONLY (up to 10):')
        for event in new_only[:10]:
            print(' ', event[1], '|', event[0])
    if not old_only and not new_only:
        print('\nPASS: event content matches (IDs intentionally differ).')
    else:
        print('\nREVIEW: differences found; do not replace the original collector yet.')


if __name__ == '__main__':
    main()
