#!/usr/bin/env python3
"""
Fetch ntopng L7 protocol counters and maintain
a rolling 60-minute record of all observed protocols.
"""

import requests
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from suricata_rule_sync import suricata_rule_sync

# ------------------ CONFIG ------------------
NTOP_HOST = "http://127.0.0.1:3000"
NTOP_USER = "admin"
NTOP_PASS = "ntopng"
IFID = 2
HISTORY_FILE = Path("/var/lib/ntopng/protocol_history.json")
OUT_FILE_TXT = Path("/var/lib/ntopng/protocols.txt")
OUT_FILE_JSON = Path("/var/lib/ntopng/protocols_full.json")
LOG_FILE = Path("/var/log/ntop_protocol_export.log")
WINDOW_MINUTES = 60
# --------------------------------------------

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

def fetch_protocols():
    """Fetch current L7 protocols from ntopng REST API."""
    url = f"{NTOP_HOST}/lua/rest/v2/get/flow/l7/counters.lua?ifid={IFID}"
    try:
        resp = requests.get(url, auth=(NTOP_USER, NTOP_PASS), timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("rc") != 0 or "rsp" not in data:
            logging.warning("Unexpected ntopng response: %s", data)
            return []
        return [
            {"name": p["name"], "count": p["count"]}
            for p in data["rsp"]
            if p["name"].lower() not in ("unknown", "ntop")
        ]
    except Exception as e:
        logging.error("Fetch failed: %s", e)
        return []


def load_history():
    """Load previous 60-minute protocol history."""
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE) as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_history(history):
    """Persist updated protocol history."""
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)


def prune_history(history):
    """Remove records older than 60 minutes."""
    cutoff = datetime.utcnow() - timedelta(minutes=WINDOW_MINUTES)
    return [h for h in history if datetime.fromisoformat(h["timestamp"]) > cutoff]


def aggregate_protocols(history):
    """Combine protocol counts across the 60-minute window."""
    agg = {}
    for record in history:
        for p in record["protocols"]:
            name = p["name"]
            agg[name] = agg.get(name, 0) + p["count"]
    return sorted(
        [{"name": k, "count": v} for k, v in agg.items()],
        key=lambda x: (-x["count"], x["name"])
    )


def save_outputs(protocols):
    """Write final TXT and JSON outputs."""
    # Save unique protocol names for Suricata
    with open(OUT_FILE_TXT, "w") as f:
        for p in protocols:
            f.write(p["name"] + "\n")

    # Save aggregated JSON with timestamp
    snapshot = {
        "timestamp": datetime.utcnow().isoformat(),
        "window_minutes": WINDOW_MINUTES,
        "protocols": protocols
    }
    with open(OUT_FILE_JSON, "w") as f:
        json.dump(snapshot, f, indent=2)

    logging.info(
        "Saved %d protocols covering last %d min",
        len(protocols), WINDOW_MINUTES
    )


if __name__ == "__main__":
    now = datetime.utcnow()
    current = fetch_protocols()
    history = load_history()
    history.append({"timestamp": now.isoformat(), "protocols": current})
    history = prune_history(history)
    save_history(history)
    aggregated = aggregate_protocols(history)
    save_outputs(aggregated)

    suricata_rule_sync()
