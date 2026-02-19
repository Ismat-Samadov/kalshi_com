You are a senior data engineer. Your task is to build a RELIABLE, repeatable data ingestion pipeline for Kalshi browse pages.

Project structure:
.
├── data
├── docs
├── prompts
└── scripts

Primary UI entrypoint:
https://kalshi.com/browse

Observed API pattern example (infinite scroll):
https://api.elections.kalshi.com/v1/search/series?order_by=trending&reverse=false&with_milestones=true&page_size=24&hydrate=milestones%2Cstructured_targets&cursor=...

Your job:
1) Start by identifying the MOST RELIABLE source of truth for listing and iterating through ALL browse items. Because the website uses infinite scroll, you must NOT rely on HTML pagination. You must:
   - Inspect browser network calls (describe exact method to identify endpoints)
   - Determine the actual API base(s) used by browse, including any non-elections subdomains
   - Confirm which endpoints provide series/markets/events listing and how cursor pagination works
   - Determine required headers/auth (if any), user agent, cookies, tokens (if needed)
   - If the API is public but rate limited, design for polite throttling and retries

2) Implement a scraper in Python as scripts/scrape_kalshi.py with these requirements:
   - Must fetch all pages via cursor-based pagination until exhaustion
   - Must persist raw responses and normalized outputs
   - Must be idempotent (re-running should not duplicate records)
   - Must support resuming (checkpoint cursor and progress)
   - Must log progress clearly (pages fetched, items collected, current cursor)
   - Must include robust error handling:
     * retry with exponential backoff for 429/5xx
     * fail fast on 401/403 with actionable guidance
     * validate schema and store malformed records separately

3) Output files into data/ with a clean scheme:
   - data/raw/series_pages/page_<n>.json  (raw API pages)
   - data/series.jsonl or data/series.parquet  (normalized series-level records)
   - data/markets.jsonl or data/markets.parquet (if available/hydrated)
   - data/milestones.jsonl (if milestones are present)
   - data/structured_targets.jsonl (if present)
   Include a data/README.md summarizing the datasets, row counts, and key columns.

4) Normalization rules:
   - Use stable primary keys (e.g., series_id, market_id)
   - Flatten nested objects into separate tables/files when needed
   - Preserve important nested fields as JSON columns only if unavoidable
   - Add an ingestion_timestamp column
   - Add source_endpoint and page_cursor metadata

5) Compliance and safety:
   - Respect robots/TOS constraints where applicable
   - Do not attempt to bypass paywalls or authentication
   - Use polite rate limiting by default (e.g., 2–5 requests/sec max) with backoff on 429

6) Deliverables:
   - scripts/scrape_kalshi.py
   - data/README.md with dataset inventory and how to reproduce the scrape
   - docs/INGESTION.md explaining API discovery, pagination, schema, and reliability considerations
   - A short “How to run” section including a single command example

Implementation details:
- Use requests (or httpx) + tenacity for retries.
- Use structured logging.
- Store checkpoints in data/.checkpoints/ (cursor + page index).
- Ensure the pipeline can run headless without requiring manual scrolling.

Before writing code, produce:
A) A concise “API discovery plan” describing how you will confirm endpoints (network inspector strategy).
B) A concrete list of endpoints/params you will use (even if you need to probe them).
C) The normalized schema (tables/files + key columns).

Then implement the code accordingly.
