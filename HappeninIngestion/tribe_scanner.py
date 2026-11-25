import requests


# --------------------------------------------------
# HAPPENIN' — TRIBE / THE EVENTS CALENDAR SCANNER
#
# Purpose:
#
# Given a bunch of venue websites, determine whether
# they expose The Events Calendar REST API.
#
# We are NOT collecting events yet.
#
# We're measuring how reusable this source family
# actually is.
# --------------------------------------------------


SITES = {
    "Lizard Lounge":
        "https://lizardloungeclub.com",

    "Club Passim":
        "https://www.passim.org",

    "Cantab Lounge":
        "https://www.thecantablounge.com",

    "Middle East":
        "https://www.mideastoffers.com",

    "Sonia":
        "https://www.soniacentralsq.com",

    "Phoenix Landing":
        "https://www.thephoenixlanding.com",

    "ManRay":
        "https://www.manrayclub.com",

    "Middlesex":
        "https://www.middlesexlounge.us",
}


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/154.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
}


# --------------------------------------------------
# Check one website.
# --------------------------------------------------


def scan_site(name, base_url):

    api_url = (
        base_url.rstrip("/")
        + "/wp-json/"
    )

    print()
    print("=" * 60)
    print(name)
    print("=" * 60)

    print(
        "Website:",
        base_url
    )

    try:

        response = requests.get(
            api_url,
            headers=HEADERS,
            timeout=15
        )

    except requests.RequestException as error:

        print(
            "RESULT: CONNECTION ERROR"
        )

        print(
            "Details:",
            error
        )

        return


    print(
        "WordPress API status:",
        response.status_code
    )


    # --------------------------------------------------
    # If /wp-json/ doesn't exist, it probably isn't
    # an exposed WordPress REST API.
    # --------------------------------------------------

    if response.status_code != 200:

        print(
            "RESULT: NO PUBLIC WORDPRESS API"
        )

        return


    # --------------------------------------------------
    # Make sure the response really is JSON.
    # --------------------------------------------------

    try:

        api_data = response.json()

    except ValueError:

        print(
            "RESULT: /wp-json/ DID NOT RETURN JSON"
        )

        return


    namespaces = api_data.get(
        "namespaces",
        []
    )


    # --------------------------------------------------
    # Detect Tribe / The Events Calendar.
    # --------------------------------------------------

    tribe_found = (
        "tribe/events/v1"
        in namespaces
    )


    if not tribe_found:

        print(
            "RESULT: WORDPRESS, BUT NO TRIBE EVENTS API"
        )

        return


    print(
        "TRIBE API: FOUND"
    )


    # --------------------------------------------------
    # Now test the actual event endpoint.
    #
    # This catches situations where the namespace is
    # advertised but the events endpoint is disabled.
    # --------------------------------------------------

    events_url = (
        base_url.rstrip("/")
        + "/wp-json/tribe/events/v1/events"
    )


    try:

        event_response = requests.get(
            events_url,
            headers=HEADERS,
            params={
                "per_page": 1
            },
            timeout=15
        )

    except requests.RequestException as error:

        print(
            "EVENT API: CONNECTION ERROR"
        )

        print(
            "Details:",
            error
        )

        return


    print(
        "Event endpoint status:",
        event_response.status_code
    )


    if event_response.status_code != 200:

        print(
            "RESULT: TRIBE DETECTED, EVENTS NOT ACCESSIBLE"
        )

        return


    try:

        event_data = (
            event_response.json()
        )

    except ValueError:

        print(
            "RESULT: EVENT ENDPOINT DID NOT RETURN JSON"
        )

        return


    events = event_data.get(
        "events",
        []
    )


    total = event_data.get(
        "total"
    )


    print(
        "Total events reported:",
        total
    )


    # --------------------------------------------------
    # Show one title as additional proof that we're
    # actually receiving event records.
    # --------------------------------------------------

    if events:

        print(
            "Sample event:",
            events[0].get("title")
        )


    print(
        "RESULT: TRIBE COLLECTOR COMPATIBLE ✓"
    )


# --------------------------------------------------
# Run every website through exactly the same test.
# --------------------------------------------------


print()
print("=" * 60)
print("HAPPENIN' SOURCE-FAMILY SCANNER")
print("=" * 60)


for name, url in SITES.items():

    scan_site(
        name,
        url
    )


print()
print("=" * 60)
print("SCAN COMPLETE")
print("=" * 60)