"""Offline smoke test: python test_calendar_collector.py"""
from datetime import datetime
from zoneinfo import ZoneInfo
from calendar_collector import parse_ics_events

SAMPLE = b'''BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Happenin Test//EN\r\nBEGIN:VEVENT\r\nUID:show-1\r\nDTSTART:20261107T200000\r\nDTEND:20261107T230000\r\nSUMMARY:Live Music Night\r\nDESCRIPTION:Sample performance\r\nEND:VEVENT\r\nBEGIN:VEVENT\r\nUID:closed-1\r\nDTSTART:20261107T210000\r\nSUMMARY:Closed\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n'''

result = parse_ics_events(SAMPLE, calendar_url='https://example.org/calendar.ics',
    venue='Test Venue', address='1 Example St, Cambridge, MA',
    now=datetime(2026, 11, 1, tzinfo=ZoneInfo('America/New_York')))
assert len(result) == 1, result
assert result[0]['title'] == 'Live Music Night'
assert result[0]['start'].startswith('2026-11-07T20:00:00')
assert result[0]['end'].startswith('2026-11-07T23:00:00')
print('PASS: timed event parsed; closure excluded; start/end preserved')
