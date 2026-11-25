
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup


TIMEZONE = ZoneInfo("America/New_York")
CALENDAR_URL = "https://calendar.ploughandstars.com/events/calendar"

VENUE = "The Plough and Stars"
ADDRESS = "912 Massachusetts Avenue, Cambridge, MA 02139"


def parse_time_range(value):
    """
    Convert calendar times such as:
        10p    -> 10:00 PM
        10pm   -> 10:00 PM
        7p     -> 7:00 PM
        4-6p   -> 4:00 PM to 6:00 PM
        7-9p   -> 7:00 PM to 9:00 PM

    Returns (start_hour, start_minute, end_hour, end_minute).
    End values are None when no end time is provided.
    """
    value = value.strip().lower().replace(" ", "").replace(".", "")

    match = re.fullmatch(
        r"(\d{1,2})(?::(\d{2}))?"
        r"(?:-(\d{1,2})(?::(\d{2}))?)?"
        r"(am|pm|a|p)",
        value,
    )

    if not match:
        return None

    start_hour = int(match.group(1))
    start_minute = int(match.group(2) or 0)
    end_hour = int(match.group(3)) if match.group(3) else None
    end_minute = int(match.group(4) or 0) if end_hour is not None else None

    suffix = match.group(5)
    is_pm = suffix.startswith("p")

    def to_24_hour(hour, pm):
        if not 1 <= hour <= 12:
            raise ValueError("Invalid hour")
        return hour % 12 + (12 if pm else 0)

    try:
        start_hour_24 = to_24_hour(start_hour, is_pm)

        if end_hour is None:
            return start_hour_24, start_minute, None, None

        end_hour_24 = to_24_hour(end_hour, is_pm)

        # If a range ends at an earlier clock hour,
        # assume it crosses noon or midnight.
        if end_hour_24 < start_hour_24:
            end_hour_24 = to_24_hour(end_hour, not is_pm)

        return start_hour_24, start_minute, end_hour_24, end_minute

    except ValueError:
        return None


def collect_plough_events():
    now = datetime.now(TIMEZONE)
    cutoff = now + timedelta(days=14)

    months = {
        (now.year, now.month),
        (cutoff.year, cutoff.month),
    }

    events = []
    seen = set()

    for year, month in sorted(months):
        try:
            response = requests.get(
                CALENDAR_URL,
                params={"month": month, "year": year},
                timeout=20,
            )
            response.raise_for_status()

        except requests.RequestException as error:
            print(f"Plough calendar error ({year}-{month:02d}): {error}")
            continue

        soup = BeautifulSoup(response.text, "html.parser")

        for day in soup.select("div.day[id]"):
            date_text = day.get("id", "")

            try:
                event_date = datetime.strptime(date_text, "%Y%m%d").date()
            except ValueError:
                continue

            for row in day.select("div.row"):
                time_element = row.select_one(".flex_item_left")
                event_element = row.select_one(".event")

                if not time_element or not event_element:
                    continue

                time_text = time_element.get_text(" ", strip=True)
                title = event_element.get_text(" ", strip=True)

                if not title:
                    continue

                parsed = parse_time_range(time_text)

                if parsed is None:
                    print(f"Plough: unrecognized time '{time_text}' for {title}")
                    continue

                start_hour, start_minute, end_hour, end_minute = parsed

                start = datetime(
                    event_date.year,
                    event_date.month,
                    event_date.day,
                    start_hour,
                    start_minute,
                    tzinfo=TIMEZONE,
                )

                if not now <= start <= cutoff:
                    continue

                end = None

                if end_hour is not None:
                    end = datetime(
                        event_date.year,
                        event_date.month,
                        event_date.day,
                        end_hour,
                        end_minute,
                        tzinfo=TIMEZONE,
                    )

                    if end <= start:
                        end += timedelta(days=1)

                link_element = event_element.select_one("a[href]")
                event_url = (
                    link_element.get("href")
                    if link_element
                    else response.url
                )

                key = (title.casefold(), start.isoformat())

                if key in seen:
                    continue

                seen.add(key)

                events.append({
                    "title": title,
                    "start": start.isoformat(),
                    "end": end.isoformat() if end else None,
                    "venue": VENUE,
                    "address": ADDRESS,
                    "source_name": VENUE,
                    "url": event_url,
                })

    events.sort(key=lambda event: event["start"])
    return events


if __name__ == "__main__":
    results = collect_plough_events()

    print(f"\nPlough and Stars events: {len(results)}\n")

    for event in results:
        print(
            event["start"],
            "|",
            event["title"],
            "| End:",
            event["end"],
        )
