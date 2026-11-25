import json
import requests
from bs4 import BeautifulSoup


# --------------------------------------------------
# AXS EXPERIMENT
#
# We're testing whether two completely different
# venues can be read using the SAME code.
#
# Roadrunner:
# https://www.axs.com/venues/128223/...
#
# The Sinclair:
# https://www.axs.com/venues/124878/...
#
# We are NOT building the final collector yet.
# First we want to see what structured information
# AXS gives us.
# --------------------------------------------------


VENUES = {
    "Roadrunner": (
        "https://www.axs.com/venues/128223/"
        "roadrunner-boston-tickets"
    ),

    "The Sinclair": (
        "https://www.axs.com/venues/124878/"
        "the-sinclair-cambridge-tickets"
    )
}


headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/154.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9"
}


# --------------------------------------------------
# Inspect each venue using exactly the same code.
# --------------------------------------------------

for venue_name, url in VENUES.items():

    print()
    print("=" * 60)
    print(venue_name)
    print("=" * 60)
    print()


    response = requests.get(
        url,
        headers=headers,
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
            "AXS did not allow this request."
        )

        continue


    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )


    # --------------------------------------------------
    # TEST 1:
    # Look for JSON-LD.
    # --------------------------------------------------

    json_ld_scripts = soup.find_all(
        "script",
        type="application/ld+json"
    )


    print(
        "JSON-LD blocks:",
        len(json_ld_scripts)
    )


    structured_events = []


    for script in json_ld_scripts:

        try:

            data = json.loads(
                script.string
            )

        except (
            json.JSONDecodeError,
            TypeError
        ):

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


            if event_type in [
                "Event",
                "MusicEvent"
            ]:

                structured_events.append(
                    item
                )


    print(
        "Structured Event objects:",
        len(structured_events)
    )

    print()


    # --------------------------------------------------
    # TEST 2:
    # Find links that look like AXS event pages.
    #
    # AXS event URLs use:
    #
    # /events/<event ID>/...
    #
    # We're deduplicating because the same event may
    # appear in the HTML more than once.
    # --------------------------------------------------

    event_links = []


    for link in soup.find_all(
        "a",
        href=True
    ):

        href = link["href"]


        if "/events/" not in href:
            continue


        if href.startswith("/"):

            href = (
                "https://www.axs.com"
                + href
            )


        # Strip query-string variations so that:
        #
        # event?skin=x
        # event?skin=y
        #
        # don't look like two separate events.

        clean_url = href.split("?")[0]


        if clean_url not in event_links:

            event_links.append(
                clean_url
            )


    print(
        "Unique /events/ links:",
        len(event_links)
    )

    print()


    # --------------------------------------------------
    # Show the first 10 event URLs.
    # --------------------------------------------------

    for index, event_url in enumerate(
        event_links[:10],
        start=1
    ):

        print(
            f"{index}. {event_url}"
        )


    # --------------------------------------------------
    # TEST 3:
    # Search the raw page for some basic terms.
    #
    # This tells us whether event information exists
    # directly in the HTML even if JSON-LD isn't used.
    # --------------------------------------------------

    page_text = soup.get_text(
        " ",
        strip=True
    )


    print()
    print(
        "Contains 'All Events':",
        "All Events" in page_text
    )

    print(
        "Contains venue name:",
        venue_name.lower()
        in page_text.lower()
    )

    print(
        "Visible text length:",
        len(page_text)
    )oyt