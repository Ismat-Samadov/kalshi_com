# Kalshi Market Intelligence
### Full Browse Catalogue — Snapshot February 2026

> **40,224 events · 157,530 market contracts · 9,438 entities · $311.9M total volume**
> Data collected via the public Kalshi API. Fully reproducible — see [How to run](#how-to-run).
>
> **Full dataset available on Kaggle:** [ismetsemedov/kalshi](https://www.kaggle.com/datasets/ismetsemedov/kalshi)

---

## Key Numbers at a Glance

| | |
|---|---|
| **40,224** events catalogued | **157,530** market contracts |
| **$311.9M** total volume (all-time) | **$5.36M** single-event record (2024 US Election) |
| **37,806** new markets in January 2026 alone | **7 days** median market lifespan |
| **85.6%** of events are Sports | **26.8%** YES resolution rate |

---

## 1 · What the Catalogue Looks Like

![Dataset Overview & Data Quality](charts/01_dataset_overview.png)

Four tables, zero missing primary keys. The `market_id` and `title` fields are intentionally sparse — markets use `yes_subtitle` instead. Everything else is clean.

---

## 2 · Sports Dominates Count; Politics Dominates Value

![Category Distribution](charts/02_top_categories.png)

Sports accounts for **85.6% of all events** but a small fraction of aggregate volume. Politics has only 1,975 events yet generated a majority of all high-stakes transactions. Entertainment (1,557 events) captures casual users but little trading depth. The category mix tells two different stories depending on whether you measure by count or by dollars.

---

## 3 · The Top 15 Events — Where the Money Actually Goes

![Top Events by Volume](charts/03_top_series_by_volume.png)

The US 2024 Presidential Election ($5.36M), Super Bowl 2026 ($3.59M), and the Fed Chair Nomination ($1.78M) sit in a league of their own. Five of the top ten events are political — despite politics being under 5% of the catalogue. College Football (KXNCAAF-26) is the one Sports event that competes on volume and market depth simultaneously.

---

## 4 · Volume Is Extremely Concentrated

![Volume Distribution](charts/04_volume_distribution.png)

The distribution is a textbook power law. The **median event generates $709 in volume**. The **mean is $7,754** — inflated by a handful of marquee events. On the log scale (right panel), the bulk of the catalogue sits in the $100–$10K range. The top ~50 events likely account for the majority of all-time platform volume.

---

## 5 · Platform Growth — 37× in 15 Months

![Monthly Market Openings](charts/05_monthly_market_openings.png)

From roughly 700 markets/month in October 2024 to **37,806 in January 2026** — a 37× acceleration. This is almost entirely Sports-driven: deeper player-prop coverage, more leagues, more granular game-level markets. January 2026 alone (pre-Super Bowl + NBA mid-season + Australian Open) set the all-time monthly record.

---

## 6 · Two Market Archetypes — Sports Props vs. Macro Bets

![Volume vs Market Count — Outliers](charts/06_volume_vs_market_count.png)

The log–log scatter reveals a structural split:

- **Bottom-right cluster** — Sports: 50–500 markets per event, sub-$10K volume each. High breadth, thin liquidity.
- **Top-left cluster** — Politics/Finance: 2–30 markets per event, $100K–$5M+ volume. Narrow but deep.

Red dots = top-10 events by volume. KXNCAAF-26 (College Football) is the sole outlier in the high-count AND high-volume quadrant.

---

## 7 · Who Are the Entities?

![Structured Target Types](charts/07_structured_target_types.png)

Kalshi maintains a catalogue of 9,438 real-world entities — mostly athletes. The **1,815 Olympic competitors** are the largest single group, built for Paris 2024 coverage. Tennis (1,326) and Basketball teams (1,197) follow. This entity infrastructure is what enables granular prop markets at scale.

---

## 8 · How Long Do Markets Live?

![Market Duration by Category](charts/08_duration_by_category.png)

**Sports markets open and close in days.** Politics markets run for months. Economics tracks monthly data releases (~30 days). The platform must handle both a 1-day basketball game and a 400-day election market within the same infrastructure. The negative-duration outliers (~24 events) are likely timezone edge cases in the source data.

---

## 9 · The Price Distribution Reveals Market Health

![Price Distribution](charts/09_price_distribution.png)

Two sharp spikes — at **0–5¢** and **85–99¢** — tell the story of a catalogue where many contracts are already near-resolved. The thin middle band (10–80¢) contains the genuinely live two-sided markets. Only about **30% of contracts** are in active price discovery. The rest are effectively settled and waiting for formal resolution.

---

## 10 · Outcomes — NO Wins Twice as Often as YES

![Market Outcomes](charts/10_market_outcomes.png)

**56.2% resolve NO, 26.8% YES, 16.6% still open.** The NO dominance is structural: most markets are single-winner propositions (e.g., 72 golfers, one champion). Politics leans more YES (~35%) because most political markets are binary two-way bets. Scalar outcomes (economic data) account for 0.5%.

---

## 11 · The Sports Event Machine

![Milestone Types](charts/11_milestone_types.png)

31,806 milestones form the scheduling backbone. Basketball (9,852), Tennis (6,038), and Soccer (4,120) dominate — reflecting daily or weekly event cadences. Table tennis (2,953) is a surprise at #4, suggesting Kalshi is tapping international table tennis circuits for continuous market supply. Each milestone triggers a batch of new market contracts.

---

## 12 · Seasonality — Sports Runs All Year, Politics Is Cyclical

![Category × Month Heatmap](charts/12_category_month_heatmap.png)

The heatmap makes the growth story concrete. **Sports (top row) lights up progressively brighter** from mid-2024 to early 2026 — continuous acceleration. Politics flared in November 2024 (US election) then went cold. Entertainment spikes in February (Super Bowl, awards season). Crypto and Economics are low-signal, consistent monthly cadences. The platform's fate is tied to the Sports calendar.

---

## So What? — Three Strategic Signals

**1. Political cycle dependency is a real risk.**
The top-volume events are almost all election-year. Between cycles, platform volume likely drops 50–80% unless Economics, Corporate, or Crypto verticals are scaled aggressively.

**2. Sports breadth ≠ Sports depth.**
The 37× growth in market creation is impressive — but median Sports event volume is $709. More markets doesn't mean more liquidity. The next lever is market-maker programs or automated liquidity to turn hundreds of thin markets into tradeable ones.

**3. January 2026 is the new baseline to watch.**
37K markets/month is a step-change. If March–April 2026 sustains ≥20K/month post-Super Bowl, platform growth is structurally real. If it reverts to <10K, it was a seasonal spike.

---

## How to Run

```bash
# 1. Install dependencies
pip install requests tenacity pandas matplotlib numpy

# 2. Full data ingestion (~17 min, ~40K events)
python scripts/scrape_kalshi.py

# 3. Regenerate all charts + stats
python scripts/generate_charts.py
```

Quick smoke test (3 pages only):
```bash
python scripts/scrape_kalshi.py --max-pages 3 --page-size 5
```

Resume after interruption:
```bash
python scripts/scrape_kalshi.py --resume
```

---

## Project Structure

```
.
├── charts/                  ← 12 PNG charts (1600×900)
├── data/
│   ├── series.jsonl         ← 40,224 events
│   ├── markets.jsonl        ← 157,530 contracts
│   ├── milestones.jsonl     ← 31,806 milestones
│   ├── structured_targets.jsonl ← 9,438 entities
│   ├── raw/series_pages/    ← 806 raw API pages
│   └── README.md            ← Column reference
├── docs/
│   ├── REPORT.md            ← Full analytical report
│   └── INGESTION.md         ← API discovery & pipeline docs
└── scripts/
    ├── scrape_kalshi.py     ← Data ingestion pipeline
    └── generate_charts.py   ← Chart generation
```

---

*Snapshot: February 19, 2026 · Source: `api.elections.kalshi.com` (public API, no auth required) · [Full dataset on Kaggle](https://www.kaggle.com/datasets/ismetsemedov/kalshi)*
