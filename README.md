# Live Event Demand & Sellout Tracker

Which events sell out, how early can you tell, and how does demand build in the weeks before a show?

Every 6 hours a GitHub Actions job takes two snapshots of upcoming US sports, concert and theater events in the next 8 weeks:

- **SeatGeek:** SeatGeek's event score and popularity, and the headline performer's score and number of upcoming events. These are SeatGeek's own demand signals.
- **Ticketmaster:** sale status (on sale, off sale, cancelled, rescheduled), public sale and presale dates, number of presales, ticket limits, promoter, and the headline act's tour size.

Following the same event across snapshots gives its demand curve by days to event. An event that goes **off sale while its public sale should still be open** is counted as a likely sellout.

**Status:** collecting data since November 4, 2026. The demand curve and sellout questions below need a few weeks of snapshots. The first cross-source result is in already.

## First result: matching the two sources (November 5, 2026)

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
