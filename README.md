# Ticket Price Tracker

How do ticket prices and supply change as an event gets closer, and does that differ for sports, concerts and theater?

Every 6 hours a GitHub Actions job takes two snapshots of upcoming US events in the next 60 days:

- **Ticketmaster** (up to 3,000 events): price range (min and max), on sale status, public sale date, venue and genre.
- **SeatGeek** (3,000 events): SeatGeek's score and popularity for each event, a demand signal. SeatGeek's public API does not return prices to non-partner accounts, so prices come from Ticketmaster.

Following the same event across snapshots gives its price and demand curve by days to event.

**Status:** collecting data. Analysis and dashboard follow once there are a few weeks of snapshots.

## Questions

1. How do the cheapest and top prices move in the last 60 days before an event, by category?
2. Does demand (SeatGeek popularity) rise before prices do?
3. When is the cheapest time to buy, and how much does waiting save or cost?
4. Which events go off sale or sell out first, and what did their prices and demand look like beforehand?

## How it works

```
collector/snapshot.py          SeatGeek events API, one row per event per snapshot
collector/ticketmaster.py      Ticketmaster Discovery API, one row per event per snapshot
.github/workflows/snapshot.yml runs every 6 hours, commits data/snapshots/ and data/tm_snapshots/
tests/test_snapshot.py         paging, de-duplication and file format, with a mocked API
```

Fields: event, category, genre, venue, city, event time, sale status and public sale date, Ticketmaster min and max price, and SeatGeek score and popularity.

## Run it locally

```bash
export SEATGEEK_CLIENT_ID=your_client_id     # free at seatgeek.com/account/develop
export TICKETMASTER_API_KEY=your_key         # free at developer.ticketmaster.com
python collector/ticketmaster.py
python collector/snapshot.py
python -m pytest -q
```

Data: Ticketmaster Discovery API and SeatGeek Platform API. Ticketmaster price ranges are the prices it lists for an event, not completed sales.
