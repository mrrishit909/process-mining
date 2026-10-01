"""Step 3: charts. The process map is rendered from charts/process_map.dot with Graphviz.

    ./venv/bin/python charts.py   -> charts/01_process_map.png (needs `dot`), 02_stages.png, 03_staff_time.png, 04_channel.png
"""
import json
import shutil
import subprocess
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = Path(__file__).parent
R = HERE / "results"
DOT = shutil.which("dot") or str(Path.home() / "micromamba" / "envs" / "analyst" / "bin" / "dot")
INK, DIM, GRID, BG, BLUE, ORANGE, GRAY = "#f2f2f0", "#8a8a87", "#1d1d1d", "#0b0b0b", "#3987e5", "#d95926", "#9a9a96"
plt.rcParams.update({
    "figure.facecolor": BG, "axes.facecolor": BG, "savefig.facecolor": BG, "text.color": INK,
    "axes.edgecolor": "#3a3a3a", "axes.labelcolor": DIM, "xtick.color": DIM, "ytick.color": DIM,
    "axes.grid": True, "axes.axisbelow": True, "grid.color": GRID, "grid.linewidth": 1,
    "axes.spines.top": False, "axes.spines.right": False,
    "font.family": ["Helvetica Neue", "Arial", "DejaVu Sans"], "font.size": 11, "axes.titlesize": 13,
    "axes.titlelocation": "left", "axes.titlepad": 12,
})
ACTIVITY = {"W_Validate application": "validate application", "W_Complete application": "complete application",
            "W_Call incomplete files": "call about missing documents", "W_Call after offers": "call to chase signed offers",
            "W_Assess potential fraud": "assess potential fraud", "W_Handle leads": "handle leads"}


def save(fig, name):
    fig.tight_layout()
    fig.savefig(HERE / "charts" / name, dpi=150)
    plt.close(fig)


def main():
    subprocess.run([DOT, "-Tpng", "-Gdpi=130", str(HERE / "charts" / "process_map.dot"), "-o", str(HERE / "charts" / "01_process_map.png")], check=True)

    st = pd.read_csv(R / "stages_by_loops.csv", dtype={"loops": str}).set_index("loops")
    fig, ax = plt.subplots(figsize=(10, 4.3))
    parts = [("days_prepare_offer", GRAY, "bank prepares offer"), ("days_customer_returns", BLUE, "customer returns signed offer"),
             ("days_bank_validates", ORANGE, "bank validates documents")]
    y = np.arange(len(st))
    left = np.zeros(len(st))
    for col, color, label in parts:
        ax.barh(y, st[col], left=left, color=color, height=0.6, label=label, edgecolor=BG, linewidth=2)
        left += st[col].values
    for i, (tot, n) in enumerate(zip(st["days_total"], st["cases"])):
        ax.text(tot + 0.3, i, f"{tot:.0f} days", va="center", color=INK, fontsize=10)
    ax.set_yticks(y, [f"{k} loop{'s' if k != '1' else ''}  (n={n:,})" for k, n in zip(st.index, st["cases"])])
    ax.invert_yaxis()
    ax.set_xlim(0, st["days_total"].max() * 1.15)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("average days, accepted applications, by number of 'documents missing' loops")
    ax.legend(frameon=False, labelcolor=INK, loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=3, fontsize=9)
    ax.set_title("Each 'documents missing' loop adds roughly 4-6 days of validation")
    save(fig, "02_stages.png")

    s = pd.read_csv(R / "staff_time_by_activity.csv")
    s = s[s["activity"].isin(ACTIVITY)].sort_values("hands_on_hours")
    fig, ax = plt.subplots(figsize=(10, 3.8))
    ax.barh([ACTIVITY[a] for a in s["activity"]], 100 * s["share_of_hands_on"], color=BLUE, height=0.6)
    for i, (v, n) in enumerate(zip(s["share_of_hands_on"], s["work_items_scheduled"])):
        ax.text(100 * v + 0.6, i, f"{100 * v:.0f}%  ({n:,} work items)", va="center", color=INK, fontsize=9)
    ax.set_xlim(0, 100 * s["share_of_hands_on"].max() * 1.45)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("share of logged hands-on staff time, 2016")
    ax.set_title("A third of staff time goes to chasing customers by phone")
    save(fig, "03_staff_time.png")

    raw = pd.read_csv(R / "channel_raw.csv").set_index("online_only")
    summ = json.loads((R / "summary.json").read_text())["channel"]
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.4))
    labels = ["mail + online", "online only"]
    for ax, col, title, fmt in [(axes[0], "median_days_to_return", "median days to return", "{:.1f}"),
                                (axes[1], "returned", "share of offers returned", "{:.0%}"),
                                (axes[2], "accepted", "share of offers accepted", "{:.0%}")]:
        vals = raw.loc[[0, 1], col].values
        ax.bar(labels, vals, color=[GRAY, BLUE], width=0.55)
        for i, v in enumerate(vals):
            ax.text(i, v * 1.02, fmt.format(v), ha="center", va="bottom", color=INK, fontsize=10)
        ax.set_ylim(0, vals.max() * 1.25)
        ax.set_title(title, fontsize=11)
        ax.grid(axis="x", visible=False)
        ax.set_yticks([])
    fig.suptitle(f"Offers sent online only came back {-summ['days_to_return_pct_diff_online_only_adjusted']:.0f}% faster "
                 f"(adjusted), but were returned a little less often", x=0.01, ha="left", fontsize=13, color=INK)
    save(fig, "04_channel.png")
    print("charts written")


if __name__ == "__main__":
    main()
