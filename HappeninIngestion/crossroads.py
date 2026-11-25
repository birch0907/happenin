import json
import requests
from bs4 import BeautifulSoup


# --------------------------------------------------
# HAPPENIN' — CROSSROADS EXPERIMENT
#
# Goal:
#
# Determine how Crossroads stores its event inventory.
#
# The public Crossroads events page contains events
# for MULTIPLE Boston-area venues.
#
# Before building a collector, we're checking:
#
# 1. Can Python access the page?
# 2. Does it contain JSON-LD?
# 3. Are event detail URLs exposed?
# 4. Are venue names present in the returned HTML?
#
# We are NOT parsing events yet.
# --------------------------------------------------


URL = "https://crossroadspresents.com/pages/events"


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/154.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


print()
print("=" * 60)
print("CROSSROADS SOURCE EXPERIMENT")
print("=" * 60)
print()


# --------------------------------------------------
# Download the public events page.
# --------------------------------------------------

try:

    response = requests.get(
        URL,
        headers=HEADERS,
        timeout=20
    )

except requests.RequestException as error:

    print("CONNECTION ERROR")
    print(error)

    raise SystemExit


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

    print("Crossroads request failed.")

    print()
    print("First 1000 characters:")
    print(response.text[:1000])

    raise SystemExit


soup = BeautifulSoup(
    response.text,
    "html.parser"
)


# --------------------------------------------------
# TEST 1
#
# Look for JSON-LD.
#
# If Crossroads gives us structured Event objects,
# that's potentially the easiest collector.
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


        event_type = item.get(
            "@type"
        )


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
# TEST 2
#
# Find links that appear to lead to Crossroads
# event-detail pages.
#
# Current public detail pages use:
#
# /pages/more-info-event
#
# often with an eventid in the query string.
# --------------------------------------------------

event_links = []


for link in soup.find_all(
    "a",
    href=True
):

    href = link["href"]


    if "more-info-event" not in href:
        continue


    if href.startswith("/"):

        href = (
            "https://crossroadspresents.com"
            + href
        )


    if href not in event_links:

        event_links.append(
            href
        )


print(
    "Unique event-detail links:",
    len(event_links)
)

print()


for index, event_url in enumerate(
    event_links[:10],
    start=1
):

    print(
        f"{index}. {event_url}"
    )


# --------------------------------------------------
# TEST 3
#
# Search the returned HTML/text for venue names.
#
# If multiple venues appear in one request, that's
# the scalability result we're looking for.
# --------------------------------------------------

page_text = soup.get_text(
    " ",
    strip=True
)


VENUE_NAMES = [
    "Paradise Rock Club",
    "Brighton Music Hall",
    "Crystal Ballroom",
    "Somerville Theatre",
    "House of Blues",
    "Big Night Live",
    "MGM Music Hall",
]


print()
print("=" * 60)
print("VENUE DETECTION")
print("=" * 60)
print()


venues_found = []


for venue_name in VENUE_NAMES:

    found = (
        venue_name.lower()
        in page_text.lower()
    )


    print(
        f"{venue_name}:",
        found
    )


    if found:

        venues_found.append(
            venue_name
        )


print()

print(
    "Venue names detected:",
    len(venues_found)
)

print(
    "Visible text length:",
    len(page_text)
)


# --------------------------------------------------
# TEST 4
#
# Look for potentially useful embedded scripts.
#
# Modern websites often put event data into a script
# even when they don't use JSON-LD.
#
# Rather than dumping hundreds of thousands of
# characters, we'll identify scripts containing
# words that look relevant.
# --------------------------------------------------

interesting_scripts = []


for index, script in enumerate(
    soup.find_all("script")
):

    script_text = (
        script.string
        or script.get_text()
        or ""
    )


    lower_text = (
        script_text.lower()
    )


    if (
        "eventid" in lower_text
        or "event_id" in lower_text
        or "venueid" in lower_text
        or "ticketmaster" in lower_text
    ):

        interesting_scripts.append(
            (
                index,
                script_text
            )
        )


print()
print(
    "Potential event-data scripts:",
    len(interesting_scripts)
)


# --------------------------------------------------
# Save small samples of interesting scripts.
#
# This gives us something to inspect without filling
# the terminal with massive JavaScript blobs.
# --------------------------------------------------

if interesting_scripts:

    with open(
        "crossroads_script_samples.txt",
        "w",
        encoding="utf-8"
    ) as file:

        for index, script_text in interesting_scripts:

            file.write(
                "=" * 70
            )

            file.write(
                f"\nSCRIPT {index}\n"
            )

            file.write(
                "=" * 70
            )

            file.write("\n")

            file.write(
                script_text[:10000]
            )

            file.write(
                "\n\n"
            )


    print(
        "Created crossroads_script_samples.txt"
    )


print()
print("=" * 60)
print("EXPERIMENT COMPLETE")
print("=" * 60)