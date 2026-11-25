import json
import re

from datetime import datetime
from difflib import SequenceMatcher


# --------------------------------------------------
# HAPPENIN' — DUPLICATE AUDIT
#
# This script DOES NOT modify events.json.
#
# Its only job is to inspect the current dataset and
# show us events that might represent the same
# real-world event.
#
# We are deliberately auditing first before building
# automatic deduplication rules.
# --------------------------------------------------


EVENTS_FILE = "events.json"


# --------------------------------------------------
# Normalize text for comparison.
#
# Example:
#
#   "Middle East - Upstairs"
#   "Middle East- Upstairs"
#
# become much easier to compare after punctuation,
# capitalization and extra spaces are removed.
# --------------------------------------------------

def normalize_text(text):

    if not text:
        return ""

    text = text.lower()

    # Replace punctuation with spaces.
    text = re.sub(
        r"[^a-z0-9]+",
        " ",
        text
    )

    # Collapse multiple spaces.
    text = " ".join(
        text.split()
    )

    return text


# --------------------------------------------------
# Return a similarity score between 0 and 1.
#
# 1.0 = identical
# 0.0 = completely different
# --------------------------------------------------

def similarity(text_a, text_b):

    text_a = normalize_text(text_a)
    text_b = normalize_text(text_b)

    if not text_a or not text_b:
        return 0.0

    return SequenceMatcher(
        None,
        text_a,
        text_b
    ).ratio()


# --------------------------------------------------
# Parse event start time.
# --------------------------------------------------

def parse_start(event):

    start_text = event.get("start")

    if not start_text:
        return None

    try:

        return datetime.fromisoformat(
            start_text
        )

    except ValueError:

        return None


# --------------------------------------------------
# Compare two events.
#
# For this first audit, events must occur within
# 30 minutes of each other before we even consider
# them possible duplicates.
# --------------------------------------------------

def compare_events(event_a, event_b):

    start_a = parse_start(event_a)
    start_b = parse_start(event_b)

    if not start_a or not start_b:
        return None

    time_difference = abs(
        (
            start_a - start_b
        ).total_seconds()
    )

    time_difference_minutes = (
        time_difference / 60
    )


    # Too far apart in time to be interesting.
    if time_difference_minutes > 30:

        return None


    title_score = similarity(
        event_a.get("title"),
        event_b.get("title")
    )


    venue_score = similarity(
        event_a.get("venue"),
        event_b.get("venue")
    )


    # --------------------------------------------------
    # Candidate rules
    #
    # HIGH:
    # Very similar title + very similar venue.
    #
    # POSSIBLE:
    # Very similar title but venue differs.
    #
    # VENUE MATCH:
    # Same venue/time but title differs enough that
    # we want to inspect it manually.
    # --------------------------------------------------

    category = None


    if (
        title_score >= 0.80
        and venue_score >= 0.80
    ):

        category = "HIGH"


    elif title_score >= 0.80:

        category = "TITLE MATCH / VENUE DIFFERENT"


    elif venue_score >= 0.90:

        category = "VENUE + TIME MATCH"


    if not category:

        return None


    return {
        "category": category,
        "time_difference": time_difference_minutes,
        "title_score": title_score,
        "venue_score": venue_score,
    }


# --------------------------------------------------
# Print one candidate pair.
# --------------------------------------------------

def print_pair(
    number,
    event_a,
    event_b,
    comparison
):

    print()
    print("=" * 70)

    print(
        f"CANDIDATE {number}"
    )

    print(
        "Category:",
        comparison["category"]
    )

    print(
        "Time difference:",
        f'{comparison["time_difference"]:.0f} minutes'
    )

    print(
        "Title similarity:",
        f'{comparison["title_score"]:.2f}'
    )

    print(
        "Venue similarity:",
        f'{comparison["venue_score"]:.2f}'
    )

    print("-" * 70)

    print(
        "A:",
        event_a.get("title")
    )

    print(
        "   Start:",
        event_a.get("start")
    )

    print(
        "   Venue:",
        event_a.get("venue")
    )

    print(
        "   Source:",
        event_a.get("source_name")
    )

    print(
        "   Source ID:",
        event_a.get("source_id")
    )

    print(
        "   URL:",
        event_a.get("source_url")
    )

    print()

    print(
        "B:",
        event_b.get("title")
    )

    print(
        "   Start:",
        event_b.get("start")
    )

    print(
        "   Venue:",
        event_b.get("venue")
    )

    print(
        "   Source:",
        event_b.get("source_name")
    )

    print(
        "   Source ID:",
        event_b.get("source_id")
    )

    print(
        "   URL:",
        event_b.get("source_url")
    )


# --------------------------------------------------
# MAIN
# --------------------------------------------------

print(
    "Loading Happenin' events..."
)


with open(
    EVENTS_FILE,
    "r",
    encoding="utf-8"
) as file:

    events = json.load(file)


print(
    "Events loaded:",
    len(events)
)

print()


# --------------------------------------------------
# Compare every event against every event that comes
# after it.
#
# With ~300 events this is perfectly fine.
#
# Later, with tens of thousands of events, we would
# NOT do it this way. We'd group/index events first.
# --------------------------------------------------

candidates = []


for i in range(len(events)):

    event_a = events[i]

    for j in range(
        i + 1,
        len(events)
    ):

        event_b = events[j]


        comparison = compare_events(
            event_a,
            event_b
        )


        if comparison:

            candidates.append(
                (
                    event_a,
                    event_b,
                    comparison
                )
            )


# --------------------------------------------------
# Sort strongest title matches first.
# --------------------------------------------------

candidates.sort(
    key=lambda item: (
        item[2]["title_score"],
        item[2]["venue_score"]
    ),
    reverse=True
)


# --------------------------------------------------
# Summary
# --------------------------------------------------

high_count = 0
title_different_venue_count = 0
venue_time_count = 0


for _, _, comparison in candidates:

    category = comparison[
        "category"
    ]


    if category == "HIGH":

        high_count += 1


    elif (
        category
        == "TITLE MATCH / VENUE DIFFERENT"
    ):

        title_different_venue_count += 1


    elif category == "VENUE + TIME MATCH":

        venue_time_count += 1


print("=" * 70)

print(
    "DUPLICATE AUDIT SUMMARY"
)

print("=" * 70)

print(
    "Events inspected:",
    len(events)
)

print(
    "Candidate pairs:",
    len(candidates)
)

print()

print(
    "HIGH:",
    high_count
)

print(
    "TITLE MATCH / VENUE DIFFERENT:",
    title_different_venue_count
)

print(
    "VENUE + TIME MATCH:",
    venue_time_count
)


# --------------------------------------------------
# Detailed candidates
# --------------------------------------------------

for number, candidate in enumerate(
    candidates,
    start=1
):

    event_a = candidate[0]
    event_b = candidate[1]
    comparison = candidate[2]

    print_pair(
        number,
        event_a,
        event_b,
        comparison
    )


print()
print("=" * 70)

print(
    "AUDIT COMPLETE"
)

print("=" * 70)