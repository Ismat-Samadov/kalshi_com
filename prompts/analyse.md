You are a senior data analyst working on a Kalshi dataset extracted from the Kalshi browse/API. Your task is to produce a high-quality analytical report with reproducible chart generation.

Project structure:
.
├── data
├── docs
├── prompts
└── scripts

You MUST:
- Create scripts/generate_charts.py
- Save ALL charts into charts/ directory
- Ensure charts have CLEAR VALUES (labels/annotations or readable axes + values)
- NEVER use pie charts
- Prefer interpretable chart types: bar, line, area, histogram, box/violin (sparingly), scatter, heatmap
- Produce a presentation-style report in docs/REPORT.md focused on insights (not technical details)
- Each insight in REPORT.md must be supported by at least one chart (embedded) or a clearly referenced table/metric

Inputs:
- Data files exist under data/ (likely series/markets/milestones/structured_targets and raw pages)
- Your code must auto-detect what files exist and adapt.

Tasks:
1) Data loading & validation
   - Detect available datasets (jsonl/csv/parquet).
   - Validate row counts, duplicates, missing keys.
   - Build a unified analysis dataframe(s) with stable IDs.
   - Create a small “data quality” section: completeness, duplicate rate, missingness by key columns.

2) Core analysis questions (answer as many as the data supports):
   - What categories/topics dominate browse listings? (by count and by “trending”/rank if present)
   - How does engagement proxy vary (e.g., trending order, liquidity proxies, volume, price, number of markets, or any available metrics)?
   - What is the lifecycle of series/markets? (if open/close times exist; time-to-resolution; frequency of milestones)
   - Identify anomalies/outliers: unusually high activity, sudden changes, extreme values.
   - Compare segments: e.g., Elections vs other verticals (if vertical/category exists), or structured_targets types.
   - If time fields exist: trends over time (new series created per day/week, activity changes).

3) Charts (store in charts/)
   Required minimum set (adapt names to what exists):
   - charts/01_dataset_overview.png: dataset sizes by table + missingness summary visualization (bar chart)
   - charts/02_top_categories.png: top categories/verticals by count (bar)
   - charts/03_top_series_by_metric.png: top N series by a meaningful metric (bar)
   - charts/04_metric_distribution.png: histogram of key metric (volume/liquidity/num_markets/etc.)
   - charts/05_time_trend.png: time-series of new series/markets or activity (line)
   - charts/06_outliers.png: boxplot or scatter highlighting outliers (no pie)
   Every chart must have:
   - title
   - labeled axes
   - readable tick formatting
   - if ranking/top-N, show the numeric values on bars or as annotations
   - deterministic output size (e.g., 1600x900) and consistent styling

4) Report (docs/REPORT.md)
   - Executive summary (5–10 bullet insights)
   - Method (1 short paragraph; no deep technical)
   - Findings sections aligned to charts
   - “So what?” recommendations: what these insights mean for a product/business/user (e.g., which categories to focus on, what trends imply, monitoring signals, data gaps)
   - Embed charts using relative paths:
     ![caption](../charts/<filename>.png)
   - Include a short appendix with key metrics table (counts, unique IDs, min/max/median of key metrics)

5) Reproducibility & ergonomics
   - scripts/generate_charts.py must run end-to-end with one command and produce charts + report.
   - If dependencies are required, output requirements.txt updates or minimal install notes in docs/REPORT.md footer.
   - Use pandas + matplotlib (or plotly, but ensure files saved as PNG and stable).
   - Add a scripts/utils.py only if necessary; otherwise keep it simple.

Deliverables:
- charts/ (create directory if missing) containing all required charts
- scripts/generate_charts.py
- docs/REPORT.md

Important constraints:
- No pie charts.
- Charts must be easy to interpret and include clear values.
- The report must be insight-driven; do not turn it into a technical README.

Start by:
A) Listing which data files are present and what columns appear most important.
B) Proposing the key metrics available in this dataset (do not invent; infer only from columns).
C) Then implement generate_charts.py and write REPORT.md accordingly.
