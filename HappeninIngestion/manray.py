
import requests
import recurring_ical_events

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from icalendar import Calendar


# ManRay's public Google Calendar feed.
CALENDAR_URL = (
    "https://calendar.google.com/calendar/ical/"
    "xtine%40manrayclub.com/public/basic.ics"
)

EASTERN = ZoneInfo("America/New_York")

VENUE = "ManRay"
ADDRESS = "40 Prospect Street, Cambridge, MA 02139"


def collect_manray_events():
    """
    Download ManRay's public calendar and return events
    occurring within the next 14 days.
    """

    print("Collecting ManRay events...")

    response = requests.get(CALENDAR_URL, timeout=30)
    response.raise_for_status()

    calendar = Calendar.from_ical(response.content)

    now = datetime.now(EASTERN)
    end_window = now + timedelta(days=14)

    # Expand recurring calendar events into actual occurrences.
    occurrences = recurring_ical_events.of(calendar).between(
        now, end_window
    )

    events = []
    seen = set()

    for event in occurrences:
        # Ignore cancelled events.
        if str(event.get("STATUS", "")).upper() == "CANCELLED":
            continue

        title = str(event.get("SUMMARY", "")).strip()

        if not title:
            continue

        # Ignore closure notices rather than treating them
        # as nightlife events.
        if "closed" in title.lower():
            continue

        start = event.decoded("DTSTART")

        # Some calendars contain all-day events represented
        # as dates rather than datetimes.
        if not isinstance(start, datetime):
            continue

        if start.tzinfo is None:
            start = start.replace(tzinfo=EASTERN)

        start = start.astimezone(EASTERN)

        end = None

        if event.get("DTEND"):
            end = event.decoded("DTEND")

            if isinstance(end, datetime):
                if end.tzinfo is None:
                    end = end.replace(tzinfo=EASTERN)

                end = end.astimezone(EASTERN)
            else:
                end = None

        uid = str(event.get("UID", "")).strip()

        # A recurring series shares one UID, so include
        # the occurrence's start time in its unique ID.
        event_id = f"manray:{uid}:{start.isoformat()}"

        if event_id in seen:
            continue

        seen.add(event_id)

        description = str(event.get("DESCRIPTION", "")).strip()

        events.append({
            "id": event_id,
            "title": title,
            "venue": VENUE,
            "address": ADDRESS,
            "start": start.isoformat(),
            "end": end.isoformat() if end else None,
            "description": description,
            "source_name": "ManRay",
            "url": "https://manrayclub.com/monthly-calendar/",
        })

    events.sort(key=lambda item: item["start"])

    return events


# Allow us to test this collector independently.
if __name__ == "__main__":
    events = collect_manray_events()

    print(f"\nManRay events found: {len(events)}")

    for event in events:
        print(
            event["start"],
            "|",
            event["title"]
        )
