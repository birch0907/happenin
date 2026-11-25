from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from icalendar import Calendar, Event
from calendar_collector import parse_ics_events
from ingest import event_is_in_time_window

TZ = ZoneInfo('America/New_York')
now = datetime(2026, 10, 30, 1, 53, tzinfo=TZ)
cal = Calendar()
def add(title, start, end=None):
    e = Event(); e.add('summary', title); e.add('dtstart', start)
    e.add('uid', title.replace(' ', '-'))
    if end is not None: e.add('dtend', end)
    cal.add_component(e)
add('Ongoing', datetime(2026, 10, 29, 22, 0, tzinfo=TZ))
add('Finished', datetime(2026, 10, 29, 20, 0, tzinfo=TZ), datetime(2026, 10, 29, 23, 0, tzinfo=TZ))
add('Future', datetime(2026, 10, 31, 20, 0, tzinfo=TZ))
add('Far Past', datetime(2026, 10, 29, 18, 0, tzinfo=TZ))
rows = parse_ics_events(cal.to_ical(), calendar_url='https://example.org/test.ics', venue='Test', address='Test', now=now)
titles = {e['title'] for e in rows}
assert titles == {'Ongoing', 'Future'}, titles
for e in rows:
    assert event_is_in_time_window(e, now, now + timedelta(days=14))
assert not event_is_in_time_window({'start':datetime(2026,10,29,20,tzinfo=TZ).isoformat(), 'end':datetime(2026,10,29,23,tzinfo=TZ).isoformat()}, now, now+timedelta(days=14))
print('PASS: ongoing event retained, finished events excluded, future events retained.')
