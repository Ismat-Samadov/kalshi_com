# Kalshi Data Ingestion – Pipeline Documentation

## Overview

This document describes the API discovery process, pagination mechanics, data
schema, and reliability considerations for the Kalshi browse-page ingestion
pipeline.

---

## A) API Discovery Plan

### Method: Browser Network Inspector

To discover which API endpoints back the browse page (`https://kalshi.com/browse`):

1. Open Chrome/Firefox DevTools → **Network** tab
2. Filter by **Fetch/XHR** and reload the page
3. Scroll down to trigger infinite scroll and watch for new requests
4. Look for requests to `api.elections.kalshi.com` or similar domains
5. Inspect each request: URL, method, query params, request headers, response body

### What was found

| Observation | Value |
|-------------|-------|
| API host | `api.elections.kalshi.com` |
| Endpoint | `GET /v1/search/series` |
| Auth required | None – fully public |
| Pagination | Cursor-based via `next_cursor` field in response |
| Default page size used by UI | 24 items |
| Encoding | gzip (brotli also offered but requires optional package) |
| Rate limiting | Not explicitly stated; 4 req/s worked without 429s during testing |

### Alternative / related endpoints

| Endpoint | Status | Notes |
|----------|--------|-------|
| `GET /v1/events/` | 301 redirect to `/v1/events/` – different data shape | Not used; `/v1/search/series` already provides event + market data |
| `api.kalshi.com` (trade API v2) | DNS does not resolve from tested environment | Trade API uses separate auth tokens |

The `/v1/search/series` endpoint is the **single reliable source of truth**
for the browse page because:
- It is the exact endpoint called by the browser UI's infinite scroll
- It returns all fields shown on the browse cards (series, events, markets, milestones, structured_targets)
- It is fully public (no authentication required)
- Total item count (`total_results_count`) is returned on every page

---

## B) Confirmed Endpoints and Parameters

### Primary endpoint

```
GET https://api.elections.kalshi.com/v1/search/series
```

### Query parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `order_by` | string | No | Sort field: `trending` (default), `volume`, `liquidity`, `newest` |
| `reverse` | bool | No | `false` = descending relevance (default) |
| `with_milestones` | bool | No | `true` = include `milestone_id` on series items |
| `page_size` | integer | No | Items per page (default 24, tested up to 50) |
| `hydrate` | string | No | Comma-separated: `milestones,structured_targets` returns hydrated objects in `hydrated_data` |
| `cursor` | string | No | Opaque cursor from `next_cursor` in previous response |

### Example request

```
GET /v1/search/series?order_by=trending&reverse=false&with_milestones=true&page_size=24&hydrate=milestones,structured_targets&cursor=<CURSOR>
Accept: application/json
Accept-Encoding: gzip, deflate
User-Agent: KalshiIngestionBot/1.0
```

### Response structure

```jsonc
{
  "total_results_count": 40378,      // total items across ALL pages
  "next_cursor": "CNDz3hsSCktY...", // pass as ?cursor= to get next page
  "current_page": [                  // array of series/event items
    {
      "series_ticker": "KXPGATOUR",
      "event_ticker": "KXPGATOUR-THGI26",
      "event_title": "The Genesis Invitational Winner?",
      "category": "Sports",
      "total_volume": 12800768,
      "total_market_count": 72,
      "active_market_count": 72,
      "markets": [ ... ],           // embedded market contracts
      "milestone_id": "aab180cc-...",
      ...
    }
  ],
  "hydrated_data": {
    "milestones": {                  // keyed by milestone UUID
      "<uuid>": { "id": "...", "title": "...", ... }
    },
    "structured_targets": {          // keyed by target UUID
      "<uuid>": { "id": "...", "name": "Scottie Scheffler", "type": "golf_competitor", ... }
    }
  }
}
```

### Pagination exhaustion

The last page is detected by either:
- `next_cursor` is `null` / empty string in the response
- `current_page` is an empty array

---

## C) Normalized Schema

### Entity–Relationship Overview

```
series (event_ticker PK)
  └── markets (market_ticker PK, FK: event_ticker, series_ticker)
        └── structured_targets (structured_target_id PK)
series ──FK──> milestones (milestone_id PK)
```

### Tables / Files

#### `data/series.jsonl`
One row per event card on the browse page.

Primary key: `event_ticker`

Key columns: `series_ticker`, `event_ticker`, `category`, `total_volume`,
`total_market_count`, `active_market_count`, `is_trending`, `ingestion_timestamp`

#### `data/markets.jsonl`
One row per market contract within an event.

Primary key: `market_ticker`

Key columns: `market_ticker`, `event_ticker`, `series_ticker`, `yes_bid`,
`yes_ask`, `last_price`, `close_ts`, `open_ts`, `volume`, `result`,
`structured_target_id`, `ingestion_timestamp`

#### `data/milestones.jsonl`
One row per unique milestone object returned via `hydrated_data`.

Primary key: `milestone_id`

Key columns: `milestone_id`, `category`, `type`, `competition`, `start_date`,
`title`, `related_event_tickers`, `ingestion_timestamp`

#### `data/structured_targets.jsonl`
One row per competitor / entity referenced by markets.

Primary key: `structured_target_id`

Key columns: `structured_target_id`, `name`, `type`, `details`,
`product_details`, `ingestion_timestamp`

#### `data/malformed.jsonl`
Records that failed minimum schema validation. Each line includes:
- `type`: `"series"` or `"market"`
- `missing_keys`: list of required keys that were absent
- `record`: the raw malformed object

#### `data/raw/series_pages/page_NNNNN.json`
Raw, unmodified API JSON response for page N.
Useful for re-processing without re-fetching.

#### `data/.checkpoints/state.json`
Checkpoint file written after each page. Contains:
```json
{
  "cursor": "<opaque cursor string>",
  "page_index": 42,
  "items_collected": 1008,
  "saved_at": "2026-02-19T15:00:00Z"
}
```

---

## Normalization Rules

| Rule | Implementation |
|------|---------------|
| Stable primary keys | `event_ticker`, `market_ticker`, `milestone_id`, `structured_target_id` |
| Flatten nested objects | `product_metadata.*` fields extracted as flat columns |
| JSON columns for complex nested data | `custom_strike`, `rulebook_variables`, `details`, `product_details` (stored as JSON strings) |
| Deduplication | `IdempotentWriter` loads existing PKs into a `set` before appending |
| Ingestion timestamp | `ingestion_timestamp` (ISO-8601 UTC) added to every record |
| Source provenance | `source_endpoint` and `page_cursor` added to every record |
| Milestones / structured_targets | Stored separately (extracted from `hydrated_data`) and de-duped |

---

## Reliability and Error Handling

### Retry strategy

Uses `tenacity` with exponential backoff:

| HTTP Status | Behavior |
|------------|----------|
| 200 | Success – process page |
| 429 | Wait `Retry-After` header seconds (default 30s), then retry |
| 500–599 | Exponential backoff: 2s → 4s → 8s → 16s → 32s → 64s → 120s (max 7 attempts) |
| 401/403 | **Fail fast** with actionable message (set `KALSHI_API_TOKEN` env var if needed) |
| Other 4xx | Raise immediately – likely a malformed request |

### Rate limiting

- Default: `MIN_REQUEST_INTERVAL = 0.25s` → ≤ 4 requests/second
- Polite for a public API with no documented rate limit
- Adjust `MIN_REQUEST_INTERVAL` in the script constants if needed

### Resumable runs

- Checkpoint is saved after **every page** to `data/.checkpoints/state.json`
- On interruption, re-run with `--resume` (default) to pick up from last cursor
- On success, checkpoint file is deleted

### Idempotency

- `IdempotentWriter` loads all existing primary keys from the JSONL file into memory before appending
- Duplicate records (same PK) are silently skipped
- Re-running the full ingestion over already-complete data produces no new rows

### Schema validation

- Minimum required keys are checked per record type
- Malformed records are written to `data/malformed.jsonl` and do not halt ingestion
- A warning is logged for each malformed record

---

## How to Run

### Prerequisites

```bash
pip install requests tenacity
# Python 3.9+ required
```

### Single command (full ingestion)

```bash
python scripts/scrape_kalshi.py
```

### All options

```
usage: scrape_kalshi.py [-h] [--page-size N] [--order-by FIELD]
                        [--max-pages N] [--resume | --no-resume]
                        [--force-restart]

options:
  --page-size N        Items per page (default: 24)
  --order-by FIELD     trending | volume | liquidity | newest (default: trending)
  --max-pages N        Stop after N pages (for testing)
  --resume             Resume from checkpoint (default: True)
  --no-resume          Ignore checkpoint and restart from beginning
  --force-restart      Delete checkpoint and restart
```

### Examples

```bash
# Full run
python scripts/scrape_kalshi.py

# Quick smoke test
python scripts/scrape_kalshi.py --max-pages 2 --page-size 5

# Resume after interruption
python scripts/scrape_kalshi.py --resume

# Fresh start ignoring checkpoint
python scripts/scrape_kalshi.py --force-restart

# Sort by volume
python scripts/scrape_kalshi.py --order-by volume
```

### Estimated runtime

Full catalogue (~40,000 items at page_size=24 ≈ 1,683 pages):
- ~7 minutes at page_size=50 (lower page count, same data)
- ~15–25 minutes at default page_size=24
- Dominated by network latency, not processing

---

## Compliance and Safety

- **robots.txt**: `Disallow:` (empty) – Kalshi explicitly allows all bots
- **Authentication**: Not required for public browse data
- **No paywall bypass**: This pipeline only accesses publicly available market data
- **Rate limiting**: Conservative 4 req/s by default; backs off on 429
- **User-Agent**: Identifies the pipeline clearly as an ingestion bot

---

## Appendix: API Discovery via Browser DevTools (Step-by-Step)

1. Navigate to `https://kalshi.com/browse` in Chrome
2. Open DevTools: `F12` or `Cmd+Option+I` (Mac)
3. Click the **Network** tab; filter by **Fetch/XHR**
4. Clear existing requests, then scroll the browse page to trigger infinite scroll
5. Look for requests to `api.elections.kalshi.com` with path `/v1/search/series`
6. Click the request → **Headers** tab to see full URL with params
7. Click **Preview** or **Response** tab to inspect the JSON structure
8. Copy the `curl` equivalent via right-click → **Copy as cURL** for offline testing

Key things to note from DevTools:
- The `cursor` parameter value from previous page's `next_cursor`
- Whether `Authorization` header is present (it is not for browse)
- The `Accept-Encoding` header (server may respond with `br`/brotli)
