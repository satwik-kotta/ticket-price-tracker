"""Demand curves and the sellout question, from all snapshots so far.

1. Demand curve. SeatGeek's event score is regressed on days-to-event dummies with event fixed effects and
   snapshot fixed effects (log score, standard errors clustered by event). The snapshot effects absorb any
   platform-wide change in scores, so the curve shows how one event's demand moves as its date approaches.
   Days 30 and above are the reference.
2. Raw growth. For events seen both about 15 days out and in their final day, the change in score.
3. Sellout signal. How many Ticketmaster events switch from on sale to off sale before showtime, and when.

Output: outputs/demand_curve.csv and outputs/demand_summary.json
"""
import glob
import json
from pathlib import Path

import numpy as np
import polars as pl
import pyfixest as pf

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
c = pl.col


def load(pattern: str) -> pl.DataFrame:
    files = sorted(glob.glob(str(ROOT / pattern)))
    return pl.concat([pl.read_csv(f, infer_schema_length=0) for f in files], how="diagonal_relaxed")


def seatgeek_panel() -> pl.DataFrame:
    sg = load("data/snapshots/*/*.csv.gz").with_columns(
        c("snapshot_utc").str.to_datetime(time_zone="UTC", strict=False).alias("snap"),
        c("datetime_utc").str.to_datetime(strict=False).dt.replace_time_zone("UTC").alias("start"),
        c("score").cast(pl.Float64, strict=False))
    return sg.filter((c("snap") < c("start")) & (c("score") > 0)).with_columns(
        ((c("start") - c("snap")).dt.total_hours() / 24).floor().cast(pl.Int32).alias("d"))


def demand_curve(sg: pl.DataFrame) -> pl.DataFrame:
    df = sg.with_columns(pl.min_horizontal(c("d"), pl.lit(30)).alias("dbin"), c("score").log().alias("ls"))
    m = pf.feols("ls ~ i(dbin, ref=30) | event_id + snapshot_utc",
                 data=df.select("event_id", "snapshot_utc", "dbin", "ls").to_pandas(), vcov={"CRV1": "event_id"})
    t = m.tidy().reset_index()
    return pl.DataFrame({
        "days_to_event": [int(s.split("::")[1]) for s in t["Coefficient"]],
        "score_change_pct": (np.exp(t["Estimate"]) - 1) * 100,
        "ci_low_pct": (np.exp(t["2.5%"]) - 1) * 100,
        "ci_high_pct": (np.exp(t["97.5%"]) - 1) * 100,
    }).sort("days_to_event")


def raw_growth(sg: pl.DataFrame) -> pl.DataFrame:
    s0 = sg.filter(c("d").is_between(14, 16)).group_by("event_id").agg(c("score").mean().alias("s0"), c("segment").first())
    s1 = sg.filter(c("d") <= 1).group_by("event_id").agg(c("score").mean().alias("s1"))
    g = s0.join(s1, on="event_id").with_columns((c("s1") / c("s0") - 1).alias("growth"))
    return g.group_by("segment").agg(pl.len().alias("events"), (c("growth").median() * 100).alias("median_growth_pct"),
                                     (c("growth") > 0).mean().alias("share_rising")).sort("segment")


def offsale_switches() -> dict:
    tm = load("data/tm_snapshots/*/*.csv.gz").with_columns(
        c("snapshot_utc").str.to_datetime(time_zone="UTC", strict=False).alias("snap"),
        c("start_utc").str.to_datetime(time_zone="UTC", strict=False).alias("start"),
        c("public_sale_end").str.to_datetime(time_zone="UTC", strict=False).alias("sale_end"))
    tm = tm.filter(c("snap") < c("start")).sort("event_id", "snap")
    ev = tm.group_by("event_id").agg(c("status").first().alias("first_status"),
                                     c("snap").filter(c("status") == "offsale").min().alias("first_off"),
                                     c("start").first(), c("sale_end").last())
    seen_on = ev.filter(c("first_status") == "onsale")
    sw = seen_on.filter(c("first_off").is_not_null()).with_columns(
        ((c("start") - c("first_off")).dt.total_hours()).alias("hours_before_start"),
        ((c("sale_end") - c("first_off")).dt.total_hours()).alias("hours_before_sale_end"))
    return {"events_seen_on_sale": seen_on.height, "switched_to_off_sale": sw.height,
            "max_hours_before_start": float(sw["hours_before_start"].max() or 0),
            "switched_more_than_a_day_before_sale_end": int((sw["hours_before_sale_end"] > 24).sum())}


def main() -> None:
    OUT.mkdir(exist_ok=True)
    sg = seatgeek_panel()
    curve = demand_curve(sg)
    curve.write_csv(OUT / "demand_curve.csv")
    peak = curve.sort("score_change_pct", descending=True).row(0, named=True)
    summary = {
        "seatgeek_snapshots": int(sg["snapshot_utc"].n_unique()), "seatgeek_events": int(sg["event_id"].n_unique()),
        "event_snapshot_rows": sg.height, "first_snapshot": str(sg["snap"].min()), "last_snapshot": str(sg["snap"].max()),
        "curve_peak": peak, "curve_event_day": curve.filter(c("days_to_event") == 0).row(0, named=True),
        "raw_growth_15_days_to_final_day": raw_growth(sg).to_dicts(),
        "ticketmaster_offsale": offsale_switches(),
    }
    (OUT / "demand_summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps(summary, indent=1, default=str))


if __name__ == "__main__":
    main()
