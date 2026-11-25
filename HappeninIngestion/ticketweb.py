import json
import requests
from bs4 import BeautifulSoup


# --------------------------------------------------
# TicketWeb Session Test
#
# Goal:
# 1. Create a persistent browser-like session.
# 2. Tell TicketWeb our location is Boston, MA.
# 3. Request the normal events page using that SAME
#    session.
# 4. Inspect the JSON-LD events TicketWeb returns.
#
# If TicketWeb stores the selected location in a
# cookie/session, the returned events should now be
# Boston-area events instead of Miami/Louisiana/etc.
# --------------------------------------------------


BASE_URL = "https://www.ticketweb.com"


headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/154.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9"
}


# --------------------------------------------------
# Create a persistent session.
# --------------------------------------------------

session = requests.Session()

session.headers.update(headers)


# --------------------------------------------------
# STEP 1:
# Tell TicketWeb that we selected Boston, MA.
# --------------------------------------------------

print("Setting TicketWeb location to Boston...")
print()


location_response = session.get(
    BASE_URL + "/data/autogeolocation",
    params={
        "city": "boston",
        "state": "ma"
    },
    timeout=20
)

location_response.raise_for_status()


print(
    "Location status:",
    location_response.status_code
)

print(
    "Location response:"
)

print(
    location_response.text
)

print()


# --------------------------------------------------
# Show cookies currently stored by the session.
#
# This is especially important for this experiment.
# If selecting Boston creates a cookie, we want to
# know about it.
# --------------------------------------------------

print("========== SESSION COOKIES ==========")

if len(session.cookies) == 0:

    print("No cookies stored.")

else:

    for cookie in session.cookies:

        print(
            cookie.name,
            "=",
            cookie.value
        )

print()


# --------------------------------------------------
# STEP 2:
# Using the SAME session, request TicketWeb's
# normal events page.
# --------------------------------------------------

print("Requesting TicketWeb events...")
print()


events_response = session.get(
    BASE_URL + "/events",
    timeout=20
)

events_response.raise_for_status()


print(
    "Events status:",
    events_response.status_code
)

print(
    "Final URL:",
    events_response.url
)

print(
    "Characters received:",
    len(events_response.text)
)

print()


# --------------------------------------------------
# STEP 3:
# Extract TicketWeb's JSON-LD structured events.
# --------------------------------------------------

soup = BeautifulSoup(
    events_response.text,
    "html.parser"
)


json_ld_scripts = soup.find_all(
    "script",
    type="application/ld+json"
)


print(
    "JSON-LD blocks:",
    len(json_ld_scripts)
)

print()


events = []


for script in json_ld_scripts:

    try:

        data = json.loads(
            script.string
        )

    except (json.JSONDecodeError, TypeError):

        continue


    if isinstance(data, dict):

        items = [data]

    elif isinstance(data, list):

        items = data

    else:

        continue


    for item in items:

        if not isinstance(item, dict):
            continue


        event_type = item.get("@type")


        if event_type not in [
            "Event",
            "MusicEvent"
        ]:
            continue


        location = item.get(
            "location",
            {}
        )


        events.append(
            {
                "title": item.get("name"),
                "start": item.get("startDate"),
                "venue": location.get("name"),
                "address": location.get("address"),
                "source_url": item.get("url")
            }
        )


# --------------------------------------------------
# STEP 4:
# Show the results.
# --------------------------------------------------

print(
    "Structured events found:",
    len(events)
)

print()


for event in events:

    print("------------------------------")

    print(
        "Title:",
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
        "Address:",
        event["address"]
    )

    print(
        "URL:",
        event["source_url"]
    )