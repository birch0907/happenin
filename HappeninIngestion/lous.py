
import html
import requests

from datetime import datetime
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs


# --------------------------------------------------
# HAPPENIN' — LOU'S EVENT COLLECTOR
# --------------------------------------------------

CALENDAR_URL = "https://www.wearelous.com/lous-live"

VENUE_NAME = "Lou's"
VENUE_ADDRESS = "13 Brattle Street, Cambridge, MA 02138"

UTC = ZoneInfo("UTC")
EASTERN = ZoneInfo("America/New_York")


def convert_google_time(time_text):

    # Google Calendar provides UTC timestamps.
    # Example: 20261009T010000Z

    utc_time = datetime.strptime(
        time_text,
        "%Y%m%dT%H%M%SZ"
    ).replace(tzinfo=UTC)

    return utc_time.astimezone(EASTERN).isoformat()


def collect_lous_events():

    response = requests.get(
        CALENDAR_URL,
        timeout=20
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    events = []
    seen_links = set()

    for link in soup.find_all("a", href=True):

        href = link["href"]

        if "google.com/calendar/event" not in href:
            continue

        # Avoid collecting the same calendar link twice.
        if href in seen_links:
            continue

        seen_links.add(href)

        parameters = parse_qs(
            urlparse(href).query
        )

        title = html.unescape(
            parameters.get("text", [""])[0]
        ).strip()

        dates = parameters.get("dates", [""])[0]

        # Skip incomplete or unsupported calendar entries.
        if not title or "/" not in dates:
            continue

        start_text, end_text = dates.split("/", 1)

        try:
            start = convert_google_time(start_text)
            end = (
                convert_google_time(end_text)
                if end_text else None
            )
        except ValueError:
            print("Skipping invalid Lou's date:", title)
            continue

        event = {
            "title": title,
            "start": start,
            "end": end,
            "venue": VENUE_NAME,
            "address": VENUE_ADDRESS,
            "city": "Cambridge",
            "state": "MA",
            "source_type": "venue_website",
            "source_name": "Lou's",
            "source_url": href
        }

        events.append(event)

    return events


# --------------------------------------------------
# INDEPENDENT TEST
# --------------------------------------------------

if __name__ == "__main__":

    events = collect_lous_events()

    print("Lou's events collected:", len(events))

    for event in events[:5]:
        print()
        print("Title:", event["title"])
        print("Start:", event["start"])
        print("End:", event["end"])
        print("Venue:", event["venue"])
