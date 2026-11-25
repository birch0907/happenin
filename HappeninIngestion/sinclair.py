import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup


EVENTS_URL = "https://www.sinclaircambridge.com/events"

SINCLAIR_ADDRESS = "52 Church Street"
SINCLAIR_CITY = "Cambridge"
SINCLAIR_STATE = "MA"


def convert_sinclair_time(date_text, time_text):

    # Example:
    #
    # date_text = "Tue, October 6, 2026"
    # time_text = "7:00 PM"

    combined = f"{date_text} {time_text}"

    event_time = datetime.strptime(
        combined,
        "%a, %B %d, %Y %I:%M %p"
    )

    eastern = ZoneInfo("America/New_York")

    event_time = event_time.replace(
        tzinfo=eastern
    )

    return event_time.isoformat()


def collect_sinclair_events():

    # --------------------------------------------------
    # Step 1:
    # Download the main events page.
    # --------------------------------------------------

    response = requests.get(
        EVENTS_URL,
        timeout=20
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )


    # --------------------------------------------------
    # Step 2:
    # Find every unique Sinclair event-detail URL.
    # --------------------------------------------------

    event_links = soup.find_all(
        "a",
        href=lambda href:
            href
            and "/events/detail/" in href
    )

    event_urls = []

    for link in event_links:

        href = link.get("href")

        if href not in event_urls:
            event_urls.append(href)


    # --------------------------------------------------
    # Step 3:
    # Visit each detail page and extract the
    # authoritative event information.
    # --------------------------------------------------

    events = []

    for event_url in event_urls:

        response = requests.get(
            event_url,
            timeout=20
        )

        response.raise_for_status()

        event_soup = BeautifulSoup(
            response.text,
            "html.parser"
        )


        # ----------------------------------------------
        # Title
        # ----------------------------------------------

        title_element = event_soup.find("h1")

        if not title_element:
            continue

        title = title_element.get_text(
            " ",
            strip=True
        )


        # ----------------------------------------------
        # Supporting artist / guest
        # ----------------------------------------------

        support_element = event_soup.find("h4")

        support = None

        if support_element:

            support = support_element.get_text(
                " ",
                strip=True
            )


        # ----------------------------------------------
        # Date
        # ----------------------------------------------

        date_element = event_soup.find(
            "label",
            string=lambda text:
                text
                and text.strip().lower() == "date"
        )

        date_text = None

        if date_element:

            parent = date_element.parent

            # Find the value beside/under the Date label.
            value = parent.find("span")

            if value:
                date_text = value.get_text(
                    " ",
                    strip=True
                )


        # ----------------------------------------------
        # Show time
        # ----------------------------------------------

        time_label = event_soup.find(
            "label",
            class_="event_time"
        )

        show_time_text = None

        if time_label:

            time_container = time_label.parent

            value = time_container.find("span")

            if value:
                show_time_text = value.get_text(
                    " ",
                    strip=True
                )


        # ----------------------------------------------
        # Doors
        # ----------------------------------------------

        doors_element = event_soup.find(
            "span",
            class_="doors"
        )

        doors_text = None

        if doors_element:

            value = doors_element.find("span")

            if value:
                doors_text = value.get_text(
                    " ",
                    strip=True
                )


        # ----------------------------------------------
        # Age restriction
        # ----------------------------------------------

        age_element = event_soup.find(
            "span",
            class_="age_res"
        )

        ages = None

        if age_element:

            ages = age_element.get_text(
                " ",
                strip=True
            )


        # ----------------------------------------------
        # We need both a date and show time to create
        # a valid Happenin' event.
        # ----------------------------------------------

        if not date_text or not show_time_text:

            print(
                "Skipping event with missing date/time:",
                title
            )

            continue


        # ----------------------------------------------
        # Convert show time.
        # ----------------------------------------------

        start = convert_sinclair_time(
            date_text,
            show_time_text
        )


        # ----------------------------------------------
        # Convert doors time.
        # ----------------------------------------------

        doors = None

        if doors_text:

            doors = convert_sinclair_time(
                date_text,
                doors_text
            )


        # ----------------------------------------------
        # Price
        # ----------------------------------------------
        #
        # For this first collector version, we'll only
        # identify events explicitly marked Free.
        #
        # Ticket prices can be handled later.

        page_text = event_soup.get_text(
            " ",
            strip=True
        )

        price = None

        if "Free" in page_text:
            price = "Free"


        # ----------------------------------------------
        # Create the Happenin' event.
        # ----------------------------------------------

        event = {
            "title": title,
            "start": start,
            "end": None,
            "venue": "The Sinclair",
            "address": SINCLAIR_ADDRESS,
            "city": SINCLAIR_CITY,
            "state": SINCLAIR_STATE,
            "source_type": "venue_website",
            "source_name": "Sinclair",
            "source_url": event_url,
            "doors": doors,
            "support": support,
            "ages": ages,
            "price": price
        }

        events.append(event)


    return events


# --------------------------------------------------
# Allow us to test this collector directly.
# --------------------------------------------------

if __name__ == "__main__":

    print("Collecting Sinclair events...")

    events = collect_sinclair_events()

    print()
    print("Sinclair events collected:", len(events))
    print()

    for event in events[:5]:

        print("------------------------------")

        print("Title:", event["title"])
        print("Start:", event["start"])
        print("Doors:", event["doors"])
        print("Support:", event["support"])
        print("Ages:", event["ages"])
        print("Price:", event["price"])
        print("URL:", event["source_url"])