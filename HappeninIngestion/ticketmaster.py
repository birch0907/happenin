import os
import requests

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


# --------------------------------------------------
# HAPPENIN' — TICKETMASTER COLLECTOR
#
# Collects upcoming Ticketmaster events near Boston
# and converts them into the Happenin' event schema.
#
# This is now a real collector module, like:
#
#     lamplighter.py
#     lilypad.py
#     sinclair.py
#
# The collector:
#
#     1. Searches geographically
#     2. Searches a limited future time window
#     3. Handles pagination
#     4. Rejects cancelled events
#     5. Rejects obvious sports events
#     6. Normalizes Ticketmaster data
#     7. Returns Happenin' event dictionaries
#
# It DOES NOT write events.json.
#
# ingest.py will eventually do that.
# --------------------------------------------------


API_URL = (
    "https://app.ticketmaster.com/"
    "discovery/v2/events.json"
)


EASTERN = ZoneInfo(
    "America/New_York"
)


# --------------------------------------------------
# Geographic coverage
#
# Same geographic experiment that gave us strong
# Boston / Cambridge / Somerville coverage.
# --------------------------------------------------

CENTER_LATITUDE = 42.3601
CENTER_LONGITUDE = -71.0589

RADIUS_MILES = 10


# --------------------------------------------------
# How far into the future should this collector look?
#
# For now:
#
#     today -> 14 days from now
#
# Later this can become configuration rather than
# being hard-coded here.
# --------------------------------------------------

DAYS_AHEAD = 14


# --------------------------------------------------
# Ticketmaster page size
#
# 200 keeps the number of API requests low.
# --------------------------------------------------

PAGE_SIZE = 200


# --------------------------------------------------
# Convert Ticketmaster's UTC dateTime into our
# Eastern ISO timestamp.
#
# Example:
#
# Ticketmaster:
#     2026-10-07T00:00:00Z
#
# Happenin':
#     2026-10-06T20:00:00-04:00
# --------------------------------------------------

def convert_ticketmaster_time(date_time):

    if not date_time:
        return None


    try:

        utc_time = datetime.fromisoformat(
            date_time.replace(
                "Z",
                "+00:00"
            )
        )

        eastern_time = utc_time.astimezone(
            EASTERN
        )

        return eastern_time.isoformat()


    except ValueError:

        return None


# --------------------------------------------------
# Pull the primary Ticketmaster classification.
#
# We preserve Ticketmaster's taxonomy rather than
# trying to turn it into Happenin' categories yet.
# --------------------------------------------------

def get_classification(event):

    classifications = event.get(
        "classifications",
        []
    )


    if not classifications:

        return (
            None,
            None,
            None
        )


    # Prefer Ticketmaster's primary classification
    # when one is explicitly marked primary.

    classification = classifications[0]


    for candidate in classifications:

        if candidate.get("primary") is True:

            classification = candidate
            break


    segment = (
        classification
        .get("segment", {})
        .get("name")
    )


    genre = (
        classification
        .get("genre", {})
        .get("name")
    )


    subgenre = (
        classification
        .get("subGenre", {})
        .get("name")
    )


    return (
        segment,
        genre,
        subgenre
    )


# --------------------------------------------------
# Decide whether an event obviously does NOT belong
# in Happenin'.
#
# IMPORTANT:
#
# We're deliberately keeping this conservative.
#
# We know useful nightlife events sometimes appear
# under:
#
#     Miscellaneous
#     Undefined
#
# So those remain.
#
# For now the only whole segment we reject is Sports.
# --------------------------------------------------

def should_keep_event(
    event,
    segment
):

    dates = event.get(
        "dates",
        {}
    )


    status = (
        dates
        .get("status", {})
        .get("code")
    )


    # Cancelled events should never appear.

    if status == "cancelled":

        return False


    # Happenin' is not a sports schedule.

    if segment == "Sports":

        return False


    return True


# --------------------------------------------------
# Convert one Ticketmaster event into the Happenin'
# schema.
# --------------------------------------------------

def normalize_ticketmaster_event(event):

    title = (
        event.get("name")
        or ""
    ).strip()


    if not title:

        return None


    # --------------------------------------------------
    # Date / time
    # --------------------------------------------------

    dates = event.get(
        "dates",
        {}
    )


    start_data = dates.get(
        "start",
        {}
    )


    start = convert_ticketmaster_time(
        start_data.get("dateTime")
    )


    # We currently require an actual known start time.
    #
    # TBA/TBD events are excluded from the API query,
    # but this protects us from incomplete records.

    if not start:

        return None


    # Ticketmaster does not reliably provide a useful
    # event end time.
    #
    # Never invent one.

    end = None


    # --------------------------------------------------
    # Classification
    # --------------------------------------------------

    (
        segment,
        genre,
        subgenre
    ) = get_classification(
        event
    )


    if not should_keep_event(
        event,
        segment
    ):

        return None


    # --------------------------------------------------
    # Venue
    # --------------------------------------------------

    venues = (
        event
        .get("_embedded", {})
        .get("venues", [])
    )


    if venues:

        venue_data = venues[0]

    else:

        venue_data = {}


    venue = (
        venue_data.get("name")
        or ""
    ).strip()


    address = (
        venue_data
        .get("address", {})
        .get("line1")
    )


    if address:

        address = address.strip()


    city = (
        venue_data
        .get("city", {})
        .get("name")
    )


    if city:

        city = city.strip()


    state = (
        venue_data
        .get("state", {})
        .get("stateCode")
    )


    if state:

        state = state.strip()


    postal_code = (
        venue_data.get("postalCode")
    )


    if postal_code:

        postal_code = postal_code.strip()


    # --------------------------------------------------
    # Coordinates
    #
    # Very valuable later when events become map pins.
    # --------------------------------------------------

    location = venue_data.get(
        "location",
        {}
    )


    latitude = location.get(
        "latitude"
    )


    longitude = location.get(
        "longitude"
    )


    # Ticketmaster normally provides these as strings.
    #
    # Convert to floats so Happenin' stores coordinates
    # as numbers.

    try:

        latitude = (
            float(latitude)
            if latitude is not None
            else None
        )

    except (
        ValueError,
        TypeError
    ):

        latitude = None


    try:

        longitude = (
            float(longitude)
            if longitude is not None
            else None
        )

    except (
        ValueError,
        TypeError
    ):

        longitude = None


    # --------------------------------------------------
    # Attractions
    #
    # These may include the headliner and supporting
    # artists.
    # --------------------------------------------------

    attractions = (
        event
        .get("_embedded", {})
        .get("attractions", [])
    )


    attraction_names = []


    for attraction in attractions:

        name = attraction.get(
            "name"
        )


        if name:

            name = name.strip()


            if (
                name
                and
                name not in attraction_names
            ):

                attraction_names.append(
                    name
                )


    # --------------------------------------------------
    # Ticketmaster source information
    # --------------------------------------------------

    source_id = event.get(
        "id"
    )


    source_url = event.get(
        "url"
    )


    # --------------------------------------------------
    # Ticket pricing (when supplied by Ticketmaster)
    # --------------------------------------------------

    price_ranges = event.get("priceRanges") or []
    price = None
    if price_ranges and isinstance(price_ranges[0], dict):
        lo = price_ranges[0].get("min")
        hi = price_ranges[0].get("max")
        if isinstance(lo, (int, float)) and isinstance(hi, (int, float)):
            if lo == 0 and hi == 0:
                price = "Free"
            elif round(lo) == round(hi):
                price = f"${int(round(lo))}"
            else:
                price = f"${int(round(lo))}–${int(round(hi))}"
        elif isinstance(lo, (int, float)):
            price = "Free" if lo == 0 else f"${int(round(lo))}+"

    admission_type = "free" if price == "Free" else "ticketed"

    # --------------------------------------------------
    # Normalized Happenin' event
    # --------------------------------------------------

    return {

        "title": title,

        "start": start,
        "end": end,

        "venue": venue or None,
        "address": address,
        "city": city,
        "state": state,
        "postal_code": postal_code,

        "latitude": latitude,
        "longitude": longitude,

        "segment": segment,
        "genre": genre,
        "subgenre": subgenre,

        "attractions": attraction_names,
        "price": price,
        "admission_type": admission_type,

        "source_type": "ticketing_platform",
        "source_name": "Ticketmaster",
        "source_id": source_id,
        "source_url": source_url,
    }


# --------------------------------------------------
# Main collector
# --------------------------------------------------

def collect_ticketmaster_events(
    center_lat=CENTER_LATITUDE,
    center_lng=CENTER_LONGITUDE,
    radius_miles=RADIUS_MILES,
    region="boston",
):

    api_key = os.getenv(
        "TICKETMASTER_API_KEY"
    )


    if not api_key:

        print(
            "Ticketmaster skipped: "
            "TICKETMASTER_API_KEY not found."
        )

        return []


    # --------------------------------------------------
    # Build our search window.
    #
    # Ticketmaster expects UTC for startDateTime and
    # endDateTime.
    # --------------------------------------------------

    now = datetime.now(
        timezone.utc
    )


    end_time = (
        now
        + timedelta(
            days=DAYS_AHEAD
        )
    )


    start_string = (
        now
        .replace(microsecond=0)
        .isoformat()
        .replace(
            "+00:00",
            "Z"
        )
    )


    end_string = (
        end_time
        .replace(microsecond=0)
        .isoformat()
        .replace(
            "+00:00",
            "Z"
        )
    )


    events = []


    page_number = 0


    print(
        "Ticketmaster window:",
        start_string,
        "to",
        end_string
    )


    # --------------------------------------------------
    # Pagination
    # --------------------------------------------------

    while True:

        params = {

            "apikey": api_key,

            "latlong": (
                f"{center_lat},"
                f"{center_lng}"
            ),

            "radius": radius_miles,
            "unit": "miles",

            "startDateTime": start_string,
            "endDateTime": end_string,

            "includeTBA": "no",
            "includeTBD": "no",
            "includeTest": "no",

            "size": PAGE_SIZE,
            "page": page_number,

            "sort": "date,asc",
        }


        try:

            response = requests.get(
                API_URL,
                params=params,
                timeout=30
            )

        except requests.RequestException as error:

            print(
                "Ticketmaster connection error:"
            )

            print(error)

            break


        if response.status_code != 200:

            print(
                "Ticketmaster request failed:",
                response.status_code
            )

            print(
                response.text[:1000]
            )

            break


        try:

            data = response.json()

        except ValueError:

            print(
                "Ticketmaster returned invalid JSON."
            )

            break


        raw_events = (
            data
            .get("_embedded", {})
            .get("events", [])
        )


        print(
            f"Ticketmaster page "
            f"{page_number + 1}: "
            f"{len(raw_events)} raw events"
        )


        # --------------------------------------------------
        # Normalize this page.
        # --------------------------------------------------

        for raw_event in raw_events:

            event = normalize_ticketmaster_event(
                raw_event
            )


            if event is not None:
                event["region"] = region
                events.append(
                    event
                )


        # --------------------------------------------------
        # Pagination information
        # --------------------------------------------------

        page_info = data.get(
            "page",
            {}
        )


        total_pages = page_info.get(
            "totalPages",
            0
        )


        # We're finished if:
        #
        #     there are no more pages
        #
        # OR
        #
        #     the next page would cross Ticketmaster's
        #     deep-paging limit.
        # --------------------------------------------------

        page_number += 1


        if page_number >= total_pages:

            break


        if (
            page_number
            * PAGE_SIZE
            >= 1000
        ):

            print(
                "Ticketmaster paging stopped "
                "at API deep-paging limit."
            )

            break


    # --------------------------------------------------
    # Sort normalized results.
    # --------------------------------------------------

    events.sort(
        key=lambda event:
        event["start"]
    )


    return events


# --------------------------------------------------
# Direct test
#
# This section only runs when we execute:
#
#     python ticketmaster.py
#
# It will NOT run later when ingest.py imports the
# collector.
# --------------------------------------------------

if __name__ == "__main__":

    ticketmaster_events = (
        collect_ticketmaster_events()
    )


    print()
    print("=" * 70)
    print("TICKETMASTER COLLECTOR RESULT")
    print("=" * 70)

    print()
    print(
        "Normalized events:",
        len(ticketmaster_events)
    )


    # --------------------------------------------------
    # Print the first 20 normalized events so we can
    # inspect the real Happenin' records.
    # --------------------------------------------------

    for event in (
        ticketmaster_events[:20]
    ):

        print()
        print("-" * 70)

        print(
            event["title"]
        )

        print(
            "Start:",
            event["start"]
        )

        print(
            "Venue:",
            event["venue"]
        )

        print(
            "Location:",
            event["city"],
            event["state"]
        )

        print(
            "Classification:",
            event["segment"],
            "->",
            event["genre"],
            "->",
            event["subgenre"]
        )

        print(
            "Coordinates:",
            event["latitude"],
            event["longitude"]
        )

        print(
            "Attractions:",
            event["attractions"]
        )

        print(
            "Source ID:",
            event["source_id"]
        )


    print()
    print("=" * 70)
    print("TEST COMPLETE")
    print("=" * 70)