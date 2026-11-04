"""Take one snapshot of upcoming SeatGeek events and their ticket price stats.

Runs on a schedule in GitHub Actions. Each run appends one gzipped CSV under
data/snapshots/YYYY-MM-DD/HHMM.csv.gz, so prices for the same event can be followed
as the event date gets closer.

Needs a free SeatGeek API client id in the SEATGEEK_CLIENT_ID environment variable.
API docs: https://platform.seatgeek.com/
"""
import csv
import gzip
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

API = "https://api.seatgeek.com/2/events"
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "snapshots"

# Three verticals, most popular events first, up to 60 days ahead.
SEGMENTS = {
    "sports": "sports",
    "concert": "concert",
    "theater": "theater",
}
PER_PAGE = 100
MAX_PAGES = 10
HORIZON_DAYS = 60

FIELDS = [
    "snapshot_utc", "segment", "event_id", "title", "type", "taxonomy", "datetime_utc", "datetime_local",
    "announce_date", "venue_id", "venue_name", "city", "state", "capacity", "score", "popularity",
    "listing_count", "visible_listing_count", "lowest_price", "median_price", "average_price",
    "highest_price", "lowest_sg_base_price", "lowest_price_good_deals",
]


def get(params: dict, retries: int = 4) -> dict:
    url = API + "?" + urllib.parse.urlencode(params)
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return json.load(r)
        except Exception as e:  # network or rate limit
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt * 3)
            print(f"retry {attempt + 1}: {e}", file=sys.stderr)
    return {}


def flatten(ev: dict, segment: str, snapshot: str) -> dict:
    venue = ev.get("venue") or {}
    stats = ev.get("stats") or {}
    tax = (ev.get("taxonomies") or [{}])[0].get("name")
    return {
        "snapshot_utc": snapshot,
        "segment": segment,
        "event_id": ev.get("id"),
        "title": ev.get("title"),
        "type": ev.get("type"),
        "taxonomy": tax,
        "datetime_utc": ev.get("datetime_utc"),
        "datetime_local": ev.get("datetime_local"),
        "announce_date": ev.get("announce_date"),
        "venue_id": venue.get("id"),
        "venue_name": venue.get("name"),
        "city": venue.get("city"),
        "state": venue.get("state"),
        "capacity": venue.get("capacity"),
        "score": ev.get("score"),
        "popularity": ev.get("popularity"),
        "listing_count": stats.get("listing_count"),
        "visible_listing_count": stats.get("visible_listing_count"),
        "lowest_price": stats.get("lowest_price"),
        "median_price": stats.get("median_price"),
        "average_price": stats.get("average_price"),
        "highest_price": stats.get("highest_price"),
        "lowest_sg_base_price": stats.get("lowest_sg_base_price"),
        "lowest_price_good_deals": stats.get("lowest_price_good_deals"),
    }


def collect(client_id: str, now: datetime | None = None, fetch=get) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    snapshot = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    lo = now.strftime("%Y-%m-%dT%H:%M:%S")
    hi = (now + timedelta(days=HORIZON_DAYS)).strftime("%Y-%m-%dT%H:%M:%S")
    rows, seen = [], set()
    for segment, taxonomy in SEGMENTS.items():
        for page in range(1, MAX_PAGES + 1):
            data = fetch({
                "client_id": client_id, "taxonomies.name": taxonomy, "datetime_utc.gte": lo,
                "datetime_utc.lte": hi, "sort": "score.desc", "per_page": PER_PAGE, "page": page,
            })
            events = data.get("events") or []
            for ev in events:
                if ev.get("id") in seen:
                    continue
                seen.add(ev.get("id"))
                rows.append(flatten(ev, segment, snapshot))
            if len(events) < PER_PAGE:
                break
            time.sleep(0.5)
    return rows


def write(rows: list[dict], now: datetime) -> Path:
    folder = OUT / now.strftime("%Y-%m-%d")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (now.strftime("%H%M") + ".csv.gz")
    with gzip.open(path, "wt", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    return path


def main() -> None:
    client_id = os.environ.get("SEATGEEK_CLIENT_ID")
    if not client_id:
        sys.exit("Set SEATGEEK_CLIENT_ID")
    now = datetime.now(timezone.utc)
    rows = collect(client_id, now)
    path = write(rows, now)
    priced = sum(1 for r in rows if r["lowest_price"] is not None)
    print(f"{len(rows)} events, {priced} with prices -> {path.relative_to(ROOT)}")
    if not rows:
        sys.exit("No events returned, check the client id")


if __name__ == "__main__":
    main()
