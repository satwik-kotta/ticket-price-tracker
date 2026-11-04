"""Take one snapshot of upcoming US Ticketmaster events: sale status, presales and artist demand.

Runs next to the SeatGeek collector. Writes data/tm_snapshots/YYYY-MM-DD/HHMM.csv.gz.
An event whose status turns "offsale" while its public sale is still meant to be open is
treated as a likely sellout in the analysis.
Needs a free Ticketmaster Discovery API key in TICKETMASTER_API_KEY.
API docs: https://developer.ticketmaster.com/products-and-docs/apis/discovery-api/v2/
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

API = "https://app.ticketmaster.com/discovery/v2/events.json"
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "tm_snapshots"

SEGMENTS = {"sports": "Sports", "concert": "Music", "theater": "Arts & Theatre"}
PAGE_SIZE = 200
MAX_PAGES = 2          # top 400 events per segment and week
HORIZON_DAYS = 56
WINDOW_DAYS = 7        # one query per week ahead, so near and far events are both covered

FIELDS = [
    "snapshot_utc", "segment", "event_id", "name", "genre", "subgenre", "start_utc", "local_date",
    "status", "public_sale_start", "public_sale_end", "presale_count", "first_presale_start",
    "has_ticket_limit", "has_seatmap", "promoter", "venue_id", "venue_name", "city", "state",
    "attraction_ids", "attraction_names", "attraction_upcoming", "url",
]


def get(params: dict, retries: int = 4) -> dict:
    url = API + "?" + urllib.parse.urlencode(params)
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return json.load(r)
        except Exception as e:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt * 3)
            print(f"retry {attempt + 1}: {e}", file=sys.stderr)
    return {}


def flatten(ev: dict, segment: str, snapshot: str) -> dict:
    dates = ev.get("dates") or {}
    start = dates.get("start") or {}
    cls = (ev.get("classifications") or [{}])[0]
    emb = ev.get("_embedded") or {}
    venue = (emb.get("venues") or [{}])[0]
    sales = ev.get("sales") or {}
    presales = sales.get("presales") or []
    attractions = emb.get("attractions") or []
    return {
        "snapshot_utc": snapshot,
        "segment": segment,
        "event_id": ev.get("id"),
        "name": ev.get("name"),
        "genre": (cls.get("genre") or {}).get("name"),
        "subgenre": (cls.get("subGenre") or {}).get("name"),
        "start_utc": start.get("dateTime"),
        "local_date": start.get("localDate"),
        "status": (dates.get("status") or {}).get("code"),
        "public_sale_start": (sales.get("public") or {}).get("startDateTime"),
        "public_sale_end": (sales.get("public") or {}).get("endDateTime"),
        "presale_count": len(presales),
        "first_presale_start": min((p.get("startDateTime") for p in presales if p.get("startDateTime")), default=None),
        "has_ticket_limit": int(bool(ev.get("ticketLimit"))),
        "has_seatmap": int(bool(ev.get("seatmap"))),
        "promoter": (ev.get("promoter") or {}).get("name"),
        "venue_id": venue.get("id"),
        "venue_name": venue.get("name"),
        "city": (venue.get("city") or {}).get("name"),
        "state": (venue.get("state") or {}).get("stateCode"),
        "attraction_ids": "|".join(a.get("id", "") for a in attractions),
        "attraction_names": "|".join(a.get("name", "") for a in attractions),
        # how many upcoming events the headline act has on sale, a measure of tour size
        "attraction_upcoming": ((attractions[0].get("upcomingEvents") or {}).get("_total")) if attractions else None,
        "url": ev.get("url"),
    }


def collect(api_key: str, now: datetime | None = None, fetch=get) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    snapshot = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    rows, seen = [], set()
    windows = [(now + timedelta(days=d), now + timedelta(days=min(d + WINDOW_DAYS, HORIZON_DAYS)))
               for d in range(0, HORIZON_DAYS, WINDOW_DAYS)]
    for (segment, name), (w0, w1) in ((s, w) for s in SEGMENTS.items() for w in windows):
        lo, hi = w0.strftime("%Y-%m-%dT%H:%M:%SZ"), w1.strftime("%Y-%m-%dT%H:%M:%SZ")
        for page in range(MAX_PAGES):
            data = fetch({
                "apikey": api_key, "countryCode": "US", "segmentName": name, "startDateTime": lo,
                "endDateTime": hi, "sort": "relevance,desc", "size": PAGE_SIZE, "page": page,
            })
            events = (data.get("_embedded") or {}).get("events") or []
            for ev in events:
                if ev.get("id") in seen:
                    continue
                seen.add(ev.get("id"))
                rows.append(flatten(ev, segment, snapshot))
            total_pages = (data.get("page") or {}).get("totalPages", 0)
            if len(events) < PAGE_SIZE or page + 1 >= total_pages:
                break
            time.sleep(0.3)   # 5 requests a second limit
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
    key = os.environ.get("TICKETMASTER_API_KEY")
    if not key:
        print("TICKETMASTER_API_KEY not set, skipping")
        return
    now = datetime.now(timezone.utc)
    rows = collect(key, now)
    path = write(rows, now)
    offsale = sum(1 for r in rows if r["status"] == "offsale")
    print(f"{len(rows)} events, {offsale} off sale -> {path.relative_to(ROOT)}")
    if not rows:
        sys.exit("No events returned, check the API key")


if __name__ == "__main__":
    main()
