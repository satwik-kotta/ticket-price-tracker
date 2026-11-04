# Ticket Price Tracker

How do ticket prices and supply change as an event gets closer, and does that differ for sports, concerts and theater?

Every 6 hours a GitHub Actions job takes a snapshot of about 3,000 upcoming SeatGeek events in the next 60 days: lowest, median, average and highest listed price, and the number of listings. Following the same event across snapshots gives its price and supply curve by days to event.

**Status:** collecting data. Analysis and dashboard follow once there are a few weeks of snapshots.

## Questions

1. How do the lowest and median price move in the last 60 days before an event, by category?
2. How fast do listings appear or sell out, and does supply lead price?
3. When is the cheapest time to buy, and how much does waiting save or cost?
4. Which events are most at risk of selling out or of prices collapsing near the date?

## How it works

```
collector/snapshot.py          calls the SeatGeek events API, one row per event per snapshot
.github/workflows/snapshot.yml runs every 6 hours, commits data/snapshots/YYYY-MM-DD/HHMM.csv.gz
tests/test_snapshot.py         paging, de-duplication and file format, with a mocked API
```

Fields: event, category, venue, city, capacity, event time, announce date, SeatGeek score and popularity, listing count, and lowest, median, average and highest price.

## Run it locally

```bash
export SEATGEEK_CLIENT_ID=your_client_id   # free at seatgeek.com/account/develop
python collector/snapshot.py
python -m pytest -q
```

Data: SeatGeek Platform API (https://platform.seatgeek.com/). Prices are listing prices shown by SeatGeek, not completed sales.
