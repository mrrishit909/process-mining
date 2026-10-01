"""Step 2: mine the loan-application process for delays, rework and automation candidates.

    ./venv/bin/python analysis.py

Questions a digital-transformation team would ask of this log:
  1. How long does an application take end to end, and in which stage does the time go?
  2. How much of that is people working vs the case waiting?
  3. Where does staff time go, and which work is repetitive enough to automate?
  4. How much rework (incomplete-file loops) is there, and what does it cost in days?
  5. Do offers sent online only come back faster than mail-and-online ones, after adjusting for loan type?
Writes aggregates to results/ and the process map's DOT source to charts/process_map.dot.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

HERE = Path(__file__).parent
OUTCOMES = ["A_Pending", "A_Denied", "A_Cancelled"]          # A_Pending = accepted and being paid out
WORK_CAP_H = 4                                               # a single work stretch longer than this is treated as left open
NAMES = {"A_Create Application": "Application created", "A_Submitted": "Submitted online", "A_Concept": "Draft",
         "A_Accepted": "Taken into processing", "A_Complete": "Application complete", "A_Validating": "Validating documents",
         "A_Incomplete": "Incomplete: documents missing", "A_Pending": "Approved (payout pending)", "A_Denied": "Denied",
         "A_Cancelled": "Application cancelled", "O_Created": "Offer created", "O_Sent (mail and online)": "Offer sent (mail + online)",
         "O_Sent (online only)": "Offer sent (online only)", "O_Returned": "Offer returned by customer", "O_Accepted": "Offer accepted",
         "O_Refused": "Offer refused", "O_Cancelled": "Offer cancelled"}


def load():
    d = pd.read_pickle(HERE / "data" / "raw" / "events.pkl")
    d["time"] = pd.to_datetime(d["time"], utc=True, format="ISO8601")
    d["requested_amount"] = pd.to_numeric(d["requested_amount"])
    return d.sort_values(["case", "time"], kind="stable").reset_index(drop=True)


def cases(d):
    """One row per application: outcome, start, end, the three stage times, rework count, channel of the first offer."""
    first = lambda act: d[d["activity"] == act].groupby("case")["time"].min()
    out = d[d["activity"].isin(OUTCOMES)].groupby("case").agg(outcome=("activity", "last"), end=("time", "last"))
    c = d.groupby("case").agg(start=("time", "min"), application_type=("application_type", "first"), loan_goal=("loan_goal", "first"),
                              requested_amount=("requested_amount", "first")).join(out)
    c["outcome"] = c["outcome"].fillna("open at end of log").str.replace("A_", "")
    sent = d[d["activity"].str.startswith("O_Sent")].groupby("case").agg(first_sent=("time", "min"), channel=("activity", "first"))
    c = c.join(sent)
    c["first_returned"] = first("O_Returned")
    c["channel"] = c["channel"].map({"O_Sent (mail and online)": "mail and online", "O_Sent (online only)": "online only"})
    days = lambda a, b: (b - a).dt.total_seconds() / 86400
    c["days_total"] = days(c["start"], c["end"])
    c["days_prepare_offer"] = days(c["start"], c["first_sent"])
    c["days_customer_returns"] = days(c["first_sent"], c["first_returned"])
    decided = c["outcome"].isin(["Pending", "Denied"])
    c["days_bank_validates"] = days(c["first_returned"], c["end"]).where(decided)
    c["incomplete_loops"] = d[d["activity"] == "A_Incomplete"].groupby("case").size().reindex(c.index, fill_value=0)
    c["offers"] = d[d["activity"] == "O_Created"].groupby("case").size().reindex(c.index, fill_value=0)
    return c


def work_time(d):
    """Hands-on time per workflow item: each start/resume paired with the next suspend/complete/abort of the same
    item (case + activity). Stretches over WORK_CAP_H hours are dropped as items left open."""
    w = d[(d["origin"] == "Workflow") & d["lifecycle"].isin(["start", "resume", "suspend", "complete", "ate_abort"])].copy()
    w = w.sort_values(["case", "activity", "time"], kind="stable")
    nxt_time = w.groupby(["case", "activity"])["time"].shift(-1)
    nxt_life = w.groupby(["case", "activity"])["lifecycle"].shift(-1)
    open_ = w["lifecycle"].isin(["start", "resume"]) & nxt_life.isin(["suspend", "complete", "ate_abort"])
    w = w.assign(hours=(nxt_time - w["time"]).dt.total_seconds() / 3600)[open_]
    kept = w[w["hours"] <= WORK_CAP_H]
    return kept, {"stretches": int(len(w)), "dropped_over_cap": int((w["hours"] > WORK_CAP_H).sum())}


def process_map(d, c, min_share=0.03):
    """Directly-follows graph over application (A_) and offer (O_) events: how often B comes right after A, and the
    median hours between them. Edges used by fewer than min_share of cases are hidden."""
    e = d[d["origin"].isin(["Application", "Offer"]) & (d["activity"] != "O_Create Offer")][["case", "activity", "time"]]
    e = e.assign(nxt=e.groupby("case")["activity"].shift(-1), dt=(e.groupby("case")["time"].shift(-1) - e["time"]).dt.total_seconds() / 3600)
    e = e.dropna(subset=["nxt"])
    edges = e.groupby(["activity", "nxt"]).agg(count=("case", "size"), cases=("case", "nunique"), median_hours=("dt", "median")).reset_index()
    edges = edges[edges["cases"] >= min_share * len(c)].sort_values("count", ascending=False)
    nodes = d[d["origin"].isin(["Application", "Offer"])].groupby("activity")["case"].nunique()
    label = lambda h: f"{h * 60:.0f} min" if h < 1 else (f"{h:.0f} h" if h < 48 else f"{h / 24:.0f} days")
    lines = ['digraph G {', '  rankdir=TB; bgcolor="#0b0b0b"; nodesep=0.35; ranksep=0.45;',
             '  node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=11, color="#3a3a3a", fontcolor="#f2f2f0"];',
             '  edge [fontname="Helvetica", fontsize=9, fontcolor="#c9c9c6"];']
    for act in sorted(set(edges["activity"]) | set(edges["nxt"])):
        fill = "#16324f" if act.startswith("A_") else "#4a2414"
        lines.append(f'  "{act}" [label="{NAMES.get(act, act)}\\n{nodes.get(act, 0):,} cases", fillcolor="{fill}"];')
    top = edges["count"].max()
    for _, r in edges.iterrows():
        width = 0.6 + 4.5 * r["count"] / top
        slow = r["median_hours"] >= 24
        lines.append(f'  "{r["activity"]}" -> "{r["nxt"]}" [label=" {r["count"]:,}\\n {label(r["median_hours"])}", penwidth={width:.2f}, '
                     f'color="{"#d95926" if slow else "#5c5c5a"}"];')
    lines.append('  label="Blue: application states.  Brown: offer states.  Arrows: how many times one step directly follows another, '
                 'and the median time between them; orange = a day or more.  Paths used by under 3% of cases hidden.";')
    lines.append('  labelloc=b; fontname="Helvetica"; fontsize=10; fontcolor="#8a8a87";')
    lines.append("}")
    return edges, "\n".join(lines) + "\n"


def main():
    out = HERE / "results"
    out.mkdir(exist_ok=True)
    (HERE / "charts").mkdir(exist_ok=True)
    d = load()
    c = cases(d)

    summary = {"events": int(len(d)), "cases": int(len(c)), "activities": int(d["activity"].nunique()), "resources": int(d["resource"].nunique()),
               "first_event": str(d["time"].min()), "last_event": str(d["time"].max()),
               "outcomes": c["outcome"].value_counts().to_dict(), "outcome_share": c["outcome"].value_counts(normalize=True).round(4).to_dict()}
    stages = {}
    for col in ["days_total", "days_prepare_offer", "days_customer_returns", "days_bank_validates"]:
        s = c.loc[c["outcome"] == "Pending", col].dropna()
        stages[col] = {"cases": int(len(s)), "median": float(s.median()), "p25": float(s.quantile(0.25)), "p75": float(s.quantile(0.75)), "mean": float(s.mean())}
    summary["stages_for_accepted_applications"] = stages
    summary["median_days_total_by_outcome"] = c.groupby("outcome")["days_total"].median().round(2).to_dict()

    kept, cap = work_time(d)
    per_case = kept.groupby("case")["hours"].sum().reindex(c.index, fill_value=0)
    acc = c["outcome"] == "Pending"
    summary["work_vs_wait"] = {**cap, "median_hands_on_hours_accepted": float(per_case[acc].median()),
                               "median_elapsed_hours_accepted": float(24 * c.loc[acc, "days_total"].median()),
                               "hands_on_share_of_elapsed_accepted": float((per_case[acc] / (24 * c.loc[acc, "days_total"])).median())}
    by_act = kept.groupby("activity").agg(hands_on_hours=("hours", "sum"), stretches=("hours", "size"), median_minutes=("hours", lambda h: 60 * h.median()))
    by_act["share_of_hands_on"] = by_act["hands_on_hours"] / by_act["hands_on_hours"].sum()
    items = d[(d["origin"] == "Workflow") & (d["lifecycle"] == "schedule")].groupby("activity").size()
    system = d[d["origin"] == "Workflow"].groupby("activity")["resource"].apply(lambda r: (r == "User_1").mean())
    by_act = by_act.join(items.rename("work_items_scheduled")).join(system.rename("share_of_events_by_system_user"))
    by_act.sort_values("hands_on_hours", ascending=False).round(4).to_csv(out / "staff_time_by_activity.csv")

    rework = c[c["outcome"].isin(["Pending", "Denied"])].copy()
    rework["loops"] = rework["incomplete_loops"].clip(upper=3).map({0: "0", 1: "1", 2: "2", 3: "3+"})
    rw = rework.groupby("loops").agg(cases=("days_total", "size"), median_days=("days_total", "median"),
                                     median_validation_days=("days_bank_validates", "median"))
    rw["share"] = rw["cases"] / rw["cases"].sum()
    rw.round(4).to_csv(out / "rework.csv")
    accd = c[c["outcome"] == "Pending"].assign(loops=lambda x: x["incomplete_loops"].clip(upper=3).map({0: "0", 1: "1", 2: "2", 3: "3+"}))
    st = accd.groupby("loops")[["days_prepare_offer", "days_customer_returns", "days_bank_validates", "days_total"]].mean()
    st.insert(0, "cases", accd.groupby("loops").size())
    st.round(3).to_csv(out / "stages_by_loops.csv")          # means, so the three stages add up to the total
    m = smf.ols("np.log(days_total) ~ C(loops) + C(loan_goal) + application_type + np.log(requested_amount + 1) + C(outcome)",
                rework[rework["days_total"] > 0]).fit(cov_type="HC3")
    summary["rework"] = {"share_of_decided_cases_with_a_loop": float((rework["incomplete_loops"] > 0).mean()),
                         "one_loop_pct_longer_adjusted": float(100 * (np.exp(m.params["C(loops)[T.1]"]) - 1)),
                         "one_loop_ci": [float(100 * (np.exp(x) - 1)) for x in m.conf_int().loc["C(loops)[T.1]"]]}

    sent = d[d["activity"].str.startswith("O_Sent")][["case", "offer_id", "activity", "time"]].rename(columns={"time": "sent"})
    ret = d[d["activity"] == "O_Returned"].groupby("offer_id")["time"].min().rename("returned")
    acc_o = d[d["activity"] == "O_Accepted"].groupby("offer_id").size().rename("accepted")
    o = sent.join(ret, on="offer_id").join(acc_o, on="offer_id").merge(c[["loan_goal", "application_type", "requested_amount"]], left_on="case", right_index=True)
    o["online_only"] = (o["activity"] == "O_Sent (online only)").astype(int)
    o["returned_flag"] = o["returned"].notna().astype(int)
    o["accepted"] = o["accepted"].fillna(0).clip(upper=1)
    o["days_to_return"] = (o["returned"] - o["sent"]).dt.total_seconds() / 86400
    o["month"] = o["sent"].dt.strftime("%Y-%m")
    raw = o.groupby("online_only").agg(offers=("case", "size"), returned=("returned_flag", "mean"), accepted=("accepted", "mean"),
                                       median_days_to_return=("days_to_return", "median"))
    raw.round(4).to_csv(out / "channel_raw.csv")
    ctl = "C(loan_goal) + application_type + np.log(requested_amount + 1) + C(month)"
    lm_ret = smf.logit(f"returned_flag ~ online_only + {ctl}", o).fit(disp=0)
    back = o[o["returned_flag"] == 1]
    lm_days = smf.ols(f"np.log(days_to_return + 0.01) ~ online_only + {ctl}", back).fit(cov_type="HC3")
    summary["channel"] = {"online_only_share_of_offers": float(o["online_only"].mean()),
                          "returned_odds_ratio_online_only_adjusted": float(np.exp(lm_ret.params["online_only"])),
                          "returned_or_ci": [float(np.exp(x)) for x in lm_ret.conf_int().loc["online_only"]],
                          "days_to_return_pct_diff_online_only_adjusted": float(100 * (np.exp(lm_days.params["online_only"]) - 1)),
                          "days_ci": [float(100 * (np.exp(x) - 1)) for x in lm_days.conf_int().loc["online_only"]]}

    a_seq = d[d["origin"] == "Application"].groupby("case")["activity"].apply(lambda s: " > ".join(a[2:] for a in s))
    var = a_seq.value_counts()
    pd.DataFrame({"cases": var, "share": var / var.sum()}).head(10).round(4).to_csv(out / "variants_top10.csv")
    summary["variants"] = {"distinct_application_paths": int(var.size), "top10_share": float(var.head(10).sum() / var.sum())}

    edges, dot = process_map(d, c)
    edges.round(3).to_csv(out / "process_map_edges.csv", index=False)
    (HERE / "charts" / "process_map.dot").write_text(dot)
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=float) + "\n")
    c.groupby(c["start"].dt.strftime("%Y-%m")).agg(applications=("outcome", "size"), median_days=("days_total", "median"),
                                                   accepted=("outcome", lambda s: (s == "Pending").mean())).round(4).to_csv(out / "by_month.csv")
    print(json.dumps(summary, indent=1, default=float))
    print(pd.read_csv(out / "staff_time_by_activity.csv").to_string(index=False))
    print(rw.round(3).to_string())
    print(raw.round(3).to_string())


if __name__ == "__main__":
    main()
