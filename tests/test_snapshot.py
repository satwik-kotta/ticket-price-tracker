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
        "performers": [{"name": "A", "score": 0.4, "num_upcoming_events": 3},
                       {"name": "B", "score": 0.9, "num_upcoming_events": 40}],
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
    assert rows[0]["city"] == "Los Angeles"
    assert (rows[0]["top_performer"], rows[0]["top_performer_upcoming"], rows[0]["performer_count"]) == ("B", 40, 2)
    assert all(c["page"] <= 2 for c in calls)
    # 8 weekly windows per segment, and windows stay inside the 56 day horizon
    assert len({(c["taxonomies.name"], c["datetime_utc.gte"]) for c in calls}) == 3 * 8
    assert max(c["datetime_utc.lte"] for c in calls) == "2026-12-30T12:00:00"

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
            "sales": {"public": {"startDateTime": "2026-08-01T17:00:00Z", "endDateTime": "2026-12-01T03:00:00Z"},
                      "presales": [{"startDateTime": "2026-07-30T17:00:00Z"}, {"startDateTime": "2026-07-29T17:00:00Z"}]},
            "ticketLimit": {"info": "8 per order"}, "promoter": {"name": "Live Nation"},
            "_embedded": {"venues": [{"id": "v1", "name": "Forum", "city": {"name": "Inglewood"},
                                      "state": {"stateCode": "CA"}}],
                          "attractions": [{"id": "a1", "name": "Band", "upcomingEvents": {"_total": 52}}]}}


def test_ticketmaster_collect(tmp_path, monkeypatch):
    def fetch(p):
        n = 200 if p["page"] == 0 else 3
        tag = p["segmentName"] + p["startDateTime"]
        return {"_embedded": {"events": [tm_event(i + 1000 * p["page"], tag) for i in range(n)]},
                "page": {"totalPages": 2}}

    monkeypatch.setattr(ticketmaster.time, "sleep", lambda s: None)
    rows = ticketmaster.collect("k", datetime(2026, 11, 4, tzinfo=timezone.utc), fetch)
    assert len(rows) == 3 * 8 * 203
    r = rows[0]
    assert (r["city"], r["status"], r["presale_count"], r["first_presale_start"]) == ("Inglewood", "onsale", 2, "2026-07-29T17:00:00Z")
    assert (r["attraction_upcoming"], r["has_ticket_limit"], r["promoter"]) == (52, 1, "Live Nation")
    monkeypatch.setattr(ticketmaster, "OUT", tmp_path)
    with gzip.open(ticketmaster.write(rows, datetime(2026, 11, 4, tzinfo=timezone.utc)), "rt") as f:
        assert len(list(csv.DictReader(f))) == len(rows)
