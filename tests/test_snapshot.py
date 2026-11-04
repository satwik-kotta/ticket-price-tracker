import gzip
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "collector"))
import snapshot  # noqa: E402


def fake_event(i, tax):
    return {
        "id": i, "title": f"Event {i}", "type": "nba", "taxonomies": [{"name": tax}],
        "datetime_utc": "2026-12-01T03:00:00", "datetime_local": "2026-11-30T19:00:00",
        "announce_date": "2026-08-01T00:00:00",
        "venue": {"id": 7, "name": "Arena", "city": "Los Angeles", "state": "CA", "capacity": 19000},
        "score": 0.8, "popularity": 0.9,
        "stats": {"listing_count": 120, "visible_listing_count": 110, "lowest_price": 45,
                  "median_price": 90, "average_price": 110, "highest_price": 900,
                  "lowest_sg_base_price": 38, "lowest_price_good_deals": 60},
    }


def test_collect_pages_dedupes_and_flattens(tmp_path, monkeypatch):
    calls = []

    def fetch(params):
        calls.append(params)
        tax = params["taxonomies.name"]
        if params["page"] == 1:
            return {"events": [fake_event(i, tax) for i in range(100)]}
        return {"events": [fake_event(1000 + (hash(tax) % 7), tax)]}

    monkeypatch.setattr(snapshot.time, "sleep", lambda s: None)
    now = datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)
    rows = snapshot.collect("x", now, fetch)
    # 100 shared ids on page 1 are deduplicated across segments
    assert len({r["event_id"] for r in rows}) == len(rows)
    assert rows[0]["lowest_price"] == 45 and rows[0]["city"] == "Los Angeles"
    assert all(c["page"] <= 2 for c in calls)

    monkeypatch.setattr(snapshot, "OUT", tmp_path)
    path = snapshot.write(rows, now)
    with gzip.open(path, "rt") as f:
        back = list(csv.DictReader(f))
    assert len(back) == len(rows)
    assert set(back[0]) == set(snapshot.FIELDS)


import ticketmaster  # noqa: E402


def tm_event(i, seg):
    return {"id": f"{seg}{i}", "name": f"Show {i}",
            "dates": {"start": {"dateTime": "2026-12-01T03:00:00Z", "localDate": "2026-11-30"},
                      "status": {"code": "onsale"}},
            "sales": {"public": {"startDateTime": "2026-08-01T17:00:00Z"}},
            "classifications": [{"genre": {"name": "Rock"}, "subGenre": {"name": "Pop"}}],
            "priceRanges": [{"type": "standard including fees", "currency": "USD", "min": 80, "max": 300},
                            {"type": "standard", "currency": "USD", "min": 65, "max": 250}],
            "_embedded": {"venues": [{"id": "v1", "name": "Forum", "city": {"name": "Inglewood"},
                                      "state": {"stateCode": "CA"}}], "attractions": [{"id": "a1"}]}}


def test_ticketmaster_collect(tmp_path, monkeypatch):
    def fetch(p):
        n = 200 if p["page"] == 0 else 3
        return {"_embedded": {"events": [tm_event(i + 1000 * p["page"], p["segmentName"]) for i in range(n)]},
                "page": {"totalPages": 2}}

    monkeypatch.setattr(ticketmaster.time, "sleep", lambda s: None)
    rows = ticketmaster.collect("k", datetime(2026, 11, 4, tzinfo=timezone.utc), fetch)
    assert len(rows) == 3 * 203
    r = rows[0]
    assert (r["price_min"], r["price_type"], r["city"], r["status"]) == (65, "standard", "Inglewood", "onsale")
    monkeypatch.setattr(ticketmaster, "OUT", tmp_path)
    with gzip.open(ticketmaster.write(rows, datetime(2026, 11, 4, tzinfo=timezone.utc)), "rt") as f:
        assert len(list(csv.DictReader(f))) == len(rows)
