"""Progress across attempts.

usage:
  python tools/trends.py data      # results/trends/trends.json + charts (input for /toefl-trends)
  python tools/trends.py render    # results/trends/trends.html + trends.pdf (includes analysis.json if present)
"""
from __future__ import annotations

import json
import sys
from collections import Counter

from common import RESULTS_DIR, save_json, load_json
from report import env, html_to_pdf

OUT = RESULTS_DIR / "trends"
SECTIONS = ["reading", "listening", "writing", "speaking"]
# categorical slots 1-4 of the reference palette, fixed per section (never by rank)
COLORS = {"reading": "#2a78d6", "listening": "#eb6834", "writing": "#1baf7a", "speaking": "#eda100", "overall": "#0b0b0b"}
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"


def rows() -> list[dict]:
    index = RESULTS_DIR / "index.jsonl"
    if not index.exists():
        sys.exit("No graded attempts yet (results/index.jsonl missing).")
    return [json.loads(l) for l in index.read_text(encoding="utf-8").splitlines() if l.strip()]


def tag_trends(data: list[dict]) -> list[dict]:
    """Per tag: occurrences in the older half vs the recent half of attempts (needs >= 2 attempts)."""
    mid = max(1, len(data) // 2)
    old, new = Counter(), Counter()
    for r in data[:mid]:
        old.update(r.get("error_tags", {}))
    for r in data[mid:]:
        new.update(r.get("error_tags", {}))
    n_old, n_new = mid, max(1, len(data) - mid)
    out = []
    for tag in set(old) | set(new):
        a, b = old[tag] / n_old, new[tag] / n_new
        out.append({"tag": tag, "per_attempt_before": round(a, 2), "per_attempt_recent": round(b, 2),
                    "change": round(b - a, 2), "total": old[tag] + new[tag]})
    return sorted(out, key=lambda x: -x["total"])


def skill_accuracy(data: list[dict]) -> dict:
    agg = {}
    for r in data[-5:]:
        for skill, (c, n) in r.get("skills", {}).items():
            a = agg.setdefault(skill, [0, 0])
            a[0] += c
            a[1] += n
    return {k: {"correct": c, "total": n, "accuracy": round(c / n, 2)} for k, (c, n) in sorted(agg.items(), key=lambda x: x[1][0] / x[1][1])}


def charts(data: list[dict]) -> list[str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": MUTED, "xtick.color": MUTED,
                         "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False})
    files = []
    x = list(range(1, len(data) + 1))
    labels = [r["date"][5:] if r.get("date") else str(i) for i, r in zip(x, data)]

    fig, ax = plt.subplots(figsize=(8, 3.6), dpi=150)
    for s in SECTIONS + ["overall"]:
        ys = [r.get("bands", {}).get(s) if s != "overall" else r.get("overall_band") for r in data]
        pts = [(xi, y) for xi, y in zip(x, ys) if y is not None]
        if not pts:
            continue
        ax.plot(*zip(*pts), color=COLORS[s], lw=2.6 if s == "overall" else 2, ls="--" if s == "overall" else "-",
                marker="o", ms=5, label=s.capitalize(), solid_capstyle="round")
        ax.annotate(f"{s.capitalize()} {pts[-1][1]}", pts[-1], xytext=(6, 0), textcoords="offset points",
                    va="center", color=INK, fontsize=8.5)
    ax.set_ylim(1, 6.2)
    ax.set_yticks([1, 2, 3, 4, 5, 6])
    ax.set_xticks(x, labels, rotation=0 if len(x) < 10 else 45)
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.set_ylabel("Band (1–6)")
    ax.set_title("Bands per attempt", loc="left", color=INK, fontsize=11)
    ax.legend(frameon=False, ncol=5, loc="upper left", bbox_to_anchor=(0, -0.12), fontsize=8.5)
    ax.margins(x=0.12)
    fig.tight_layout()
    fig.savefig(OUT / "bands.png")
    files.append("bands.png")
    plt.close(fig)

    tags = [t for t in tag_trends(data)][:10]
    if tags:
        fig, ax = plt.subplots(figsize=(8, 0.42 * len(tags) + 1.2), dpi=150)
        names = [t["tag"] for t in tags][::-1]
        before = [t["per_attempt_before"] for t in tags][::-1]
        recent = [t["per_attempt_recent"] for t in tags][::-1]
        y = range(len(names))
        ax.barh([i + 0.2 for i in y], before, height=0.36, color="#a9c8ee", label="Earlier attempts")
        ax.barh([i - 0.2 for i in y], recent, height=0.36, color="#2a78d6", label="Recent attempts")
        ax.set_yticks(list(y), names, fontsize=8.5)
        ax.grid(axis="x", color=GRID, lw=0.8)
        ax.set_xlabel("Errors per attempt")
        ax.set_title("Most frequent error types", loc="left", color=INK, fontsize=11)
        ax.legend(frameon=False, loc="lower right", fontsize=8.5)
        fig.tight_layout()
        fig.savefig(OUT / "errors.png")
        files.append("errors.png")
        plt.close(fig)
    return files


def build_data() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    data = rows()
    summary = {
        "attempts": len(data),
        "full_tests": sum(r["mode"] == "full" for r in data),
        "history": [{k: r.get(k) for k in ("attempt_id", "date", "mode", "test_id", "overall_band", "est_total_120", "bands", "task_scores")} for r in data],
        "error_tag_trends": tag_trends(data),
        "skill_accuracy_last5": skill_accuracy(data),
        "charts": charts(data),
    }
    save_json(OUT / "trends.json", summary)
    print(f"Wrote {OUT / 'trends.json'} ({len(data)} attempts)")
    return summary


def render() -> None:
    summary = load_json(OUT / "trends.json") if (OUT / "trends.json").exists() else build_data()
    analysis = load_json(OUT / "analysis.json") if (OUT / "analysis.json").exists() else None
    html = OUT / "trends.html"
    html.write_text(env().get_template("trends.html.j2").render(s=summary, a=analysis), encoding="utf-8")
    pdf = OUT / "trends.pdf"
    pdf.unlink(missing_ok=True)
    print(f"Wrote {pdf if html_to_pdf(html, pdf) else html}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "data"
    build_data() if cmd == "data" else render()
