"""Step 1: the BPI Challenge 2017 event log and a flat table of its events.

    ./venv/bin/python download.py

Source: van Dongen, B.F. (2017) BPI Challenge 2017. 4TU.ResearchData. https://doi.org/10.4121/uuid:5f3067df-f10b-45da-b98b-86ae4c7a310b
The loan-application process of a Dutch financial institute, 2016 to early 2017. Used under the 4TU.ResearchData General
Terms of Use (non-commercial, with attribution). The log (XES, an XML format) goes to data/raw/ and is not committed.
"""
import gzip
import ssl
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd

RAW = Path(__file__).parent / "data" / "raw"
URL = "https://data.4tu.nl/file/34c3f44b-3101-4ea9-8281-e38905c68b8d/f3aec4f7-d52c-4217-82f4-57d719a8298c"
CASE_ATTRS = {"concept:name": "case", "ApplicationType": "application_type", "LoanGoal": "loan_goal", "RequestedAmount": "requested_amount"}
EVENT_ATTRS = {"concept:name": "activity", "lifecycle:transition": "lifecycle", "time:timestamp": "time", "org:resource": "resource",
               "EventOrigin": "origin", "Action": "action", "OfferID": "offer_id", "OfferedAmount": "offered_amount",
               "MonthlyCost": "monthly_cost", "NumberOfTerms": "terms", "CreditScore": "credit_score", "Accepted": "accepted",
               "Selected": "selected"}


def parse(path):
    """Stream the XES file: one row per event, with its case's attributes copied on."""
    rows, start = [], 0
    for kind, el in ET.iterparse(gzip.open(path), events=("start", "end")):
        tag = el.tag.split("}")[-1]
        if kind == "start":
            if tag == "trace":
                start = len(rows)                                  # this trace's events begin here
            continue
        if tag == "event":
            rows.append({EVENT_ATTRS[a.get("key")]: a.get("value") for a in el if a.get("key") in EVENT_ATTRS})
            el.clear()
        elif tag == "trace":
            case = {CASE_ATTRS[a.get("key")]: a.get("value") for a in el if a.get("key") in CASE_ATTRS}
            for ev in rows[start:]:
                ev.update(case)
            el.clear()
    return pd.DataFrame(rows)


if __name__ == "__main__":
    RAW.mkdir(parents=True, exist_ok=True)
    xes = RAW / "BPI_Challenge_2017.xes.gz"
    if not xes.exists():
        ctx = ssl.create_default_context(cafile="/etc/ssl/cert.pem")
        xes.write_bytes(urllib.request.urlopen(URL, context=ctx, timeout=600).read())
    d = parse(xes)
    d.to_pickle(RAW / "events.pkl")
    print(len(d), "events,", d["case"].nunique(), "cases")
