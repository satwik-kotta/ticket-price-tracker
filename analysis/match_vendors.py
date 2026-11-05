"""Match the same upcoming events across SeatGeek and Ticketmaster, then compare SeatGeek demand signals
for events Ticketmaster still sells against events it has already taken off sale.

Matching rule: same local date and city, then at least 30% word overlap on both the event name and the
venue name (Jaccard on words longer than 2 letters). Each event is matched at most once on each side.

Output: outputs/matched_events.csv and outputs/match_summary.json
"""
import glob
import json
from pathlib import Path

import polars as pl
from scipy.stats import mannwhitneyu

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
STOP = {"the", "and", "with", "tour", "live", "presents", "theatre", "theater", "center", "arena"}
c = pl.col


def load(pattern: str) -> pl.DataFrame:
    files = sorted(glob.glob(str(ROOT / pattern)))
    df = pl.concat([pl.read_csv(f, infer_schema_length=10000) for f in files], how="diagonal_relaxed")
    return df.sort("snapshot_utc").unique("event_id", keep="last")  # latest view of each event


def norm(e: pl.Expr) -> pl.Expr:
    return e.str.to_lowercase().str.replace_all(r"[^a-z0-9 ]", " ").str.replace_all(r"\s+", " ").str.strip_chars()


def words(s: str | None) -> set[str]:
    return {w for w in (s or "").split() if len(w) > 2 and w not in STOP}


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def match(sg: pl.DataFrame, tm: pl.DataFrame) -> pl.DataFrame:
    a = sg.select("event_id", c("datetime_local").str.slice(0, 10).alias("d"), norm(c("city")).alias("cy"),
                  norm(c("title")).alias("nm"), norm(c("venue_name")).alias("vn"))
    b = tm.select(c("event_id").alias("tm_event_id"), c("local_date").cast(pl.Utf8).alias("d"),
                  norm(c("city")).alias("cy"), norm(c("name")).alias("tnm"), norm(c("venue_name")).alias("tvn"))
    pairs = a.join(b, on=["d", "cy"], how="inner")
    scored = pairs.with_columns(
        pl.struct("nm", "tnm").map_elements(lambda r: jaccard(words(r["nm"]), words(r["tnm"])), return_dtype=pl.Float64).alias("name_sim"),
        pl.struct("vn", "tvn").map_elements(lambda r: jaccard(words(r["vn"]), words(r["tvn"])), return_dtype=pl.Float64).alias("venue_sim"),
    ).filter((c("name_sim") >= 0.3) & (c("venue_sim") >= 0.3))
    best = (scored.sort(c("name_sim") + c("venue_sim"), descending=True)
            .unique("event_id", keep="first", maintain_order=True)
            .unique("tm_event_id", keep="first", maintain_order=True))
    return best.select("event_id", "tm_event_id", "name_sim", "venue_sim")


def main() -> None:
    OUT.mkdir(exist_ok=True)
    sg = load("data/snapshots/*/*.csv.gz")
    tm = load("data/tm_snapshots/*/*.csv.gz")
    m = match(sg, tm)
    num = ["score", "popularity", "listing_count", "capacity"]
    mm = (m.join(sg.with_columns(*[c(x).cast(pl.Float64, strict=False) for x in num]), on="event_id")
          .join(tm.select(c("event_id").alias("tm_event_id"), "status", "presale_count", "public_sale_start"),
                on="tm_event_id"))
    mm.write_csv(OUT / "matched_events.csv")

    two = mm.filter(c("status").is_in(["onsale", "offsale"]))
    by_status = two.group_by("status").agg(pl.len().alias("events"), c("score").median().alias("median_score"),
                                           c("listing_count").median().alias("median_listings"))
    q = two.with_columns(c("score").qcut(5, labels=[f"Q{i}" for i in range(1, 6)], allow_duplicates=True).alias("q"))
    by_q = q.group_by("q").agg(pl.len().alias("events"), (c("status") == "offsale").mean().alias("offsale_share")).sort("q")
    off, on = (two.filter(c("status") == s)["score"].drop_nulls() for s in ("offsale", "onsale"))
    summary = {
        "seatgeek_events": sg.height, "ticketmaster_events": tm.height,
        "snapshots": {"seatgeek": int(sg["snapshot_utc"].n_unique()), "ticketmaster": int(tm["snapshot_utc"].n_unique())},
        "matched_events": mm.height,
        "status_counts": dict(mm.group_by("status").len().iter_rows()),
        "by_status": by_status.to_dicts(),
        "offsale_share_by_score_quintile": by_q.with_columns(c("q").cast(pl.Utf8)).to_dicts(),
        "mann_whitney_p": float(mannwhitneyu(off, on).pvalue) if len(off) and len(on) else None,
    }
    (OUT / "match_summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps(summary, indent=1, default=str))


if __name__ == "__main__":
    main()
