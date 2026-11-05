import sys
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analysis"))
from match_vendors import match  # noqa: E402


def test_match_pairs_same_event_and_skips_lookalikes():
    sg = pl.DataFrame({
        "event_id": [1, 2, 3],
        "datetime_local": ["2026-12-01T19:30:00", "2026-12-01T20:00:00", "2026-12-02T19:00:00"],
        "city": ["Boston", "Boston", "Boston"],
        "title": ["Miami Heat at Boston Celtics", "Brett Eldredge", "Hamilton - Boston"],
        "venue_name": ["TD Garden", "Boch Center Wang Theatre", "Citizens Opera House"],
    })
    tm = pl.DataFrame({
        "event_id": ["a", "b", "c"],
        "local_date": ["2026-12-01", "2026-12-01", "2026-12-03"],  # c is a different day
        "city": ["Boston", "Boston", "Boston"],
        "name": ["Boston Celtics vs. Miami Heat", "Brett Eldredge: Glow Tour", "Hamilton (Touring)"],
        "venue_name": ["TD Garden", "Boch Center Wang Theatre", "Citizens Opera House"],
    })
    m = dict(match(sg, tm).select("event_id", "tm_event_id").iter_rows())
    assert m == {1: "a", 2: "b"}
