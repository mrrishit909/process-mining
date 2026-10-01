"""The project's check: fails loudly if the parsing, the case metrics or the work-time pairing break.

    ./venv/bin/python check.py

1. the parsed log matches the published BPI Challenge 2017 statistics (31,509 cases, 1,202,267 events, 26 activities)
2. a plain per-case loop recomputes total days and hands-on hours for 300 random cases
3. the three stages add up to the total; process-map and rework counts reconcile with case counts
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

import analysis as A

R = Path(__file__).parent / "results"


def hands_on(ev):
    """Walk one case's workflow events in time order, per item: open on start/resume, close on suspend/complete/abort."""
    total = 0.0
    for _, g in ev[ev["origin"] == "Workflow"].groupby("activity"):
        g = g.sort_values("time", kind="stable")
        rows = list(zip(g["lifecycle"], g["time"]))
        for (life, t), (nlife, nt) in zip(rows, rows[1:]):
            if life in ("start", "resume") and nlife in ("suspend", "complete", "ate_abort"):
                h = (nt - t).total_seconds() / 3600
                if h <= A.WORK_CAP_H:
                    total += h
    return total


def main():
    d = A.load()
    assert (d["case"].nunique(), len(d), d["activity"].nunique()) == (31509, 1202267, 26)
    c = A.cases(d)
    kept, _ = A.work_time(d)
    per_case = kept.groupby("case")["hours"].sum()

    by_case = dict(tuple(d.groupby("case")))
    for case in c.sample(300, random_state=2).index:
        ev = by_case[case]
        outs = ev[ev["activity"].isin(A.OUTCOMES)]
        if len(outs):
            total = (outs["time"].iloc[-1] - ev["time"].min()).total_seconds() / 86400
            assert abs(total - c.loc[case, "days_total"]) < 1e-9
        assert abs(hands_on(ev) - per_case.get(case, 0.0)) < 1e-9

    acc = c[c["outcome"] == "Pending"]
    parts = acc["days_prepare_offer"] + acc["days_customer_returns"] + acc["days_bank_validates"]
    assert np.allclose(parts, acc["days_total"])
    st = pd.read_csv(R / "stages_by_loops.csv")
    assert np.allclose(st[["days_prepare_offer", "days_customer_returns", "days_bank_validates"]].sum(axis=1), st["days_total"], atol=0.01)
    assert st["cases"].sum() == len(acc)

    e = pd.read_csv(R / "process_map_edges.csv")
    assert e.loc[e["activity"] == "A_Create Application", "count"].sum() == 31509
    rw = pd.read_csv(R / "rework.csv")
    assert rw["cases"].sum() == (c["outcome"].isin(["Pending", "Denied"])).sum()
    ch = pd.read_csv(R / "channel_raw.csv")
    assert ch["offers"].sum() == d["activity"].str.startswith("O_Sent").sum()
    s = json.loads((R / "summary.json").read_text())
    print(f"OK: log matches the published statistics; 300 cases' days and hands-on hours recomputed by a plain loop; "
          f"stages add up (accepted median {s['stages_for_accepted_applications']['days_total']['median']:.1f} days, "
          f"{s['work_vs_wait']['median_hands_on_hours_accepted'] * 60:.0f} min hands-on); counts reconcile")


if __name__ == "__main__":
    main()
