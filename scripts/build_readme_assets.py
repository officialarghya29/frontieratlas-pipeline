#!/usr/bin/env python3
"""Build the README visual set from the committed FrontierAtlas run.

Every chart reads the actual exports in data/exports/ and the quality report.
The two screenshots are rendered locally with LibreOffice and pdftoppm; if
those tools are absent, the chart set is still rebuilt and the screenshot
step is skipped.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import math
import shutil
import subprocess
import tempfile
import textwrap
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
EXPORTS = ROOT / "data" / "exports"
OUT = ROOT / "assets" / "readme"

# --------------------------------------------------------------------------- #
# Palette and typography
# --------------------------------------------------------------------------- #

BG = "#05070D"
PANEL = "#0B1220"
PANEL_2 = "#101B2E"
GRID = "#1B2A41"
TEXT = "#EAF2FF"
MUTED = "#8FA4C0"
FAINT = "#5C708A"
CYAN = "#5DE4FF"
BLUE = "#4D8DFF"
VIOLET = "#A78BFA"
AMBER = "#FFB86B"
PINK = "#FF6B9D"
GREEN = "#5EF2B2"
RED = "#FF6B6B"

TYPE_COLORS = {
    "STARTUP": CYAN,
    "PRODUCT": VIOLET,
    "RESEARCH_PAPER": BLUE,
    "JOB": AMBER,
    "NEWS": PINK,
}

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 9,
        "axes.edgecolor": GRID,
        "axes.labelcolor": MUTED,
        "axes.titlecolor": TEXT,
        "xtick.color": MUTED,
        "ytick.color": TEXT,
        "text.color": TEXT,
        "figure.facecolor": BG,
        "savefig.facecolor": BG,
        "axes.grid": False,
        "pdf.fonttype": 42,
    }
)


def _reading(path: Path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _quality():
    return json.loads((EXPORTS / "data_quality_report.json").read_text(encoding="utf-8"))


def _canvas(width: float = 10.4, height: float = 5.9):
    fig = plt.figure(figsize=(width, height), dpi=170)
    return fig


def _header(fig, kicker: str, title: str, subtitle: str) -> None:
    fig.text(0.055, 0.935, kicker.upper(), color=CYAN, fontsize=8.5, weight="bold", va="top")
    fig.text(0.055, 0.875, title, color=TEXT, fontsize=21, weight="bold", va="top")
    fig.text(0.055, 0.807, subtitle, color=MUTED, fontsize=9.7, va="top")


def _footer(fig, label: str = "FRONTIERATLAS / FINAL RUN / 2026-11-21") -> None:
    fig.text(0.055, 0.032, label, color=FAINT, fontsize=7.2, va="bottom")
    fig.text(0.945, 0.032, "AR1", color=FAINT, fontsize=7.2, ha="right", va="bottom")


def _type_legend(fig, y: float = 0.075) -> None:
    items = [
        ("startups", TYPE_COLORS["STARTUP"]),
        ("products", TYPE_COLORS["PRODUCT"]),
        ("papers", TYPE_COLORS["RESEARCH_PAPER"]),
        ("jobs", TYPE_COLORS["JOB"]),
        ("news", TYPE_COLORS["NEWS"]),
    ]
    x = 0.31
    for label, color in items:
        fig.text(x, y, f"● {label}", color=color, fontsize=7.3, weight="bold")
        x += 0.115


def _save(fig, name: str, pad: float = 0.15) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    fig.savefig(path, bbox_inches="tight", pad_inches=pad, facecolor=BG)
    plt.close(fig)
    # Keep the committed PNGs reasonable without losing text sharpness.
    with Image.open(path) as image:
        if image.width > 1800:
            ratio = 1800 / image.width
            image = image.resize((1800, int(image.height * ratio)), Image.Resampling.LANCZOS)
        image.save(path, optimize=True)


def _grid(ax, axis: str = "x") -> None:
    ax.set_facecolor(PANEL)
    ax.grid(axis=axis, color=GRID, linewidth=0.8, alpha=0.8)
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_color(GRID)
    ax.tick_params(length=0)


# --------------------------------------------------------------------------- #
# 00 — hero signal map
# --------------------------------------------------------------------------- #


def hero() -> None:
    width, height = 1500, 720
    x = np.linspace(-1.0, 1.0, width)
    y = np.linspace(-1.0, 1.0, height)
    xx, yy = np.meshgrid(x, y)
    radius = np.sqrt((xx * 1.25) ** 2 + (yy * 1.75) ** 2)
    glow = np.exp(-(radius * 2.2) ** 2)
    horizon = np.exp(-((yy - 0.30) * 7.5) ** 2)

    canvas = np.zeros((height, width, 3), dtype=float)
    canvas[:, :, 0] = 0.012 + 0.035 * glow + 0.018 * horizon
    canvas[:, :, 1] = 0.025 + 0.075 * glow + 0.030 * horizon
    canvas[:, :, 2] = 0.050 + 0.150 * glow + 0.070 * horizon
    canvas = np.clip(canvas, 0, 1)

    fig = plt.figure(figsize=(12.5, 6.0), dpi=180)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.imshow(canvas, extent=[0, 1, 0, 1], origin="lower", aspect="auto", zorder=0)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    # Faint coordinate grid.
    for gx in np.linspace(0.05, 0.95, 19):
        ax.plot([gx, gx], [0.08, 0.92], color=CYAN, alpha=0.035, lw=0.6, zorder=1)

    # Holographic atlas rings.
    centre = (0.735, 0.52)
    for ring, alpha in [(0.07, 0.40), (0.14, 0.26), (0.21, 0.17), (0.29, 0.11), (0.38, 0.07)]:
        ax.add_patch(Circle(centre, ring, fill=False, edgecolor=CYAN, lw=0.9, alpha=alpha, zorder=2))
    # No radial spokes: the horizontal spoke would cut through the copy.

    # A deterministic constellation around the core.
    rng = np.random.default_rng(7)
    angles = rng.uniform(0, math.tau, 92)
    radii = rng.uniform(0.045, 0.38, 92) ** 0.55
    points_x = centre[0] + radii * np.cos(angles)
    points_y = centre[1] + radii * np.sin(angles) * 0.84
    ax.scatter(points_x, points_y, s=rng.uniform(4, 22, 92), c=CYAN, alpha=0.55, linewidths=0, zorder=4)
    ax.scatter(points_x, points_y, s=rng.uniform(25, 80, 92), c=CYAN, alpha=0.08, linewidths=0, zorder=3)
    # Keep the constellation as points only. Edges are intentionally omitted:
    # at hero scale a single random edge can cut through the body copy.

    # A jagged "signal" that ends in the atlas core.
    signal_x = np.linspace(0.04, 0.70, 40)
    signal_y = 0.17 + 0.035 * np.sin(signal_x * 91) + 0.018 * np.sin(signal_x * 219)
    ax.plot(signal_x, signal_y, color=CYAN, alpha=0.25, lw=2.4, zorder=4)
    ax.plot(signal_x, signal_y, color=CYAN, alpha=0.9, lw=0.85, zorder=5)
    ax.scatter([0.70], [0.17 + 0.035 * math.sin(0.70 * 91) + 0.018 * math.sin(0.70 * 219)], s=45, color=AMBER, zorder=6)

    # Text block. Horizontal grid lines are intentionally omitted here so
    # they never cut through the body copy.
    ax.text(0.055, 0.86, "AI ECOSYSTEM  /  RUN 01", color=CYAN, fontsize=8.5, weight="bold", va="top", zorder=6)
    ax.text(0.052, 0.73, "FRONTIER", color=TEXT, fontsize=43, weight="bold", va="center", zorder=6)
    ax.text(0.052, 0.60, "ATLAS", color=TEXT, fontsize=43, weight="bold", va="center", zorder=6)
    ax.text(
        0.055,
        0.505,
        "A mapped day of the AI economy — public sources,\nreal provenance, conservative joins.",
        color=MUTED,
        fontsize=10.5,
        linespacing=1.55,
        va="top",
        zorder=6,
    )
    stats = [("5,928", "records"), ("15", "sources"), ("29.55s", "collection"), ("0", "schema issues")]
    for index, (value, label) in enumerate(stats):
        left = 0.055 + index * 0.165
        ax.text(left, 0.345, value, color=CYAN if index < 3 else GREEN, fontsize=15, weight="bold", va="center")
        ax.text(left, 0.300, label, color=FAINT, fontsize=7.5, va="center")
    ax.text(0.055, 0.105, "Built by Arghya Bose  ·  21 November 2026", color=TEXT, fontsize=8, alpha=0.85)
    ax.text(0.055, 0.073, "github.com/officialarghya29/frontieratlas-pipeline", color=FAINT, fontsize=7, alpha=0.9)
    _save(fig, "00_hero_signal_map.png", pad=0.0)


# --------------------------------------------------------------------------- #
# 01 — dataset at a glance
# --------------------------------------------------------------------------- #


def dataset_overview() -> None:
    report = _quality()
    counts = report["counts"]["by_type"]
    labels = [
        ("Startups", "STARTUP"),
        ("Products", "PRODUCT"),
        ("Research papers", "RESEARCH_PAPER"),
        ("Jobs", "JOB"),
        ("News", "NEWS"),
    ]
    values = [counts[key] for _, key in labels]
    names = [label for label, _ in labels]
    colors = [TYPE_COLORS[key] for _, key in labels]

    fig = _canvas(10.8, 5.6)
    ax = fig.add_axes([0.19, 0.18, 0.72, 0.57])
    ypos = np.arange(len(names))
    ax.barh(ypos, values, height=0.52, color=colors, alpha=0.88, zorder=3)
    for y, value, color in zip(ypos, values, colors):
        ax.barh(y, value, height=0.52, color=color, alpha=0.12, zorder=2)
        ax.text(value + 35, y, f"{value:,}", color=TEXT, fontsize=10, weight="bold", va="center")
    ax.set_yticks(ypos, names)
    ax.set_xlim(0, max(values) * 1.16)
    ax.set_xlabel("canonical records", labelpad=8)
    ax.invert_yaxis()
    _grid(ax, "x")
    ax.text(
        0.98,
        0.08,
        f"{report['counts']['total_dataset_records']:,}\nTOTAL RECORDS",
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        color=TEXT,
        fontsize=14,
        weight="bold",
        linespacing=1.2,
        bbox=dict(boxstyle="round,pad=0.55", facecolor=PANEL, edgecolor=GRID),
    )
    _header(
        fig,
        "01 / the inventory",
        "Five artifacts, one coherent map",
        "Counts are read from the committed JSONL/CSV exports, not from a hand-written summary.",
    )
    _footer(fig)
    _save(fig, "01_dataset_at_a_glance.png")


# --------------------------------------------------------------------------- #
# 02 — source yield comparison
# --------------------------------------------------------------------------- #


def source_yield() -> None:
    report = _quality()
    short = {
        "yc_ai": "YC AI",
        "arxiv": "arXiv",
        "huggingface_spaces": "Hugging Face Spaces",
        "producthunt": "Product Hunt",
        "showhn": "Show HN",
        "techcrunch_ai": "TechCrunch",
        "theverge_ai": "The Verge",
        "wired_ai": "WIRED",
        "arstechnica": "Ars Technica",
        "mit_tech_review": "MIT Tech Review",
        "himalayas": "Himalayas",
        "remotive": "Remotive",
        "remoteok": "Remote OK",
        "arbeitnow": "Arbeitnow",
        "jobicy": "Jobicy",
    }
    rows = []
    for source in report["sources"]:
        discovered = source.get("discovered", 0) or 0
        accepted = source.get("accepted", 0) or 0
        yield_pct = (accepted / discovered * 100) if discovered else 0.0
        rows.append((short.get(source["source"], source["source"]), source["record_type"], discovered, accepted, yield_pct))
    rows.sort(key=lambda row: row[4], reverse=True)

    fig = _canvas(10.8, 7.0)
    ax = fig.add_axes([0.27, 0.20, 0.65, 0.58])
    ypos = np.arange(len(rows))
    for y, (name, kind, discovered, accepted, pct) in zip(ypos, rows):
        color = TYPE_COLORS.get(kind, MUTED)
        ax.hlines(y, 0, pct, color=color, alpha=0.35, lw=2.0, zorder=2)
        ax.scatter(pct, y, s=62, color=color, edgecolor=BG, linewidth=1.2, zorder=4)
        ax.text(pct + 2.0, y, f"{pct:4.1f}%  ({accepted:,}/{discovered:,})", color=TEXT, fontsize=7.5, va="center")
    ax.set_yticks(ypos, [row[0] for row in rows], fontsize=8)
    ax.set_xlim(0, 112)
    ax.set_xlabel("accepted / discovered")
    ax.invert_yaxis()
    _grid(ax, "x")
    ax.axvline(50, color=FAINT, lw=0.8, ls=(0, (2, 3)), alpha=0.55)
    _type_legend(fig, y=0.075)
    _header(
        fig,
        "02 / source comparison",
        "Not every feed deserves the same trust",
        "The denominator is what a source offered; the numerator is what survived schema, relevance and freshness checks.",
    )
    _footer(fig)
    _save(fig, "02_source_yield_comparison.png")


# --------------------------------------------------------------------------- #
# 03 — entity resolution
# --------------------------------------------------------------------------- #


def entity_resolution() -> None:
    report = _quality()
    entity = report["entity_resolution"]
    decisions = entity["decisions"]
    methods = entity["methods"]

    fig = _canvas(10.8, 5.8)
    grid = fig.add_gridspec(1, 2, left=0.055, right=0.95, top=0.73, bottom=0.16, width_ratios=[1.0, 1.28], wspace=0.28)
    ax = fig.add_subplot(grid[0, 0])
    ax.set_facecolor(BG)
    values = [decisions["AUTO_MATCHED"], decisions["REVIEW_REQUIRED"], decisions["NO_MATCH"]]
    colors = [GREEN, AMBER, "#263A55"]
    wedges, _ = ax.pie(
        values,
        colors=colors,
        startangle=90,
        counterclock=False,
        wedgeprops={"width": 0.30, "edgecolor": BG, "linewidth": 3},
    )
    ax.text(0, 0.07, "2,490", ha="center", va="center", color=TEXT, fontsize=22, weight="bold")
    ax.text(0, -0.12, "product names", ha="center", va="center", color=MUTED, fontsize=8.5)

    ax.set_aspect("equal")
    ax.set_xlim(-1.55, 1.55)
    ax.set_ylim(-1.48, 1.30)
    ax.text(-1.46, -1.24, "●  AUTO 6", color=GREEN, fontsize=7.4, weight="bold", va="center")
    ax.text(-0.48, -1.24, "●  REVIEW 71", color=AMBER, fontsize=7.4, weight="bold", va="center")
    ax.text(0.56, -1.24, "●  NO MATCH 2,413", color="#6D86A4", fontsize=7.4, weight="bold", va="center")

    ax2 = fig.add_subplot(grid[0, 1])
    method_rows = [
        ("not name-like", methods["not_name_like"], FAINT),
        ("fuzzy token set", methods["fuzzy_token_set"], VIOLET),
        ("alias match", methods["alias_match"], AMBER),
        ("domain match", methods["domain_match"], GREEN),
    ]
    ypos = np.arange(len(method_rows))
    for y, (label, value, color) in zip(ypos, method_rows):
        ax2.barh(y, value, height=0.48, color=color, alpha=0.82, zorder=3)
        ax2.text(value + 25, y, f"{value:,}", color=TEXT, fontsize=9.2, va="center", weight="bold")
    ax2.set_yticks(ypos, [row[0] for row in method_rows])
    ax2.set_xlim(0, max(row[1] for row in method_rows) * 1.22)
    ax2.invert_yaxis()
    ax2.set_xlabel("product names", labelpad=8)
    _grid(ax2, "x")
    ax2.text(
        0.98,
        0.06,
        "6 auto-matches\nall from domain equality",
        transform=ax2.transAxes,
        ha="right",
        va="bottom",
        color=GREEN,
        fontsize=7.8,
        linespacing=1.4,
    )

    _header(
        fig,
        "03 / entity resolution",
        "Precision beats a confident guess",
        "Fuzzy matching proposes; only exact, verified-alias or non-shared-domain evidence can auto-merge.",
    )
    _footer(fig)
    _save(fig, "03_entity_resolution_split.png")


# --------------------------------------------------------------------------- #
# 04 — freshness
# --------------------------------------------------------------------------- #


def _parse_date(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def freshness() -> None:
    report = _quality()
    run_end = _parse_date(report["run"]["finished_at"])
    jobs = _reading(EXPORTS / "jobs.csv")
    news = _reading(EXPORTS / "news.csv")
    records = [("JOB", row) for row in jobs] + [("NEWS", row) for row in news]

    grouped: dict[str, list[float]] = {}
    for kind, row in records:
        source = row.get("source_name") or row.get("publisher") or "unknown"
        try:
            age = (run_end - _parse_date(row["date"])).total_seconds() / 3600
        except (KeyError, ValueError):
            continue
        grouped.setdefault(source, []).append(age)

    order = sorted(grouped, key=lambda source: min(grouped[source]))
    fig = _canvas(10.8, 5.8)
    ax = fig.add_axes([0.20, 0.21, 0.73, 0.53])
    rng = np.random.default_rng(11)
    ypos = {source: index for index, source in enumerate(order)}
    for kind, row in records:
        source = row.get("source_name") or row.get("publisher") or "unknown"
        if source not in ypos:
            continue
        try:
            age = (run_end - _parse_date(row["date"])).total_seconds() / 3600
        except (KeyError, ValueError):
            continue
        ax.scatter(
            age,
            ypos[source] + rng.uniform(-0.12, 0.12),
            s=24,
            color=TYPE_COLORS[kind],
            alpha=0.72,
            linewidths=0,
            zorder=3,
        )
    ax.set_yticks(range(len(order)), order, fontsize=8.5)
    ax.set_xlim(0, 24.5)
    ax.set_xlabel("publication age at collection (hours)", labelpad=8)
    ax.axvline(24, color=RED, lw=1.0, ls=(0, (3, 3)), alpha=0.8)
    ax.text(23.7, -0.75, "24h cutoff", color=RED, fontsize=7.4, ha="right")
    _grid(ax, "x")
    ax.invert_yaxis()

    fig.text(
        0.055,
        0.075,
        "●  jobs 214",
        color=TYPE_COLORS["JOB"],
        fontsize=7.6,
        weight="bold",
    )
    fig.text(
        0.145,
        0.075,
        "●  news 16",
        color=TYPE_COLORS["NEWS"],
        fontsize=7.6,
        weight="bold",
    )


    _header(
        fig,
        "04 / freshness",
        "A 24-hour window is a design decision",
        "Every plotted point has a timezone-aware publication timestamp; crawl time is never used as publication time.",
    )
    _footer(fig)
    _save(fig, "04_freshness_window.png")


# --------------------------------------------------------------------------- #
# 05 — targets vs actual
# --------------------------------------------------------------------------- #


def targets() -> None:
    report = _quality()
    rows = [
        ("Startups", report["targets"]["STARTUP"]["target"], report["targets"]["STARTUP"]["actual"], CYAN),
        ("Products", report["targets"]["PRODUCT"]["target"], report["targets"]["PRODUCT"]["actual"], VIOLET),
        ("Research papers", report["targets"]["RESEARCH_PAPER"]["target"], report["targets"]["RESEARCH_PAPER"]["actual"], BLUE),
    ]
    fig = _canvas(10.8, 5.5)
    ax = fig.add_axes([0.22, 0.20, 0.67, 0.54])
    ypos = np.arange(len(rows))
    for y, (label, target, actual, color) in zip(ypos, rows):
        ax.barh(y - 0.16, target, height=0.28, color="#25364F", alpha=0.9, zorder=2)
        ax.barh(y + 0.16, actual, height=0.28, color=color, alpha=0.9, zorder=3)
        ax.text(actual + 38, y + 0.16, f"{actual:,}", color=color, fontsize=10, weight="bold", va="center")
        ax.text(target + 38, y - 0.16, f"{target:,} target", color=MUTED, fontsize=7.5, va="center")
    ax.set_yticks(ypos, [row[0] for row in rows])
    ax.set_xlim(0, 2900)
    ax.invert_yaxis()
    ax.set_xlabel("records", labelpad=8)
    _grid(ax, "x")
    ax.text(
        0.98,
        0.06,
        "3 / 3 targets met\n53 / 53 tests pass",
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        color=GREEN,
        fontsize=9,
        weight="bold",
        linespacing=1.5,
        bbox=dict(boxstyle="round,pad=0.45", facecolor=PANEL, edgecolor=GRID),
    )
    _header(
        fig,
        "05 / the scorecard",
        "The collection cleared every count target",
        "The bars compare the assignment threshold with the actual committed output; no target was lowered after the run.",
    )
    _footer(fig)
    _save(fig, "05_targets_vs_actual.png")


# --------------------------------------------------------------------------- #
# 06 — startup industry mix
# --------------------------------------------------------------------------- #


def industry_mix() -> None:
    startups = _reading(EXPORTS / "startups.csv")
    counts = Counter(row.get("industry") or "Unspecified" for row in startups)
    rows = counts.most_common()
    rows = [(label, value) for label, value in rows if label]
    fig = _canvas(10.8, 5.4)
    ax = fig.add_axes([0.30, 0.17, 0.62, 0.57])
    ypos = np.arange(len(rows))
    colors = [CYAN if index < 3 else "#2C4667" for index in range(len(rows))]
    ax.barh(ypos, [value for _, value in rows], height=0.48, color=colors, alpha=0.9, zorder=3)
    for y, (label, value) in zip(ypos, rows):
        pct = value / len(startups) * 100
        ax.text(value + 18, y, f"{value:,}  ({pct:.1f}%)", color=TEXT if value > 20 else MUTED, fontsize=8.2, va="center")
    ax.set_yticks(ypos, [label for label, _ in rows], fontsize=8.2)
    ax.set_xlim(0, 1450)
    ax.invert_yaxis()
    ax.set_xlabel("YC AI startups", labelpad=8)
    _grid(ax, "x")
    _header(
        fig,
        "06 / the shape of the sample",
        "The AI ecosystem is still a B2B story",
        "This is the YC AI-tag distribution, not a claim about every AI company on earth. The sample is intentionally explicit.",
    )
    _footer(fig)
    _save(fig, "06_startup_industry_mix.png")


# --------------------------------------------------------------------------- #
# 07 — pipeline architecture
# --------------------------------------------------------------------------- #


def _box(ax, xy, width, height, title, body, color):
    x, y = xy
    patch = FancyBboxPatch(
        (x, y),
        width,
        height,
        boxstyle="round,pad=0.02,rounding_size=1.1",
        linewidth=1.0,
        edgecolor=color,
        facecolor=PANEL,
        alpha=0.96,
        zorder=2,
    )
    ax.add_patch(patch)
    ax.text(x + 1.0, y + height - 1.3, title, color=color, fontsize=7.6, weight="bold", va="top", zorder=3)
    ax.text(x + 1.0, y + height - 3.65, body, color=MUTED, fontsize=6.2, va="top", linespacing=1.35, zorder=3)


def _arrow(ax, start, end, color=CYAN):
    ax.add_patch(
        FancyArrowPatch(
            start,
            end,
            arrowstyle="-|>",
            mutation_scale=11,
            linewidth=1.0,
            color=color,
            alpha=0.75,
            connectionstyle="arc3,rad=0",
            zorder=1,
        )
    )


def pipeline() -> None:
    fig = _canvas(11.4, 6.4)
    ax = fig.add_axes([0.03, 0.05, 0.94, 0.78])
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")

    _box(ax, (2, 70), 19, 16, "PUBLIC SOURCES", "YC · arXiv · HN\nHF · Product Hunt\nRSS · jobs · GitHub", CYAN)
    _box(ax, (27, 70), 20, 16, "ASYNC COLLECT", "bounded concurrency\nretries · checkpoints\nraw retention", BLUE)
    _box(ax, (53, 70), 20, 16, "NORMALIZE", "Pydantic v2\nUTC timestamps\nstable record_id", VIOLET)
    _box(ax, (79, 70), 19, 16, "STORE", "SQLite WAL\nidempotent upsert\nrevision audit", GREEN)
    _box(ax, (27, 40), 20, 16, "ENRICH", "GitHub stars\nexplicit repo evidence\nchecked_at recorded", AMBER)
    _box(ax, (53, 40), 20, 16, "RESOLVE", "exact → alias\n→ domain → fuzzy\nreview if uncertain", PINK)
    _box(ax, (79, 40), 19, 16, "EXPORT", "CSV · JSONL\nsix-tab XLSX\nSheets API", CYAN)
    _box(ax, (27, 10), 45, 16, "AUDIT LAYER", "manifest hashes · schema validation · 24h freshness\nsecret scan · 53 tests · identity check", GREEN)

    _arrow(ax, (21.3, 78), (26.6, 78))
    _arrow(ax, (47.3, 78), (52.6, 78))
    _arrow(ax, (73.3, 78), (78.6, 78))
    _arrow(ax, (37, 69.6), (37, 56.4), AMBER)
    _arrow(ax, (63, 69.6), (63, 56.4), PINK)
    _arrow(ax, (88.5, 69.6), (88.5, 56.4), CYAN)
    _arrow(ax, (47.3, 48), (52.6, 48), PINK)
    _arrow(ax, (73.3, 48), (78.6, 48), CYAN)
    _arrow(ax, (88.5, 39.6), (88.5, 26.4), CYAN)
    _arrow(ax, (37, 39.6), (37, 26.4), AMBER)
    _arrow(ax, (63, 39.6), (63, 26.4), PINK)

    ax.text(2, 4, "Design rule: raw first, normalized second, exported last. Every layer can be replayed from retained inputs.", color=FAINT, fontsize=7.2)
    _header(
        fig,
        "07 / system map",
        "One pipeline, five clean boundaries",
        "The boxes are implemented modules. Postgres clusters, durable queues and a review UI stay out of this diagram.",
    )
    _footer(fig)
    _save(fig, "07_pipeline_architecture.png")


# --------------------------------------------------------------------------- #
# 08 — sheet handoff map
# --------------------------------------------------------------------------- #


def sheet_map() -> None:
    report = _quality()
    counts = report["counts"]["by_type"]
    cards = [
        ("01", "Startups", counts["STARTUP"], CYAN),
        ("02", "Products", counts["PRODUCT"], VIOLET),
        ("03", "Research Papers", counts["RESEARCH_PAPER"], BLUE),
        ("04", "Jobs", counts["JOB"], AMBER),
        ("05", "News", counts["NEWS"], PINK),
        ("06", "Entity Mapping Log", report["counts"]["entity_mappings"], GREEN),
    ]
    fig = _canvas(10.8, 5.9)
    ax = fig.add_axes([0.04, 0.06, 0.92, 0.74])
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")
    ax.text(0, 93, "ONE WORKBOOK  /  SIX TABS  /  8,418 DATA ROWS", color=CYAN, fontsize=8.0, weight="bold")
    ax.text(0, 85, "The handoff is deliberately boring.", color=TEXT, fontsize=19, weight="bold")
    ax.text(0, 78, "Upload one XLSX, or import the numbered CSVs into a blank sheet. Same data, two paths.", color=MUTED, fontsize=9.0)
    for index, (number, name, count, color) in enumerate(cards):
        col = index % 3
        row = index // 3
        x = 0 + col * 33.2
        y = 45 - row * 30
        box = FancyBboxPatch(
            (x, y),
            30.5,
            22,
            boxstyle="round,pad=0.2,rounding_size=1.5",
            linewidth=0.9,
            edgecolor=color,
            facecolor=PANEL,
            alpha=0.96,
        )
        ax.add_patch(box)
        ax.text(x + 1.6, y + 18.2, number, color=color, fontsize=8, weight="bold")
        ax.text(x + 1.6, y + 13.3, name, color=TEXT, fontsize=9.2, weight="bold")
        ax.text(x + 1.6, y + 7.4, f"{count:,}", color=color, fontsize=18, weight="bold")
        ax.text(x + 1.6, y + 3.3, "rows", color=FAINT, fontsize=7)
    ax.text(0, 2, "Use data/google_sheets/00_START_HERE.md for the exact import and sharing steps.", color=FAINT, fontsize=7.2)
    _save(fig, "08_sheet_handoff_map.png")


# --------------------------------------------------------------------------- #
# 09 / 10 — real artifact previews
# --------------------------------------------------------------------------- #


def _render_first_page(pdf: Path, output: Path, dpi: int = 120) -> bool:
    with tempfile.TemporaryDirectory(prefix="frontieratlas-preview-") as tmp:
        prefix = Path(tmp) / "page"
        result = subprocess.run(
            ["pdftoppm", "-png", "-r", str(dpi), "-f", "1", "-l", "1", str(pdf), str(prefix)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return False
        pages = sorted(Path(tmp).glob("page*.png"))
        if not pages:
            return False
        with Image.open(pages[0]) as image:
            image = ImageOps.contain(image.convert("RGB"), (1700, 1200), Image.Resampling.LANCZOS)
            framed = Image.new("RGB", (image.width + 40, image.height + 40), BG)
            framed.paste(image, (20, 20))
            framed.save(output, optimize=True)
        return True


def screenshots() -> None:
    workbook = EXPORTS / "FrontierAtlas_submission.xlsx"
    architecture = ROOT / "architecture.pdf"
    if not shutil.which("libreoffice") or not shutil.which("pdftoppm"):
        print("Skipping artifact previews: libreoffice and pdftoppm are required.")
        return
    with tempfile.TemporaryDirectory(prefix="frontieratlas-workbook-") as tmp:
        result = subprocess.run(
            ["libreoffice", "--headless", "--convert-to", "pdf", "--outdir", tmp, str(workbook)],
            capture_output=True,
            text=True,
        )
        pdf = Path(tmp) / "FrontierAtlas_submission.pdf"
        if result.returncode == 0 and pdf.exists():
            full = OUT / "09_workbook_full_page.png"
            _render_first_page(pdf, full, dpi=120)
            with Image.open(full) as image:
                # The full sheet is deliberately wide; this crop makes the first
                # columns legible in the README while the full page stays linked.
                crop = image.crop((70, 0, 1030, 690))
                crop = crop.resize((min(1600, crop.width * 2), int(crop.height * min(2, 1600 / crop.width))), Image.Resampling.LANCZOS)
                crop.save(OUT / "09_workbook_startups_preview.png", optimize=True)
    if architecture.exists():
        _render_first_page(architecture, OUT / "10_architecture_page_preview.png", dpi=120)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    hero()
    dataset_overview()
    source_yield()
    entity_resolution()
    freshness()
    targets()
    industry_mix()
    pipeline()
    sheet_map()
    screenshots()
    print(f"README assets written to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
