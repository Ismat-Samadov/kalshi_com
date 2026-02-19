#!/usr/bin/env python3
"""
Kalshi Dataset – Chart Generation & Report
===========================================
Produces all charts into charts/ and writes docs/REPORT.md.

Usage:
    python scripts/generate_charts.py
"""

import json
import pathlib
import warnings
from collections import Counter
from datetime import datetime, timezone

import matplotlib
matplotlib.use("Agg")          # headless
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT    = pathlib.Path(__file__).parent.parent
DATA    = ROOT / "data"
CHARTS  = ROOT / "charts"
DOCS    = ROOT / "docs"

CHARTS.mkdir(parents=True, exist_ok=True)
DOCS.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------
FIGSIZE  = (16, 9)
DPI      = 100          # 1600×900 px
BG       = "#F8F9FA"
ACCENT   = "#1B4F72"    # dark blue
PALETTE  = [
    "#1B4F72", "#2E86C1", "#1ABC9C", "#F39C12",
    "#C0392B", "#8E44AD", "#16A085", "#D35400",
    "#2C3E50", "#7F8C8D", "#27AE60", "#E74C3C",
]

def style_ax(ax, title="", xlabel="", ylabel=""):
    ax.set_facecolor(BG)
    ax.figure.patch.set_facecolor(BG)
    ax.set_title(title, fontsize=15, fontweight="bold", pad=12)
    ax.set_xlabel(xlabel, fontsize=11)
    ax.set_ylabel(ylabel, fontsize=11)
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(labelsize=10)

def save(fig, name):
    path = CHARTS / name
    fig.savefig(path, dpi=DPI, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    print(f"  Saved {path.name}")
    return path

def fmt_int(v):
    if v >= 1_000_000:
        return f"{v/1_000_000:.1f}M"
    if v >= 1_000:
        return f"{v/1_000:.0f}K"
    return str(v)

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
print("Loading data...")

def load_jsonl(p: pathlib.Path) -> pd.DataFrame:
    rows = [json.loads(l) for l in p.read_text().strip().splitlines() if l.strip()]
    return pd.DataFrame(rows)

series_df  = load_jsonl(DATA / "series.jsonl")
markets_df = load_jsonl(DATA / "markets.jsonl")
ms_df      = load_jsonl(DATA / "milestones.jsonl")
st_df      = load_jsonl(DATA / "structured_targets.jsonl")

print(f"  series={len(series_df):,}  markets={len(markets_df):,}  "
      f"milestones={len(ms_df):,}  structured_targets={len(st_df):,}")

# ---------------------------------------------------------------------------
# Data prep
# ---------------------------------------------------------------------------
series_df["total_volume"]       = pd.to_numeric(series_df["total_volume"],       errors="coerce")
series_df["total_series_volume"]= pd.to_numeric(series_df["total_series_volume"],errors="coerce")
series_df["total_market_count"] = pd.to_numeric(series_df["total_market_count"], errors="coerce")
series_df["active_market_count"]= pd.to_numeric(series_df["active_market_count"],errors="coerce")

markets_df["last_price"] = pd.to_numeric(markets_df["last_price"], errors="coerce")
markets_df["yes_bid"]    = pd.to_numeric(markets_df["yes_bid"],    errors="coerce")
markets_df["yes_ask"]    = pd.to_numeric(markets_df["yes_ask"],    errors="coerce")
markets_df["volume"]     = pd.to_numeric(markets_df["volume"],     errors="coerce")

# Parse timestamps
for col in ("open_ts", "close_ts"):
    markets_df[col] = pd.to_datetime(markets_df[col], utc=True, errors="coerce")

markets_df["open_month"] = markets_df["open_ts"].dt.to_period("M")
markets_df["days_open"]  = (markets_df["close_ts"] - markets_df["open_ts"]).dt.days

# bid-ask spread as liquidity proxy
markets_df["spread"] = markets_df["yes_ask"] - markets_df["yes_bid"]

# category cleanup for series
series_df["category"] = series_df["category"].fillna("").replace("", "Unknown")

# ============================================================================
# CHART 01 – Dataset overview (row counts + missingness)
# ============================================================================
print("Chart 01: Dataset overview...")

tables = {
    "series": series_df,
    "markets": markets_df,
    "milestones": ms_df,
    "structured_targets": st_df,
}

key_cols = {
    "series":  ["event_ticker","category","total_volume","total_market_count"],
    "markets": ["market_ticker","last_price","volume","open_ts","close_ts"],
    "milestones": ["milestone_id","category","type","start_date"],
    "structured_targets": ["structured_target_id","name","type"],
}

fig, axes = plt.subplots(1, 2, figsize=FIGSIZE, facecolor=BG)

# Left: row counts
names  = list(tables.keys())
counts = [len(v) for v in tables.values()]
bars = axes[0].barh(names, counts, color=PALETTE[:4], edgecolor="white")
for bar, cnt in zip(bars, counts):
    axes[0].text(bar.get_width() * 1.01, bar.get_y() + bar.get_height()/2,
                 f"{cnt:,}", va="center", ha="left", fontsize=11, fontweight="bold")
axes[0].set_xlim(0, max(counts) * 1.18)
style_ax(axes[0], "Table Row Counts", "Rows", "")
axes[0].invert_yaxis()

# Right: missingness heatmap-style bar chart
miss_data = {}
for tname, df in tables.items():
    cols = key_cols[tname]
    for c in cols:
        pct = 0.0
        if c in df.columns:
            pct = df[c].isnull().mean() * 100
            if df[c].dtype == object:
                pct = (df[c].isnull() | (df[c] == "")).mean() * 100
        miss_data[f"{tname}.{c}"] = pct

miss_df = pd.Series(miss_data).sort_values(ascending=True)
colors = [PALETTE[1] if v < 5 else PALETTE[4] for v in miss_df]
bars2 = axes[1].barh(miss_df.index, miss_df.values, color=colors, edgecolor="white")
for bar, v in zip(bars2, miss_df.values):
    axes[1].text(bar.get_width() + 0.3, bar.get_y() + bar.get_height()/2,
                 f"{v:.1f}%", va="center", ha="left", fontsize=9)
axes[1].set_xlim(0, max(miss_df.values) * 1.25 + 2)
style_ax(axes[1], "Field Missingness / Emptiness (%)", "Missing %", "")
axes[1].invert_yaxis()

fig.suptitle("Data Quality Overview – Kalshi Dataset", fontsize=17, fontweight="bold", y=1.01)
fig.tight_layout()
save(fig, "01_dataset_overview.png")

# ============================================================================
# CHART 02 – Top categories by event count
# ============================================================================
print("Chart 02: Top categories...")

cat_counts = (series_df
              .groupby("category")
              .agg(event_count=("event_ticker","count"),
                   total_volume=("total_volume","sum"))
              .sort_values("event_count", ascending=False)
              .head(14))

fig, axes = plt.subplots(1, 2, figsize=FIGSIZE, facecolor=BG)

colors = PALETTE[:len(cat_counts)]
bars = axes[0].bar(cat_counts.index, cat_counts["event_count"],
                   color=colors, edgecolor="white")
for bar, v in zip(bars, cat_counts["event_count"]):
    axes[0].text(bar.get_x() + bar.get_width()/2, bar.get_height() + 60,
                 fmt_int(v), ha="center", va="bottom", fontsize=9, fontweight="bold")
axes[0].set_xticklabels(cat_counts.index, rotation=35, ha="right")
style_ax(axes[0], "Events per Category", "Category", "Event Count")
axes[0].yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: fmt_int(x)))

bars2 = axes[1].bar(cat_counts.index, cat_counts["total_volume"] / 1e6,
                    color=colors, edgecolor="white")
for bar, v in zip(bars2, cat_counts["total_volume"]):
    axes[1].text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                 f"{v/1e6:.0f}M", ha="center", va="bottom", fontsize=9, fontweight="bold")
axes[1].set_xticklabels(cat_counts.index, rotation=35, ha="right")
style_ax(axes[1], "Total Volume by Category (Cents)", "Category", "Volume (Millions)")

fig.suptitle("Category Distribution – Count vs Volume", fontsize=17, fontweight="bold", y=1.01)
fig.tight_layout()
save(fig, "02_top_categories.png")

# ============================================================================
# CHART 03 – Top 15 events by volume
# ============================================================================
print("Chart 03: Top events by volume...")

top_events = (series_df
              .nlargest(15, "total_volume")
              [["event_ticker","category","total_volume","total_market_count"]]
              .sort_values("total_volume"))

fig, ax = plt.subplots(figsize=FIGSIZE, facecolor=BG)
cat_color_map = {c: PALETTE[i % len(PALETTE)] for i, c in enumerate(series_df["category"].unique())}
colors = [cat_color_map.get(c, PALETTE[0]) for c in top_events["category"]]

bars = ax.barh(top_events["event_ticker"], top_events["total_volume"] / 1e6,
               color=colors, edgecolor="white", height=0.7)
for bar, row in zip(bars, top_events.itertuples()):
    ax.text(bar.get_width() + 1, bar.get_y() + bar.get_height()/2,
            f"${row.total_volume/1e6:.1f}M  ({row.total_market_count} mkts)",
            va="center", ha="left", fontsize=10, fontweight="bold")

# legend
from matplotlib.patches import Patch
used_cats = top_events["category"].unique()
legend_elements = [Patch(facecolor=cat_color_map[c], label=c) for c in used_cats]
ax.legend(handles=legend_elements, loc="lower right", fontsize=9)

ax.set_xlim(0, top_events["total_volume"].max() / 1e6 * 1.35)
style_ax(ax, "Top 15 Events by Total Volume", "Volume (Millions of Cents)", "Event")
fig.tight_layout()
save(fig, "03_top_series_by_volume.png")

# ============================================================================
# CHART 04 – Volume distribution (histogram + log scale)
# ============================================================================
print("Chart 04: Volume distribution...")

vols = series_df["total_volume"].dropna()
vols_nz = vols[vols > 0]

fig, axes = plt.subplots(1, 2, figsize=FIGSIZE, facecolor=BG)

# Linear histogram (clipped at 99th pct)
p99 = vols_nz.quantile(0.99)
clipped = vols_nz[vols_nz <= p99]
axes[0].hist(clipped / 1e3, bins=50, color=PALETTE[1], edgecolor="white", alpha=0.85)
axes[0].axvline(vols_nz.median() / 1e3, color=PALETTE[4], linewidth=2, linestyle="--",
                label=f"Median: {vols_nz.median()/1e3:.0f}K")
axes[0].axvline(vols_nz.mean() / 1e3, color=PALETTE[2], linewidth=2, linestyle=":",
                label=f"Mean: {vols_nz.mean()/1e3:.0f}K")
axes[0].legend(fontsize=10)
style_ax(axes[0], f"Volume Distribution (≤99th pct = {p99/1e3:.0f}K)", "Volume (K cents)", "Events")
axes[0].xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:.0f}K"))

# Log-scale histogram
log_vols = np.log10(vols_nz)
axes[1].hist(log_vols, bins=60, color=PALETTE[0], edgecolor="white", alpha=0.85)
log_ticks = [1,2,3,4,5,6,7,8,9]
axes[1].set_xticks(log_ticks)
axes[1].set_xticklabels([f"10^{t}" for t in log_ticks])
axes[1].axvline(np.log10(vols_nz.median()), color=PALETTE[4], linewidth=2, linestyle="--",
                label=f"Median: {vols_nz.median():,.0f}")
axes[1].axvline(np.log10(vols_nz.mean()), color=PALETTE[2], linewidth=2, linestyle=":",
                label=f"Mean: {vols_nz.mean():,.0f}")
axes[1].legend(fontsize=10)
style_ax(axes[1], "Volume Distribution (Log₁₀ scale – full range)", "Volume (log₁₀ cents)", "Events")

fig.suptitle("Event Volume Distribution (Total Volume in Cents)", fontsize=17, fontweight="bold", y=1.01)
fig.tight_layout()
save(fig, "04_volume_distribution.png")

# ============================================================================
# CHART 05 – Monthly market openings trend
# ============================================================================
print("Chart 05: Monthly market openings trend...")

monthly = (markets_df
           .dropna(subset=["open_month"])
           .groupby("open_month")
           .size()
           .reset_index(name="markets_opened"))
monthly["open_month_ts"] = monthly["open_month"].dt.to_timestamp()

# filter: only complete months before this data collection
monthly = monthly[monthly["open_month"] >= "2024-01"]
monthly = monthly[monthly["open_month"] <= "2026-02"]

fig, ax = plt.subplots(figsize=FIGSIZE, facecolor=BG)
ax.fill_between(monthly["open_month_ts"], monthly["markets_opened"],
                alpha=0.25, color=PALETTE[1])
ax.plot(monthly["open_month_ts"], monthly["markets_opened"],
        color=PALETTE[0], linewidth=2.5, marker="o", markersize=5)

for _, row in monthly.iterrows():
    if row["markets_opened"] > monthly["markets_opened"].quantile(0.75):
        ax.annotate(fmt_int(int(row["markets_opened"])),
                    (row["open_month_ts"], row["markets_opened"]),
                    textcoords="offset points", xytext=(0, 8),
                    ha="center", fontsize=9, fontweight="bold")

ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%b %Y"))
ax.xaxis.set_major_locator(matplotlib.dates.MonthLocator(interval=2))
plt.xticks(rotation=35, ha="right")
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: fmt_int(x)))
style_ax(ax, "Monthly Market Openings (Jan 2024 – Feb 2026)", "Month", "Markets Opened")
fig.tight_layout()
save(fig, "05_monthly_market_openings.png")

# ============================================================================
# CHART 06 – Outlier detection: volume vs market count scatter
# ============================================================================
print("Chart 06: Outlier scatter...")

df6 = series_df[["event_ticker","category","total_volume","total_market_count"]].dropna()
df6 = df6[df6["total_volume"] > 0]

# label top-10 by volume as outliers
top10 = df6.nlargest(10, "total_volume")

fig, ax = plt.subplots(figsize=FIGSIZE, facecolor=BG)

for cat, grp in df6.groupby("category"):
    c = cat_color_map.get(cat, "#aaa")
    ax.scatter(grp["total_market_count"], grp["total_volume"] / 1e6,
               alpha=0.35, s=12, color=c, label=cat)

# Highlight outliers
ax.scatter(top10["total_market_count"], top10["total_volume"] / 1e6,
           s=80, color=PALETTE[4], zorder=5, edgecolors="black", linewidth=0.8)
for _, row in top10.iterrows():
    label = row["event_ticker"].split("-")[0] + "…"
    ax.annotate(label,
                (row["total_market_count"], row["total_volume"] / 1e6),
                textcoords="offset points", xytext=(6, 4),
                fontsize=8, color=PALETTE[4], fontweight="bold")

ax.set_xscale("log")
ax.set_yscale("log")
ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: fmt_int(int(x))))
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:.1f}M"))
style_ax(ax, "Volume vs. Market Count (log–log) – Outliers Highlighted",
         "Market Count (log)", "Total Volume in Millions (log)")
handles, labels = ax.get_legend_handles_labels()
# deduplicate legend
by_label = dict(zip(labels, handles))
ax.legend(by_label.values(), by_label.keys(), fontsize=8, loc="upper left",
          markerscale=2, ncol=2)
fig.tight_layout()
save(fig, "06_volume_vs_market_count.png")

# ============================================================================
# CHART 07 – Structured target types (competitor types)
# ============================================================================
print("Chart 07: Structured target types...")

st_type_counts = st_df["type"].value_counts().head(12)

fig, ax = plt.subplots(figsize=FIGSIZE, facecolor=BG)
colors = PALETTE[:len(st_type_counts)]
bars = ax.bar(st_type_counts.index, st_type_counts.values, color=colors, edgecolor="white")
for bar, v in zip(bars, st_type_counts.values):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 10,
            f"{v:,}", ha="center", va="bottom", fontsize=10, fontweight="bold")
ax.set_xticklabels(st_type_counts.index, rotation=35, ha="right")
style_ax(ax, "Structured Target Types (Entity Catalogue)", "Type", "Count")
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: fmt_int(int(x))))
fig.tight_layout()
save(fig, "07_structured_target_types.png")

# ============================================================================
# CHART 08 – Market duration boxplot by category
# ============================================================================
print("Chart 08: Duration boxplot by category...")

dur_df = markets_df[["days_open","series_ticker"]].copy()
dur_df = dur_df.merge(
    series_df[["series_ticker","category"]].drop_duplicates("series_ticker"),
    on="series_ticker", how="left"
)
dur_df["category"] = dur_df["category"].fillna("Unknown")
dur_df = dur_df[(dur_df["days_open"] >= 0) & (dur_df["days_open"] <= 730)]

top_cats = dur_df["category"].value_counts().head(10).index.tolist()
plot_df = dur_df[dur_df["category"].isin(top_cats)]
order = (plot_df.groupby("category")["days_open"].median()
         .sort_values(ascending=False).index.tolist())

fig, ax = plt.subplots(figsize=FIGSIZE, facecolor=BG)
data_by_cat = [plot_df[plot_df["category"] == c]["days_open"].dropna().values for c in order]
bp = ax.boxplot(data_by_cat, vert=True, patch_artist=True,
                medianprops=dict(color="black", linewidth=2))
for patch, color in zip(bp["boxes"], PALETTE):
    patch.set_facecolor(color)
    patch.set_alpha(0.75)
ax.set_xticks(range(1, len(order)+1))
ax.set_xticklabels(order, rotation=30, ha="right")

# annotate medians
for i, cat in enumerate(order):
    med = np.median(data_by_cat[i])
    ax.text(i+1, med + 3, f"{med:.0f}d", ha="center", fontsize=9, fontweight="bold", color="black")

style_ax(ax, "Market Duration Distribution by Category (days open)", "Category", "Days Open")
fig.tight_layout()
save(fig, "08_duration_by_category.png")

# ============================================================================
# CHART 09 – Price distribution (market last_price)
# ============================================================================
print("Chart 09: Price distribution (market last_price)...")

prices = markets_df["last_price"].dropna()
prices = prices[(prices >= 0) & (prices <= 100)]

# bin by 5-cent buckets
bins = list(range(0, 105, 5))
counts, edges = np.histogram(prices, bins=bins)
centers = [(edges[i] + edges[i+1])/2 for i in range(len(counts))]

fig, ax = plt.subplots(figsize=FIGSIZE, facecolor=BG)
bars = ax.bar(centers, counts, width=4.5, color=PALETTE[1], edgecolor="white", alpha=0.9)
# highlight extreme bins
for i, (bar, cnt) in enumerate(zip(bars, counts)):
    if cnt > counts.mean() * 1.5:
        bar.set_color(PALETTE[4])
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 200,
            fmt_int(cnt), ha="center", va="bottom", fontsize=8, rotation=90)

ax.axvline(50, color="gray", linewidth=1.5, linestyle="--", label="50¢ midpoint")
ax.set_xticks(range(0, 105, 10))
ax.set_xticklabels([f"{x}¢" for x in range(0, 105, 10)])
ax.legend(fontsize=10)
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: fmt_int(int(x))))
style_ax(ax, "Market Last-Price Distribution (0–100¢ range)", "Price (cents)", "Number of Markets")
fig.tight_layout()
save(fig, "09_price_distribution.png")

# ============================================================================
# CHART 10 – Market outcome rates (yes/no/open)
# ============================================================================
print("Chart 10: Market outcomes...")

outcome_map = {
    "yes": "Resolved YES",
    "no":  "Resolved NO",
    "":    "Still Open",
    "scalar": "Scalar",
}
outcomes = markets_df["result"].fillna("").map(lambda x: outcome_map.get(x, x))
oc = outcomes.value_counts()

fig, axes = plt.subplots(1, 2, figsize=FIGSIZE, facecolor=BG)

colors_out = [PALETTE[2], PALETTE[4], PALETTE[0], PALETTE[3]]
bars = axes[0].bar(oc.index, oc.values, color=colors_out[:len(oc)], edgecolor="white")
for bar, v in zip(bars, oc.values):
    axes[0].text(bar.get_x() + bar.get_width()/2, bar.get_height() + 200,
                 f"{v:,}\n({v/len(markets_df)*100:.1f}%)",
                 ha="center", va="bottom", fontsize=10, fontweight="bold")
style_ax(axes[0], "Market Outcome Distribution", "Outcome", "Market Count")
axes[0].yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: fmt_int(int(x))))

# YES rate by top categories
cat_outcomes = markets_df.copy()
cat_outcomes = cat_outcomes.merge(
    series_df[["series_ticker","category"]].drop_duplicates("series_ticker"),
    on="series_ticker", how="left"
)
top10_cats = series_df["category"].value_counts().head(9).index.tolist()
cat_outcomes = cat_outcomes[cat_outcomes["category"].isin(top10_cats)]
yes_rate = (cat_outcomes.groupby("category")["result"]
            .apply(lambda s: (s == "yes").sum() / len(s) * 100)
            .sort_values(ascending=True))

bars2 = axes[1].barh(yes_rate.index, yes_rate.values,
                     color=PALETTE[2], edgecolor="white", alpha=0.85)
for bar, v in zip(bars2, yes_rate.values):
    axes[1].text(bar.get_width() + 0.3, bar.get_y() + bar.get_height()/2,
                 f"{v:.1f}%", va="center", ha="left", fontsize=10, fontweight="bold")
axes[1].set_xlim(0, yes_rate.max() * 1.25)
style_ax(axes[1], "YES Resolution Rate by Category", "Category", "YES Rate (%)")

fig.suptitle("Market Outcomes & YES Resolution Rates", fontsize=17, fontweight="bold", y=1.01)
fig.tight_layout()
save(fig, "10_market_outcomes.png")

# ============================================================================
# CHART 11 – Top milestone types (sports lifecycle)
# ============================================================================
print("Chart 11: Milestone types...")

ms_type_cnt = ms_df["type"].value_counts().head(12)
ms_cat_cnt  = ms_df["category"].str.lower().value_counts().head(8)

fig, axes = plt.subplots(1, 2, figsize=FIGSIZE, facecolor=BG)

bars = axes[0].barh(ms_type_cnt.index[::-1], ms_type_cnt.values[::-1],
                    color=PALETTE[:len(ms_type_cnt)], edgecolor="white")
for bar, v in zip(bars, ms_type_cnt.values[::-1]):
    axes[0].text(bar.get_width() + 40, bar.get_y() + bar.get_height()/2,
                 f"{v:,}", va="center", ha="left", fontsize=10, fontweight="bold")
axes[0].set_xlim(0, ms_type_cnt.max() * 1.2)
style_ax(axes[0], "Top Milestone Types", "Count", "Type")

bars2 = axes[1].bar(ms_cat_cnt.index, ms_cat_cnt.values,
                    color=PALETTE[:len(ms_cat_cnt)], edgecolor="white")
for bar, v in zip(bars2, ms_cat_cnt.values):
    axes[1].text(bar.get_x() + bar.get_width()/2, bar.get_height() + 30,
                 f"{v:,}", ha="center", va="bottom", fontsize=10, fontweight="bold")
axes[1].set_xticklabels(ms_cat_cnt.index, rotation=30, ha="right")
style_ax(axes[1], "Milestone Category Mix", "Category", "Count")

fig.suptitle("Milestone Landscape – Types & Categories", fontsize=17, fontweight="bold", y=1.01)
fig.tight_layout()
save(fig, "11_milestone_types.png")

# ============================================================================
# CHART 12 – Category volume share heatmap (category × month)
# ============================================================================
print("Chart 12: Category-month heatmap...")

mkt_cat = markets_df.merge(
    series_df[["series_ticker","category"]].drop_duplicates("series_ticker"),
    on="series_ticker", how="left"
)
mkt_cat = mkt_cat.dropna(subset=["open_month","category"])
mkt_cat = mkt_cat[mkt_cat["open_month"] >= "2024-07"]
mkt_cat = mkt_cat[mkt_cat["open_month"] <= "2026-02"]
top8 = series_df["category"].value_counts().head(8).index.tolist()
mkt_cat = mkt_cat[mkt_cat["category"].isin(top8)]

pivot = (mkt_cat
         .groupby(["category", "open_month"])
         .size()
         .unstack("open_month", fill_value=0))
pivot.columns = [str(c) for c in pivot.columns]

fig, ax = plt.subplots(figsize=FIGSIZE, facecolor=BG)
im = ax.imshow(pivot.values, aspect="auto", cmap="YlOrRd")
ax.set_xticks(range(len(pivot.columns)))
ax.set_xticklabels(pivot.columns, rotation=45, ha="right", fontsize=9)
ax.set_yticks(range(len(pivot.index)))
ax.set_yticklabels(pivot.index, fontsize=10)

# annotate cells
for i in range(len(pivot.index)):
    for j in range(len(pivot.columns)):
        val = pivot.values[i, j]
        text_color = "white" if val > pivot.values.max() * 0.5 else "black"
        ax.text(j, i, fmt_int(int(val)), ha="center", va="center",
                fontsize=8, color=text_color, fontweight="bold")

cbar = fig.colorbar(im, ax=ax, fraction=0.02, pad=0.02)
cbar.set_label("Markets Opened", fontsize=10)
style_ax(ax, "Markets Opened per Category per Month (Jul 2024 – Feb 2026)", "", "")
fig.tight_layout()
save(fig, "12_category_month_heatmap.png")

# ============================================================================
# Summary stats for report
# ============================================================================
print("\nBuilding report stats...")

total_volume_all = series_df["total_volume"].sum()
top_cat = series_df["category"].value_counts().idxmax()
top_cat_pct = series_df["category"].value_counts().iloc[0] / len(series_df) * 100
top_event = series_df.nlargest(1,"total_volume").iloc[0]
yes_rate_overall = (markets_df["result"] == "yes").sum() / len(markets_df) * 100
no_rate_overall  = (markets_df["result"] == "no").sum()  / len(markets_df) * 100
open_rate        = (markets_df["result"] == "").sum()    / len(markets_df) * 100
med_duration     = markets_df["days_open"].dropna().median()
med_vol          = series_df["total_volume"].dropna().median()
max_mkts         = series_df["total_market_count"].max()

stats = {
    "total_series": len(series_df),
    "total_markets": len(markets_df),
    "total_milestones": len(ms_df),
    "total_structured_targets": len(st_df),
    "total_volume_cents": int(total_volume_all),
    "top_category": top_cat,
    "top_category_pct": round(top_cat_pct, 1),
    "top_event_ticker": top_event["event_ticker"],
    "top_event_volume": int(top_event["total_volume"]),
    "yes_rate_pct": round(yes_rate_overall, 1),
    "no_rate_pct":  round(no_rate_overall, 1),
    "open_rate_pct": round(open_rate, 1),
    "median_duration_days": round(med_duration, 1),
    "median_event_volume_cents": int(med_vol),
    "max_markets_per_event": int(max_mkts),
}

for k, v in stats.items():
    print(f"  {k}: {v}")

# Save stats
(ROOT / "data" / "summary_stats.json").write_text(json.dumps(stats, indent=2))

print("\nAll charts saved to charts/")
print("Run complete.")
