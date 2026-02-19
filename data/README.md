# Kalshi Data Inventory

Data produced by `scripts/scrape_kalshi.py` ingesting the Kalshi browse
page API (`api.elections.kalshi.com/v1/search/series`).

---

## Dataset Files

| File | Format | Primary Key | Description |
|------|--------|-------------|-------------|
| `series.jsonl` | JSONL | `event_ticker` | One record per event/series card from the browse page |
| `markets.jsonl` | JSONL | `market_ticker` | Individual market contracts (child of series) |
| `milestones.jsonl` | JSONL | `milestone_id` | Milestone objects hydrated alongside series |
| `structured_targets.jsonl` | JSONL | `structured_target_id` | Competitor/target objects (athletes, teams, etc.) |
| `malformed.jsonl` | JSONL | – | Records that failed schema validation (stored for inspection) |
| `raw/series_pages/page_NNNNN.json` | JSON | – | Raw API response for each paginated page |
| `.checkpoints/state.json` | JSON | – | Cursor + progress checkpoint for resumable runs |

---

## Column Reference

### `series.jsonl`

| Column | Type | Notes |
|--------|------|-------|
| `series_ticker` | string | Top-level series identifier (e.g. `KXPGATOUR`) |
| `event_ticker` | string | **PK** – event-level identifier (e.g. `KXPGATOUR-THGI26`) |
| `event_title` | string | Human-readable event title |
| `event_subtitle` | string | Subtitle (competition name) |
| `series_title` | string | Series name (e.g. `PGA Tour`) |
| `category` | string | Top-level category (Sports, Politics, Finance, etc.) |
| `total_series_volume` | integer | Lifetime dollar-cents volume across the series |
| `total_volume` | integer | Volume on this specific event |
| `total_market_count` | integer | Total market contracts in event |
| `active_market_count` | integer | Currently active contracts |
| `is_trending` | boolean | Trending flag |
| `is_new` | boolean | Recently opened flag |
| `is_closing` | boolean | Closing soon flag |
| `is_price_delta` | boolean | Price movement flag |
| `search_score` | number | API-assigned relevance score |
| `fee_type` | string | Fee structure type |
| `fee_multiplier` | number | Fee multiplier |
| `milestone_id` | string | FK → `milestones.milestone_id` (if any) |
| `product_metadata_categories` | JSON string | Array of category tags |
| `product_metadata_competition` | string | Competition name from metadata |
| `product_metadata_scope` | string | Scope (Game / Tournament / etc.) |
| `product_metadata_custom_image_url` | string | Cover image URL |
| `ingestion_timestamp` | ISO-8601 | When this record was ingested |
| `source_endpoint` | string | API URL used |
| `page_cursor` | string | Cursor value for the page this record came from |

### `markets.jsonl`

| Column | Type | Notes |
|--------|------|-------|
| `market_ticker` | string | **PK** – market contract ticker |
| `series_ticker` | string | FK → `series.series_ticker` |
| `event_ticker` | string | FK → `series.event_ticker` |
| `yes_subtitle` / `no_subtitle` | string | Outcome label |
| `yes_bid` / `yes_ask` | integer | Bid/ask in cents (0–100) |
| `last_price` | integer | Last traded price (cents) |
| `yes_bid_dollars` / `yes_ask_dollars` / `last_price_dollars` | string | Dollar-formatted prices |
| `price_delta` / `previous_price` | integer | Price change info |
| `volume` | integer | Contract volume |
| `score` | integer | Ranking score |
| `open_ts` / `close_ts` / `expected_expiration_ts` | ISO-8601 | Lifecycle timestamps |
| `result` | string | Settlement result (empty if open) |
| `structured_target_id` | string | FK → `structured_targets.structured_target_id` |
| `featured_text` | string | Short display label |
| `market_id` | string | Internal UUID (may be empty for some markets) |
| `title` | string | Market title (may be empty; use `yes_subtitle`) |
| `background_color_light_mode` / `background_color_dark_mode` | string | UI hex colors |
| `image_scale` | integer | UI image scale hint |
| `custom_strike` | JSON string | Strike parameters (varies by market type) |
| `rulebook_variables` | JSON string | Rulebook parameters |
| `ingestion_timestamp` | ISO-8601 | Ingestion time |
| `source_endpoint` | string | API URL |
| `page_cursor` | string | Source page cursor |

### `milestones.jsonl`

| Column | Type | Notes |
|--------|------|-------|
| `milestone_id` | string | **PK** (UUID) |
| `category` / `type` | string | Classification |
| `competition` | string | Competition name |
| `start_date` | string | Start date |
| `title` | string | Display title |
| `notification_message` | string | Push notification copy |
| `related_event_tickers` | JSON string | Array of related event tickers |
| `primary_event_tickers` | JSON string | Array of primary event tickers |
| `details` / `product_details` | JSON string | Rich metadata objects |
| `last_updated_ts` | ISO-8601 | Last update timestamp from API |
| `ingestion_timestamp` | ISO-8601 | Ingestion time |

### `structured_targets.jsonl`

| Column | Type | Notes |
|--------|------|-------|
| `structured_target_id` | string | **PK** (UUID) |
| `name` | string | Display name (e.g. player/team name) |
| `type` | string | Target type (e.g. `golf_competitor`) |
| `details` | JSON string | Type-specific details |
| `product_details` | JSON string | Product display details |
| `last_updated_ts` | ISO-8601 | Last update timestamp from API |
| `ingestion_timestamp` | ISO-8601 | Ingestion time |

---

## Row Counts (last full run)

Run `python scripts/scrape_kalshi.py` and then:

```bash
wc -l data/series.jsonl data/markets.jsonl data/milestones.jsonl data/structured_targets.jsonl
```

The full catalogue contains ~40,000+ series/events as of February 2026.

---

## How to Reproduce

```bash
# Install dependencies
pip install requests tenacity

# Full ingestion (all ~1,700 pages at page_size=24)
python scripts/scrape_kalshi.py

# Quick smoke test (3 pages)
python scripts/scrape_kalshi.py --max-pages 3 --page-size 5

# Resume after interruption
python scripts/scrape_kalshi.py --resume

# Force fresh start
python scripts/scrape_kalshi.py --force-restart
```

Estimated runtime for full catalogue: ~15–25 minutes (respects 4 req/s limit).

See `docs/INGESTION.md` for full pipeline documentation.
