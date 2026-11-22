# Live Event Demand & Sellout Tracker

Which events sell out, how early can you tell, and how does demand build in the weeks before a show?

Every 6 hours a GitHub Actions job takes two snapshots of upcoming US sports, concert and theater events in the next 8 weeks:

- **SeatGeek:** SeatGeek's event score and popularity, and the headline performer's score and number of upcoming events. These are SeatGeek's own demand signals.
- **Ticketmaster:** sale status (on sale, off sale, cancelled, rescheduled), public sale and presale dates, number of presales, ticket limits, promoter, and the headline act's tour size.

Following the same event across snapshots gives its demand curve by days to event. An event that goes **off sale while its public sale should still be open** is counted as a likely sellout.

**Status:** collecting since November 4, 2026. Results below use 45 SeatGeek snapshots through November 22
(14,820 events, 307,078 event snapshot rows) and 43 Ticketmaster snapshots (16,199 events).

## Results (November 22, 2026)

### Demand rises for two weeks, peaks 5 days out, then fades

`analysis/demand_curves.py` regresses each event's log SeatGeek score on days to the event, with event fixed
effects and snapshot fixed effects (standard errors clustered by event). The snapshot effects remove any
platform wide shift in scores, so the curve shows how one event's demand moves as its date gets closer.

| Days to event | 30+ | 17 | 14 | 10 | 7 | **5** | 3 | 1 | 0 |
|---|---|---|---|---|---|---|---|---|---|
| Score vs 30+ days out | ref | +0.4% | +1.3% | +4.5% | +7.8% | **+13.6%** | +10.1% | +5.8% | +1.9% |

The peak at 5 days is +13.6% (95% CI 12.6% to 14.5%). Without the model, for 744 events seen about 15 days
out and again in their final day, the median score rose 11.4% for concerts, 9.7% for sports and 13.2% for
theater, and about 9 in 10 events rose in every segment. The last week is where demand moves, so that is
when a pricing or marketing change would matter most.

### Ticketmaster's off sale status is not a sellout signal

Of 14,713 events first seen on sale, only 21 switched to off sale before showtime, all within 17 hours of the
start and none more than a day before the scheduled end of sales. In the public Discovery API the status
follows the sales calendar, not inventory. Without partner access to inventory or prices, sellouts cannot be observed directly,
so this project reports demand curves instead of a sellout model.

Outputs: `outputs/demand_curve.csv`, `outputs/demand_summary.json`.

## Matching the two sources (November 5, 2026)

`analysis/match_vendors.py` links the same event across both APIs. A pair must share the local date and city and
overlap by at least 30% on both event name and venue name, and each event is used at most once on each side.

- **3,268 events matched** out of 7,829 SeatGeek and 10,164 Ticketmaster events. A random check of 40 pairs
  found all 40 correct, including name differences like "Miami Heat at Boston Celtics" vs "Boston Celtics vs. Miami Heat".
- Ticketmaster already lists **60 of the matched events as off sale**, 25 as rescheduled and 5 as cancelled.
- **SeatGeek's demand score does not separate the off sale events.** Their median score is 0.49, against 0.50 for
  events still on sale (Mann-Whitney p = 0.78), and the off sale share is flat across score quintiles (0.9% to 2.5%).
  A single snapshot of SeatGeek's score is not a sellout signal, so the analysis will rely on how demand changes
  over time rather than its level on one day.

Outputs: `outputs/matched_events.csv`, `outputs/match_summary.json`.

## Questions

1. How does demand (SeatGeek score and popularity) change over the last 8 weeks before an event, for sports, concerts and theater?
2. Which events sell out, and how many days before the event?
3. Can demand two to three weeks out predict a sellout? Which signals matter most: demand trend, presales, tour size, venue, day of week?
4. Which events are at risk of not selling through, early enough to act (marketing push, price change)?

## Why not prices?

Both SeatGeek's and Ticketmaster's public APIs now return no ticket prices to non-partner accounts. I checked this in the first runs: the price fields were empty for all 3,000 events from each source. The project uses the demand and availability signals both APIs still provide.

## How it works

```
collector/snapshot.py          SeatGeek events API, top 300 events per category and week ahead
collector/ticketmaster.py      Ticketmaster Discovery API, top 400 events per category and week ahead
.github/workflows/snapshot.yml runs every 6 hours, commits data/snapshots/ and data/tm_snapshots/
analysis/demand_curves.py      demand curve with event and snapshot fixed effects, off sale switch check
analysis/match_vendors.py      links the same event across both sources and compares demand by sale status
tests/test_snapshot.py         paging, weekly windows, de-duplication, fields and file format, with mocked APIs
tests/test_match.py            matching pairs the same event and skips other days
```

## Run it locally

```bash
export SEATGEEK_CLIENT_ID=your_client_id     # free at seatgeek.com/account/develop
export TICKETMASTER_API_KEY=your_key         # free at developer.ticketmaster.com
python collector/snapshot.py
python collector/ticketmaster.py
python -m pytest -q
```

Data: SeatGeek Platform API and Ticketmaster Discovery API.
