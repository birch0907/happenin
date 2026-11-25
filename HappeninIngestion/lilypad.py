import html
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs


def convert_google_time(time_text):

    # Google Calendar gives us UTC timestamps:
    #
    # 20261004T193000Z

    utc_time = datetime.strptime(
        time_text,
        "%Y%m%dT%H%M%SZ"
    )

    utc = ZoneInfo("UTC")

    utc_time = utc_time.replace(
        tzinfo=utc
    )

    # Convert UTC into Cambridge local time.
    eastern = ZoneInfo(
        "America/New_York"
    )

    local_time = utc_time.astimezone(
        eastern
    )

    return local_time.isoformat()


def collect_lilypad_events():

    url = "https://www.lilypadinman.com/"

    response = requests.get(
        url,
        timeout=20
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    # Find Google's calendar links.
    calendar_links = soup.find_all(
        "a",
        href=lambda href:
            href
            and "google.com/calendar/event" in href
    )

    events = []

    for link in calendar_links:

        href = link.get("href")

        parsed_url = urlparse(href)

        parameters = parse_qs(
            parsed_url.query
        )

        title = parameters.get(
            "text",
            [""]
        )[0]

        dates = parameters.get(
            "dates",
            [""]
        )[0]

        address = parameters.get(
            "location",
            [""]
        )[0]

        # Clean HTML entities and whitespace.
        title = html.unescape(
            title
        ).strip()

        # Some Lilypad calendar entries omit
        # the address.
        if not address:
            address = (
                "1353 Cambridge Street, "
                "Cambridge, MA 02139"
            )

        start_text = ""
        end_text = ""

        if "/" in dates:
            start_text, end_text = dates.split(
                "/",
                1
            )

        start = convert_google_time(
            start_text
        )

        end = convert_google_time(
            end_text
        )

        event = {
            "title": title,
            "start": start,
            "end": end,
            "venue": "The Lilypad",
            "address": address,
            "city": "Cambridge",
            "state": "MA",
            "source_type": "venue_website",
            "source_name": "Lilypad",
            "source_url": href
        }

        events.append(event)

    return events