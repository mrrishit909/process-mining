# Where a bank's loan process loses time (process mining, BPI Challenge 2017)

Process mining reads a system's event log, the timestamped trail of every step in every case, to show how a process
*really* runs. This project mines the event log of a Dutch financial institute's personal-loan applications in 2016:
31,509 applications and 1,202,267 events. It finds where the time goes and what a digital-transformation programme
should automate first.

Build log: https://mrrishit909.github.io/projects/process-mining/

## Data and licence

van Dongen, B.F. (2017) *BPI Challenge 2017*. 4TU.ResearchData. https://doi.org/10.4121/uuid:5f3067df-f10b-45da-b98b-86ae4c7a310b

Used under the 4TU.ResearchData General Terms of Use: non-commercial use with attribution to the creator. Any further
distribution must carry the same acknowledgement. The log isn't committed; `download.py` fetches it. Only aggregates are
published here.

## Steps

| Step | File | What it does |
|---|---|---|
| 1 | `download.py` | the XES log (an XML event-log standard), streamed into a flat table |
| 2 | `analysis.py` | stages, outcomes, hands-on vs waiting, staff time, rework, offer channel, variants, process map |
| 3 | `charts.py` | process map (Graphviz) and charts |
| 4 | `check.py` | matches the published log statistics; a plain loop recomputes 300 cases; stages and counts reconcile |

## What the log shows

**Outcomes:**
- 54.7% approved (17,228);
- 33.1% cancelled (10,431);
- 11.9% denied (3,752);
- 98 still open when the log ends.

The single most common path (21.7% of applications) runs from application to offer sent to *cancelled*: the customer
never sent the offer back.

**Where the time goes (approved applications; averages, so the stages add up):**

| Stage | Average days | Share |
|---|---:|---:|
| Bank prepares and sends the offer | 1.4 | 8% |
| **Customer returns the signed offer** | **9.9** | **54%** |
| Bank validates the documents | 6.8 | 38% |
| Total | 18.1 | |

The median approved application takes 14.8 days (middle half: 10.2–22.7). Cancelled ones sit for a median of
31.6 days, because an unreturned offer is cancelled after about a month.

**Work vs wait:** the median approved application gets **33 minutes** of logged hands-on staff time in 356 hours
elapsed, which is 0.15%. Hands-on time pairs each start/resume of a work item with its next suspend/complete; 649 of
254,370 stretches over 4 hours are dropped as items left open. The process is almost all waiting.

**Where staff time goes (logged hands-on hours):**

| Work | Share | Work items |
|---|---:|---:|
| Validate application | 40% | 39,012 |
| Complete application | 27% | 31,532 |
| Call customers about missing documents | 17% | 23,055 |
| Call customers to chase signed offers | 15% | 34,656 |

**Rework:** 67% of decided applications loop back at least once because documents are missing. Holding loan goal,
application type, amount and outcome equal, one loop means **29% longer** (95% CI 27–32%). Approved applications
average 13 days with no loops, then 17, 22 and 29 days with one, two and three or more.

**The digital channel:** 4.9% of offers were sent online only. They came back far faster: median 1.8 vs 7.2 days,
**82% faster** after adjusting for loan goal, type, amount and month (95% CI 80–84%). They were returned slightly less
often (51% vs 56%; adjusted odds ratio 0.78, 0.71–0.86), but accepted more often (46% vs 41%). The channel was
chosen, not randomised, so this is a strong lead, not proof.

## What to automate first (ideas the data supports, not tested changes)

1. **Online document upload with an automatic completeness check at submission.** It targets the loops in two-thirds of
   cases (4–6 days each) and the 17% of staff time spent phoning about missing documents.
2. **Online offers with e-signature as the default.** The customer-return wait is 54% of the time, and online-only offers
   came back in a median 1.8 days.
3. **Automated reminders instead of chase calls.** That's 34,656 call work items and 15% of staff time.
4. **An earlier nudge or expiry for silent offers.** Unreturned offers sit about 31 days before cancellation.

## Not done

- Logged hands-on time is a lower bound: work outside the system (or a call left running) isn't measured the same way.
- No conformance checking against a reference model.
- The channel comparison is observational.

## Run it

```
python3 -m venv venv && ./venv/bin/pip install pandas numpy statsmodels matplotlib scipy
./venv/bin/python download.py && ./venv/bin/python analysis.py && ./venv/bin/python charts.py && ./venv/bin/python check.py
# charts.py needs Graphviz's `dot` on PATH (or in ~/micromamba/envs/analyst/bin)
```
