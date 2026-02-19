#!/usr/bin/env python3
"""
Kalshi Browse Page Data Ingestion Pipeline
==========================================
Fetches all series/markets/milestones/structured_targets from the Kalshi
elections API via cursor-based pagination.

Usage:
    python scripts/scrape_kalshi.py [--page-size N] [--order-by FIELD] [--max-pages N]

API Base: https://api.elections.kalshi.com/v1/search/series
Auth: None required (public API)
Robots.txt: Disallow: (empty) – all bots allowed
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import requests
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw" / "series_pages"
CHECKPOINT_DIR = DATA_DIR / ".checkpoints"

SERIES_JSONL = DATA_DIR / "series.jsonl"
MARKETS_JSONL = DATA_DIR / "markets.jsonl"
MILESTONES_JSONL = DATA_DIR / "milestones.jsonl"
STRUCTURED_TARGETS_JSONL = DATA_DIR / "structured_targets.jsonl"
MALFORMED_JSONL = DATA_DIR / "malformed.jsonl"

CHECKPOINT_FILE = CHECKPOINT_DIR / "state.json"

# ---------------------------------------------------------------------------
# API constants
# ---------------------------------------------------------------------------
API_BASE = "https://api.elections.kalshi.com/v1/search/series"
DEFAULT_PAGE_SIZE = 24
DEFAULT_ORDER_BY = "trending"
MIN_REQUEST_INTERVAL = 0.25   # seconds between requests (≤ 4 req/s)
MAX_RETRIES = 7

HEADERS = {
    "Accept": "application/json",
    # Explicitly avoid brotli (br) – requests doesn't decode it without
    # the optional `brotli` system package.  gzip/deflate are always safe.
    "Accept-Encoding": "gzip, deflate",
    "User-Agent": (
        "KalshiIngestionBot/1.0 (data pipeline; "
        "https://github.com/kalshi_com; polite crawler)"
    ),
}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("kalshi_scraper")


# ---------------------------------------------------------------------------
# Retry predicate – retry on 429 and 5xx, fail fast on 401/403
# ---------------------------------------------------------------------------
class FatalHTTPError(Exception):
    """Non-retryable HTTP error (4xx except 429)."""
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(f"HTTP {status_code}: {message}")


def is_retryable(exc: BaseException) -> bool:
    """Return True only for transient errors."""
    if isinstance(exc, FatalHTTPError):
        return False
    return True


@retry(
    retry=retry_if_exception(is_retryable),
    stop=stop_after_attempt(MAX_RETRIES),
    wait=wait_exponential(multiplier=1, min=2, max=120),
    before_sleep=before_sleep_log(log, logging.WARNING),
    reraise=True,
)
def fetch_page(
    session: requests.Session,
    cursor: Optional[str],
    page_size: int,
    order_by: str,
) -> dict:
    """Fetch a single page from the Kalshi search/series API."""
    params: dict[str, Any] = {
        "order_by": order_by,
        "reverse": "false",
        "with_milestones": "true",
        "page_size": page_size,
        "hydrate": "milestones,structured_targets",
    }
    if cursor:
        params["cursor"] = cursor

    resp = session.get(API_BASE, params=params, headers=HEADERS, timeout=30)

    if resp.status_code == 429:
        retry_after = int(resp.headers.get("Retry-After", 30))
        log.warning("Rate limited (429). Backing off %ds.", retry_after)
        time.sleep(retry_after)
        raise requests.exceptions.ConnectionError("Rate limited – retrying")

    if resp.status_code in (401, 403):
        raise FatalHTTPError(
            resp.status_code,
            f"Authentication required or forbidden. "
            f"If a token is needed, set KALSHI_API_TOKEN env var. "
            f"Response: {resp.text[:200]}",
        )

    if resp.status_code >= 500:
        log.warning("Server error %d. Will retry.", resp.status_code)
        resp.raise_for_status()  # triggers tenacity retry

    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Schema validation (minimal)
# ---------------------------------------------------------------------------
REQUIRED_SERIES_KEYS = {
    "series_ticker", "event_ticker", "category",
    "total_volume", "markets",
}
REQUIRED_MARKET_KEYS = {
    "ticker", "yes_bid", "yes_ask", "last_price",
    "close_ts", "open_ts",
}


def validate_series(item: dict) -> list[str]:
    """Return list of missing required keys (empty = valid)."""
    return sorted(REQUIRED_SERIES_KEYS - item.keys())


def validate_market(mkt: dict) -> list[str]:
    return sorted(REQUIRED_MARKET_KEYS - mkt.keys())


# ---------------------------------------------------------------------------
# Checkpoint helpers
# ---------------------------------------------------------------------------
def load_checkpoint() -> dict:
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE) as f:
            return json.load(f)
    return {"cursor": None, "page_index": 0, "items_collected": 0}


def save_checkpoint(cursor: Optional[str], page_index: int, items: int) -> None:
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    state = {
        "cursor": cursor,
        "page_index": page_index,
        "items_collected": items,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump(state, f, indent=2)


def clear_checkpoint() -> None:
    if CHECKPOINT_FILE.exists():
        CHECKPOINT_FILE.unlink()


# ---------------------------------------------------------------------------
# Idempotent writers (set-based dedup on primary keys)
# ---------------------------------------------------------------------------
def load_seen_ids(path: Path, id_field: str) -> set[str]:
    """Load already-written primary keys from a JSONL file."""
    seen: set[str] = set()
    if not path.exists():
        return seen
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                if id_field in rec:
                    seen.add(rec[id_field])
            except json.JSONDecodeError:
                pass
    return seen


class IdempotentWriter:
    """Append-only JSONL writer that deduplicates by primary key."""

    def __init__(self, path: Path, id_field: str):
        self.path = path
        self.id_field = id_field
        path.parent.mkdir(parents=True, exist_ok=True)
        self._seen: set[str] = load_seen_ids(path, id_field)
        self._fh = open(path, "a", encoding="utf-8")
        self._new_count = 0

    def write(self, record: dict) -> bool:
        pk = record.get(self.id_field)
        if pk and pk in self._seen:
            return False
        line = json.dumps(record, ensure_ascii=False, default=str)
        self._fh.write(line + "\n")
        if pk:
            self._seen.add(pk)
        self._new_count += 1
        return True

    def close(self) -> None:
        self._fh.flush()
        self._fh.close()

    @property
    def new_count(self) -> int:
        return self._new_count


# ---------------------------------------------------------------------------
# Normalizers
# ---------------------------------------------------------------------------
def normalize_series(item: dict, page_cursor: Optional[str], endpoint: str) -> dict:
    ts = datetime.now(timezone.utc).isoformat()
    return {
        "series_ticker": item.get("series_ticker", ""),
        "series_title": item.get("series_title", ""),
        "event_ticker": item.get("event_ticker", ""),
        "event_title": item.get("event_title", ""),
        "event_subtitle": item.get("event_subtitle", ""),
        "category": item.get("category", ""),
        "total_series_volume": item.get("total_series_volume"),
        "total_volume": item.get("total_volume"),
        "total_market_count": item.get("total_market_count"),
        "active_market_count": item.get("active_market_count"),
        "is_trending": item.get("is_trending"),
        "is_new": item.get("is_new"),
        "is_closing": item.get("is_closing"),
        "is_price_delta": item.get("is_price_delta"),
        "search_score": item.get("search_score"),
        "fee_type": item.get("fee_type"),
        "fee_multiplier": item.get("fee_multiplier"),
        "milestone_id": item.get("milestone_id"),
        # product metadata flattened
        "product_metadata_categories": json.dumps(
            item.get("product_metadata", {}).get("categories"), default=str
        ),
        "product_metadata_competition": item.get("product_metadata", {}).get(
            "competition"
        ),
        "product_metadata_scope": item.get("product_metadata", {}).get("scope"),
        "product_metadata_custom_image_url": item.get("product_metadata", {}).get(
            "custom_image_url"
        ),
        # ingestion metadata
        "ingestion_timestamp": ts,
        "source_endpoint": endpoint,
        "page_cursor": page_cursor or "",
    }


def normalize_market(
    mkt: dict,
    series_ticker: str,
    event_ticker: str,
    page_cursor: Optional[str],
    endpoint: str,
) -> dict:
    ts = datetime.now(timezone.utc).isoformat()
    return {
        "market_ticker": mkt.get("ticker", ""),
        "series_ticker": series_ticker,
        "event_ticker": event_ticker,
        "yes_subtitle": mkt.get("yes_subtitle", ""),
        "no_subtitle": mkt.get("no_subtitle", ""),
        "yes_bid": mkt.get("yes_bid"),
        "yes_ask": mkt.get("yes_ask"),
        "last_price": mkt.get("last_price"),
        "yes_bid_dollars": mkt.get("yes_bid_dollars"),
        "yes_ask_dollars": mkt.get("yes_ask_dollars"),
        "last_price_dollars": mkt.get("last_price_dollars"),
        "price_delta": mkt.get("price_delta"),
        "previous_price": mkt.get("previous_price"),
        "volume": mkt.get("volume"),
        "score": mkt.get("score"),
        "open_ts": mkt.get("open_ts"),
        "close_ts": mkt.get("close_ts"),
        "expected_expiration_ts": mkt.get("expected_expiration_ts"),
        "result": mkt.get("result", ""),
        "structured_target_id": mkt.get("structured_target_id", ""),
        "featured_text": mkt.get("featured_text", ""),
        "market_id": mkt.get("market_id", ""),
        "title": mkt.get("title", ""),
        "background_color_light_mode": mkt.get("background_color_light_mode", ""),
        "background_color_dark_mode": mkt.get("background_color_dark_mode", ""),
        "image_scale": mkt.get("image_scale"),
        "custom_strike": json.dumps(mkt.get("custom_strike"), default=str),
        "rulebook_variables": json.dumps(
            mkt.get("rulebook_variables"), default=str
        ),
        "ingestion_timestamp": ts,
        "source_endpoint": endpoint,
        "page_cursor": page_cursor or "",
    }


def normalize_milestone(
    ms: dict, page_cursor: Optional[str], endpoint: str
) -> dict:
    ts = datetime.now(timezone.utc).isoformat()
    return {
        "milestone_id": ms.get("id", ""),
        "category": ms.get("category", ""),
        "type": ms.get("type", ""),
        "competition": ms.get("competition", ""),
        "start_date": ms.get("start_date"),
        "title": ms.get("title", ""),
        "notification_message": ms.get("notification_message", ""),
        "related_event_tickers": json.dumps(
            ms.get("related_event_tickers"), default=str
        ),
        "primary_event_tickers": json.dumps(
            ms.get("primary_event_tickers"), default=str
        ),
        "details": json.dumps(ms.get("details"), default=str),
        "product_details": json.dumps(ms.get("product_details"), default=str),
        "last_updated_ts": ms.get("last_updated_ts"),
        "ingestion_timestamp": ts,
        "source_endpoint": endpoint,
        "page_cursor": page_cursor or "",
    }


def normalize_structured_target(
    st: dict, page_cursor: Optional[str], endpoint: str
) -> dict:
    ts = datetime.now(timezone.utc).isoformat()
    return {
        "structured_target_id": st.get("id", ""),
        "name": st.get("name", ""),
        "type": st.get("type", ""),
        "details": json.dumps(st.get("details"), default=str),
        "product_details": json.dumps(st.get("product_details"), default=str),
        "last_updated_ts": st.get("last_updated_ts"),
        "ingestion_timestamp": ts,
        "source_endpoint": endpoint,
        "page_cursor": page_cursor or "",
    }


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------
def run(
    page_size: int = DEFAULT_PAGE_SIZE,
    order_by: str = DEFAULT_ORDER_BY,
    max_pages: Optional[int] = None,
    resume: bool = True,
    force_restart: bool = False,
) -> None:
    # --- Setup directories ---
    for d in [DATA_DIR, RAW_DIR, CHECKPOINT_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    # --- Load or reset checkpoint ---
    if force_restart:
        clear_checkpoint()
    checkpoint = load_checkpoint() if resume else {"cursor": None, "page_index": 0, "items_collected": 0}
    start_cursor = checkpoint["cursor"]
    start_page = checkpoint["page_index"]
    total_collected = checkpoint["items_collected"]

    if start_cursor:
        log.info(
            "Resuming from page %d, cursor=%s..., items so far=%d",
            start_page,
            start_cursor[:20],
            total_collected,
        )
    else:
        log.info("Starting fresh ingestion (order_by=%s, page_size=%d)", order_by, page_size)

    # --- Open idempotent writers ---
    series_writer = IdempotentWriter(SERIES_JSONL, "event_ticker")
    markets_writer = IdempotentWriter(MARKETS_JSONL, "market_ticker")
    milestones_writer = IdempotentWriter(MILESTONES_JSONL, "milestone_id")
    st_writer = IdempotentWriter(STRUCTURED_TARGETS_JSONL, "structured_target_id")
    malformed_fh = open(MALFORMED_JSONL, "a", encoding="utf-8")

    session = requests.Session()
    session.headers.update(HEADERS)

    cursor: Optional[str] = start_cursor
    page_idx: int = start_page
    total_results: Optional[int] = None
    last_request_time = 0.0

    try:
        while True:
            if max_pages is not None and page_idx >= start_page + max_pages:
                log.info("Reached max_pages=%d. Stopping.", max_pages)
                break

            # Polite rate limiting
            elapsed = time.monotonic() - last_request_time
            if elapsed < MIN_REQUEST_INTERVAL:
                time.sleep(MIN_REQUEST_INTERVAL - elapsed)

            log.info(
                "Fetching page %d | cursor=%s | collected=%d%s",
                page_idx,
                (cursor[:20] + "...") if cursor else "START",
                total_collected,
                f"/{total_results}" if total_results else "",
            )

            try:
                data = fetch_page(session, cursor, page_size, order_by)
            except FatalHTTPError as e:
                log.error("Fatal HTTP error – aborting: %s", e)
                sys.exit(1)
            except Exception as e:
                log.error("Failed to fetch page %d after retries: %s", page_idx, e)
                save_checkpoint(cursor, page_idx, total_collected)
                log.info("Checkpoint saved. Re-run with --resume to continue.")
                sys.exit(2)

            last_request_time = time.monotonic()
            total_results = data.get("total_results_count", total_results)
            current_page = data.get("current_page", [])
            next_cursor = data.get("next_cursor")
            hydrated = data.get("hydrated_data", {})

            # --- Save raw page ---
            raw_path = RAW_DIR / f"page_{page_idx:05d}.json"
            with open(raw_path, "w", encoding="utf-8") as rf:
                json.dump(data, rf, ensure_ascii=False, default=str)

            # --- Process milestones from hydrated_data ---
            for ms in hydrated.get("milestones", {}).values():
                ms_norm = normalize_milestone(ms, cursor, API_BASE)
                milestones_writer.write(ms_norm)

            # --- Process structured_targets from hydrated_data ---
            for st in hydrated.get("structured_targets", {}).values():
                st_norm = normalize_structured_target(st, cursor, API_BASE)
                st_writer.write(st_norm)

            # --- Process series items ---
            page_new = 0
            for item in current_page:
                missing = validate_series(item)
                if missing:
                    log.warning(
                        "Malformed series (missing %s): %s",
                        missing,
                        item.get("event_ticker", "UNKNOWN"),
                    )
                    malformed_fh.write(
                        json.dumps(
                            {"type": "series", "missing_keys": missing, "record": item},
                            default=str,
                        )
                        + "\n"
                    )
                    continue

                s_norm = normalize_series(item, cursor, API_BASE)
                if series_writer.write(s_norm):
                    page_new += 1

                # Markets
                for mkt in item.get("markets", []):
                    m_missing = validate_market(mkt)
                    if m_missing:
                        malformed_fh.write(
                            json.dumps(
                                {
                                    "type": "market",
                                    "missing_keys": m_missing,
                                    "record": mkt,
                                    "parent_event_ticker": item.get("event_ticker"),
                                },
                                default=str,
                            )
                            + "\n"
                        )
                        continue

                    m_norm = normalize_market(
                        mkt,
                        item.get("series_ticker", ""),
                        item.get("event_ticker", ""),
                        cursor,
                        API_BASE,
                    )
                    markets_writer.write(m_norm)

            total_collected += page_new
            page_idx += 1

            log.info(
                "  → page %d done | new series=%d | total=%d | milestones=%d | structured_targets=%d",
                page_idx - 1,
                page_new,
                series_writer.new_count,
                milestones_writer.new_count,
                st_writer.new_count,
            )

            # Save checkpoint after every page
            save_checkpoint(next_cursor, page_idx, total_collected)

            # Check for end of pagination
            if not next_cursor or not current_page:
                log.info("Pagination exhausted. All pages fetched.")
                clear_checkpoint()
                break

            cursor = next_cursor

    finally:
        series_writer.close()
        markets_writer.close()
        milestones_writer.close()
        st_writer.close()
        malformed_fh.flush()
        malformed_fh.close()

    log.info(
        "Ingestion complete. "
        "Series: %d new | Markets: %d new | Milestones: %d new | "
        "Structured targets: %d new | Pages: %d",
        series_writer.new_count,
        markets_writer.new_count,
        milestones_writer.new_count,
        st_writer.new_count,
        page_idx - start_page,
    )
    log.info("Outputs:")
    log.info("  %s", SERIES_JSONL)
    log.info("  %s", MARKETS_JSONL)
    log.info("  %s", MILESTONES_JSONL)
    log.info("  %s", STRUCTURED_TARGETS_JSONL)
    log.info("  %s  (raw pages)", RAW_DIR)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Kalshi browse page data ingestion pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full run:
  python scripts/scrape_kalshi.py

  # Quick smoke test (2 pages):
  python scripts/scrape_kalshi.py --max-pages 2

  # Resume after interruption:
  python scripts/scrape_kalshi.py --resume

  # Force restart (ignore checkpoint):
  python scripts/scrape_kalshi.py --force-restart

  # Order by volume descending:
  python scripts/scrape_kalshi.py --order-by volume
        """,
    )
    p.add_argument(
        "--page-size",
        type=int,
        default=DEFAULT_PAGE_SIZE,
        help=f"Items per API page (default: {DEFAULT_PAGE_SIZE}, max ~50)",
    )
    p.add_argument(
        "--order-by",
        default=DEFAULT_ORDER_BY,
        choices=["trending", "volume", "liquidity", "newest"],
        help="Sort order for results (default: trending)",
    )
    p.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Stop after this many pages (for testing)",
    )
    p.add_argument(
        "--resume",
        action="store_true",
        default=True,
        help="Resume from saved checkpoint (default: True)",
    )
    p.add_argument(
        "--no-resume",
        dest="resume",
        action="store_false",
        help="Ignore checkpoint and start from beginning",
    )
    p.add_argument(
        "--force-restart",
        action="store_true",
        default=False,
        help="Delete checkpoint and restart (same as --no-resume but also clears checkpoint file)",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(
        page_size=args.page_size,
        order_by=args.order_by,
        max_pages=args.max_pages,
        resume=args.resume,
        force_restart=args.force_restart,
    )
