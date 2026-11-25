import json
import requests


# --------------------------------------------------
# THE EVENTS CALENDAR API TEST
#
# We discovered that Lizard Lounge exposes:
#
# /tribe/events/v1/events
#
# Now we're going to ask that endpoint directly
# for its events and inspect the structured data.
# --------------------------------------------------


BASE_URL = "https://musicintheberkshires.com"


EVENTS_URL = (
    BASE_URL
    + "/wp-json/tribe/events/v1/events"
)


headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/154.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9"
}


print("=" * 60)
print("THE EVENTS CALENDAR API")
print("=" * 60)
print()


# --------------------------------------------------
# Request events.
#
# per_page=5 keeps this first experiment small.
# --------------------------------------------------

response = requests.get(
    EVENTS_URL,
    headers=headers,
    params={
        "per_page": 5
    },
    timeout=20
)


print(
    "Status:",
    response.status_code
)

print(
    "Final URL:",
    response.url
)

print(
    "Characters received:",
    len(response.text)
)

print()


if response.status_code != 200:

    print(
        "Event API request failed."
    )

    print()

    print(
        response.text[:2000]
    )

    raise SystemExit


# --------------------------------------------------
# Parse JSON.
# --------------------------------------------------

try:

    data = response.json()

except ValueError:

    print(
        "Response was not valid JSON."
    )

    raise SystemExit


print("Valid JSON received.")
print()


# --------------------------------------------------
# The API should give us an "events" list.
# --------------------------------------------------

events = data.get(
    "events",
    []
)


print(
    "Events returned:",
    len(events)
)

print()


# --------------------------------------------------
# The response may also tell us how many events
# exist and how pagination works.
# --------------------------------------------------

print(
    "Total available:",
    data.get("total")
)

print(
    "Total pages:",
    data.get("total_pages")
)

print()


# --------------------------------------------------
# Inspect the first few events.
#
# We're deliberately NOT converting them into the
# Happenin' schema yet.
#
# First we want to understand exactly what this
# reusable API provides.
# --------------------------------------------------

for index, event in enumerate(
    events,
    start=1
):

    print()
    print("=" * 60)
    print(
        "EVENT",
        index
    )
    print("=" * 60)


    print(
        "ID:",
        event.get("id")
    )

    print(
        "Title:",
        event.get("title")
    )

    print(
        "URL:",
        event.get("url")
    )

    print(
        "Start:",
        event.get("start_date")
    )

    print(
        "End:",
        event.get("end_date")
    )

    print(
        "Timezone:",
        event.get("timezone")
    )

    print(
        "Cost:",
        event.get("cost")
    )


    # --------------------------------------------------
    # Venue is usually already embedded in the event.
    # --------------------------------------------------

    venue = event.get(
        "venue"
    )


    print()
    print("VENUE:")


    if isinstance(venue, dict):

        print(
            "Name:",
            venue.get("venue")
        )

        print(
            "Address:",
            venue.get("address")
        )

        print(
            "City:",
            venue.get("city")
        )

        print(
            "State:",
            venue.get("state")
        )

        print(
            "ZIP:",
            venue.get("zip")
        )

    else:

        print(venue)


    # --------------------------------------------------
    # Organizer may also be structured.
    # --------------------------------------------------

    organizer = event.get(
        "organizer"
    )


    print()
    print("ORGANIZER:")


    if isinstance(organizer, list):

        for item in organizer:

            if isinstance(item, dict):

                print(
                    item.get("organizer")
                )

    elif isinstance(organizer, dict):

        print(
            organizer.get("organizer")
        )

    else:

        print(organizer)


# --------------------------------------------------
# Finally, save ONE complete raw event so we can
# inspect every field the plugin gives us.
# --------------------------------------------------

if events:

    with open(
        "wordpress_event_sample.json",
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            events[0],
            file,
            indent=4,
            ensure_ascii=False
        )


    print()
    print("=" * 60)

    print(
        "Created wordpress_event_sample.json"
    )

    print("=" * 60)