
import re
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests


# --------------------------------------------------
# POSH — BOSTON EVENT COLLECTOR
# --------------------------------------------------

API_URL = "https://posh.vip/api/bff/v1/explore/events"

EVENT_URL = "https://posh.vip/e/"

EASTERN = ZoneInfo("America/New_York")

DAYS_AHEAD = 14

# Boston coordinates used for POSH discovery.
SEARCH_LAT = 42.3601
SEARCH_LNG = -71.0589

MAX_PAGES = 50

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


# --------------------------------------------------
# PARSE POSH TIMESTAMPS
# --------------------------------------------------

def parse_datetime(value):

    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )

        if parsed.tzinfo is None:
            return None

        return parsed.astimezone(EASTERN)

    except (ValueError, TypeError):
        return None


# --------------------------------------------------
# FETCH INDIVIDUAL EVENT LOCATION
# --------------------------------------------------

def get_event_location(session, event_url):

    try:
        response = session.get(
            event_url,
            timeout=20
        )

        response.raise_for_status()

        html = response.text.replace('\\"', '"')

        address_match = re.search(
            r'"venueAddress"\s*:\s*"([^"]+)"',
            html
        )

        coordinates_match = re.search(
            r'"lat"\s*:\s*(-?\d+(?:\.\d+)?)\s*,\s*'
            r'"lng"\s*:\s*(-?\d+(?:\.\d+)?)',
            html
        )

        address = (
            address_match.group(1)
            if address_match
            else None
        )

        latitude = None
        longitude = None

        if coordinates_match:
            latitude = float(coordinates_match.group(1))
            longitude = float(coordinates_match.group(2))

        # Classify how accurately we know the event's location.
        location_precision = "unknown"

        if address:
            address_lower = address.lower().strip()

            hidden_phrases = [
                "revealed after",
                "location will be",
                "to be announced",
                "tba",
                "secret location",
                "undisclosed",
            ]

            if any(phrase in address_lower for phrase in hidden_phrases):
                location_precision = "hidden"

            elif re.match(r"^\d+\s+\S+", address.strip()):
                location_precision = "street"

            else:
                location_precision = "city"

        return {
            "address": address,
            "latitude": latitude,
            "longitude": longitude,
            "location_precision": location_precision
        }

    except requests.RequestException:
        return {
            "address": None,
            "latitude": None,
            "longitude": None,
            "location_precision": "unknown"
        }


# --------------------------------------------------
# COLLECT POSH EVENTS
# --------------------------------------------------

def collect_posh_events():

    now = datetime.now(EASTERN)
    cutoff = now + timedelta(days=DAYS_AHEAD)

    session = requests.Session()
    session.headers.update(HEADERS)

    events = []
    seen_ids = set()
    seen_cursors = set()

    cursor = None

    for page in range(1, MAX_PAGES + 1):

        params = {
            "lat": SEARCH_LAT,
            "lng": SEARCH_LNG,
            "timezone": "America/New_York",
            "when": "This Month"
        }

        if cursor is not None:
            params["cursor"] = cursor

        try:
            response = session.get(
                API_URL,
                params=params,
                timeout=20
            )

            response.raise_for_status()
            data = response.json()

        except (requests.RequestException, ValueError) as error:
            print(f"POSH page {page} error: {error}")
            break

        page_events = data.get("events", [])

        print(
            f"POSH page {page}: {len(page_events)} records"
        )

        for item in page_events:

            event_id = item.get("id")

            if not event_id or event_id in seen_ids:
                continue

            seen_ids.add(event_id)

            start = parse_datetime(
                item.get("startDate")
            )

            if start is None:
                continue

            if not now <= start < cutoff:
                continue

            title = item.get("title")

            slug = item.get("url")

            if not title or not slug:
                continue

            event_url = (
                slug
                if slug.startswith("http")
                else EVENT_URL + slug.lstrip("/")
            )

            end = parse_datetime(
                item.get("endDate")
            )

            location = get_event_location(
                session,
                event_url
            )

            events.append({
                "title": title,
                "start": start.isoformat(),
                "end": end.isoformat() if end else None,
                "venue": item.get("venueName"),
                "address": location["address"],
                "latitude": location["latitude"],
                "longitude": location["longitude"],
                "location_precision": location["location_precision"],
                "source_name": "POSH",
                "source_id": event_id,
                "url": event_url,
                "image_url": item.get("imageUrl"),
                "min_ticket_price": item.get("minTicketPrice")
            })

            # Avoid making requests too quickly.
            time.sleep(0.1)

        next_cursor = data.get("nextCursor")

        if (
            not page_events
            or next_cursor is None
            or next_cursor in seen_cursors
        ):
            break

        seen_cursors.add(next_cursor)
        cursor = next_cursor

    events.sort(
        key=lambda event: event["start"]
    )

    return events


# --------------------------------------------------
# STANDALONE TEST
# --------------------------------------------------

if __name__ == "__main__":

    results = collect_posh_events()

    print()
    print("------------------------------")
    print("POSH events:", len(results))

    precise = sum(
        event["location_precision"] == "street"
        for event in results
    )

    city_only = sum(
        event["location_precision"] == "city"
        for event in results
    )

    unknown = sum(
        event["location_precision"] == "unknown"
        for event in results
    )

    hidden = sum(
        event["location_precision"] == "hidden"
        for event in results
    )

    print("Street-level locations:", precise)
    print("City-level locations:", city_only)
    print("Unknown locations:", unknown)
    print("Hidden locations:", hidden)
    print("------------------------------")

    for event in results[:15]:
        print(
            event["start"],
            "|",
            event["title"],
            "|",
            event["address"]
        )
