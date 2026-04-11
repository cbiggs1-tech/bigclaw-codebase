#!/usr/bin/env python3
"""Google Calendar checker for BigClaw — uses private ICS URL (no OAuth, no expiry).

Usage:
    python3 calendar_check.py              # Today + next 3 days
    python3 calendar_check.py --days 7     # Next 7 days
    python3 calendar_check.py --json
"""

import argparse
import json
import os
import requests
from datetime import datetime, timedelta, timezone, date
from icalendar import Calendar

ICS_URL = os.environ.get("GOOGLE_CALENDAR_ICS_URL", "")


def fetch_events(days_ahead=3):
    """Fetch upcoming calendar events from the ICS feed."""
    if not ICS_URL:
        raise ValueError("GOOGLE_CALENDAR_ICS_URL not set in environment")

    resp = requests.get(ICS_URL, timeout=15)
    resp.raise_for_status()

    cal = Calendar.from_ical(resp.content)

    now   = datetime.now(timezone.utc)
    until = now + timedelta(days=days_ahead)

    events = []
    for component in cal.walk():
        if component.name != "VEVENT":
            continue

        dtstart = component.get("DTSTART")
        if not dtstart:
            continue

        start = dtstart.dt
        # Normalize to datetime with timezone
        if isinstance(start, date) and not isinstance(start, datetime):
            start = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
        elif start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)

        if not (now <= start <= until):
            continue

        dtend = component.get("DTEND")
        end = dtend.dt if dtend else None
        if isinstance(end, date) and not isinstance(end, datetime):
            end = datetime(end.year, end.month, end.day, tzinfo=timezone.utc)
        elif end and end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)

        summary  = str(component.get("SUMMARY", "(no title)"))
        location = str(component.get("LOCATION", ""))
        desc     = str(component.get("DESCRIPTION", ""))

        events.append({
            "summary":  summary,
            "start":    start,
            "end":      end,
            "location": location,
            "description": desc[:200] if desc else "",
        })

    # Sort by start time
    events.sort(key=lambda e: e["start"])
    return events


def format_events(events, days_ahead=3):
    if not events:
        return f"📅 No events in the next {days_ahead} days."

    lines = [f"📅 Upcoming Events (next {days_ahead} days):\n"]
    ct = timezone(timedelta(hours=-6))  # CST

    for e in events:
        start_ct = e["start"].astimezone(ct)
        day_str  = start_ct.strftime("%A %b %d")
        time_str = start_ct.strftime("%I:%M %p CT").lstrip("0")

        # All-day check
        if e["start"].hour == 0 and e["start"].minute == 0:
            time_str = "All day"

        line = f"  📌 {day_str} {time_str} — {e['summary']}"
        if e["location"]:
            line += f"\n     📍 {e['location']}"
        lines.append(line)

    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Calendar checker (ICS)")
    parser.add_argument("--days", type=int, default=3, help="Days ahead to look")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        events = fetch_events(args.days)
        if args.json:
            print(json.dumps([
                {**e, "start": e["start"].isoformat(), "end": e["end"].isoformat() if e["end"] else None}
                for e in events
            ], indent=2))
        else:
            print(format_events(events, args.days))
    except Exception as e:
        print(f"❌ Calendar error: {e}")
        import traceback
        traceback.print_exc()
