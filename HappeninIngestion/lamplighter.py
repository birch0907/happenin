import requests
from datetime import datetime, timedelta
from urllib.parse import urljoin
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup

BASE_URL = "https://lamplighterbrewing.com"
EVENTS_URL = f"{BASE_URL}/collections/events"
EASTERN = ZoneInfo("America/New_York")


def normalize_time(time_text):
    time_text = time_text.strip().lower()
    time_text = time_text.replace("am", " am").replace("pm", " pm")
    time_text = " ".join(time_text.split())
    if ":" not in time_text:
        number, period = time_text.split()
        time_text = f"{number}:00 {period}"
    return time_text


def convert_lamplighter_time(date_text, time_text):
    start_text, end_text = time_text.split("-", 1)
    start = datetime.strptime(
        f"{date_text} {normalize_time(start_text)}", "%B %d, %Y %I:%M %p"
    ).replace(tzinfo=EASTERN)
    end = datetime.strptime(
        f"{date_text} {normalize_time(end_text)}", "%B %d, %Y %I:%M %p"
    ).replace(tzinfo=EASTERN)
    if end <= start:
        end += timedelta(days=1)
    return start.isoformat(), end.isoformat()


def fetch_shopify_prices():
    """Fetch exact event prices from Lamplighter's Shopify collection JSON."""
    prices = {}
    try:
        resp = requests.get(f"{EVENTS_URL}/products.json?limit=250", timeout=15)
        if resp.status_code == 200:
            for prod in resp.json().get("products", []):
                handle = prod.get("handle")
                variants = prod.get("variants") or []
                vals = []
                for v in variants:
                    try:
                        vals.append(float(v.get("price", "")))
                    except (TypeError, ValueError):
                        pass
                if handle and vals:
                    lo, hi = min(vals), max(vals)
                    if hi == 0:
                        prices[handle] = ("free", "Free")
                    elif round(lo) == round(hi):
                        prices[handle] = ("ticketed", f"${int(round(lo))}")
                    else:
                        prices[handle] = ("ticketed", f"${int(round(lo))}–${int(round(hi))}")
    except requests.RequestException:
        pass
    return prices


def collect_lamplighter_events():
    response = requests.get(EVENTS_URL, timeout=20)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    event_cards = soup.find_all("a", class_="md:table-row")
    shopify_prices = fetch_shopify_prices()
    events = []

    for card in event_cards:
        title_cell = card.find(attrs={"data-index": "0"})
        date_cell = card.find(attrs={"data-index": "1"})
        time_cell = card.find(attrs={"data-index": "2"})
        location_cell = card.find(attrs={"data-index": "3"})

        if not all((title_cell, date_cell, time_cell, location_cell)):
            print("Skipping incomplete Lamplighter event card")
            continue

        title = title_cell.get_text(" ", strip=True)
        date = date_cell.get_text(" ", strip=True)
        event_time = time_cell.get_text(" ", strip=True)
        address = location_cell.get_text(" ", strip=True)

        try:
            start, end = convert_lamplighter_time(date, event_time)
        except (ValueError, TypeError) as error:
            print(f"Skipping Lamplighter event '{title}': {error}")
            continue

        source_url = urljoin(BASE_URL, card.get("href") or EVENTS_URL)
        handle = source_url.rstrip("/").split("/")[-1].split("?")[0]
        admission_type, price = shopify_prices.get(handle, ("free", "Free"))

        event = {
            "title": title,
            "start": start,
            "end": end,
            "venue": "Lamplighter Brewing Co.",
            "address": address,
            "city": "Cambridge",
            "state": "MA",
            "price": price,
            "admission_type": admission_type,
            "source_type": "venue_website",
            "source_name": "Lamplighter",
            "source_url": source_url,
        }
        events.append(event)

    return events


if __name__ == "__main__":
    events = collect_lamplighter_events()
    print(f"Lamplighter collected: {len(events)}")
    for event in events:
        print(f"{event['start']} | {event['title']}")
