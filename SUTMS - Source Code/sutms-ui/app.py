#!/usr/bin/env python3
"""
Flask backend for SUTMS UI
 - Provides endpoints that aggregate data from ntopng and Suricata (eve.json).
 - Falls back to local sample data in ./data/ when the real services aren't reachable.
"""

import json
import os
import time
from datetime import datetime, timedelta
from flask import Flask, jsonify, send_from_directory, render_template, request, redirect
import requests
from dateutil import parser as dtparser
import psutil
from utils import get_system_health_stats
from utils_host import get_active_hosts
from utils_interface import get_network_interfaces
from utils_log import read_fast_log, categorize_event

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Load config
with open(os.path.join(BASE_DIR, "config.json")) as f:
    cfg = json.load(f)

NTOP_URL = cfg.get("NTOP_URL")
NTOP_KEY = cfg.get("NTOP_API_KEY") or None
NTOP_FALLBACK = cfg.get("NTOP_USE_SAMPLE_ON_FAIL", True)
SURICATA_PATH = cfg.get("SURICATA_EVE_PATH")
SURICATA_FALLBACK = cfg.get("SURICATA_USE_SAMPLE_ON_FAIL", True)
CACHE_SECONDS = int(cfg.get("CACHE_SECONDS", 30))

# default UI ports for services (used for redirects built from incoming host)
NTOP_UI_PORT = int(cfg.get("NTOP_UI_PORT", 3000))
SURICATA_UI_PORT = int(cfg.get("SURICATA_UI_PORT", 10000))

# Simple in-memory cache to avoid frequent reads
_cached = {}
def cache_get(key):
    entry = _cached.get(key)
    if not entry:
        return None
    ts, val = entry
    if time.time() - ts > CACHE_SECONDS:
        return None
    return val

def cache_set(key, val):
    _cached[key] = (time.time(), val)

app = Flask(__name__, template_folder="templates", static_folder="static")

# ---------- helpers ----------
def read_sample(path):
    p = os.path.join(BASE_DIR, "data", path)
    if os.path.isfile(p):
        with open(p, "r") as f:
            return json.load(f)
    return None

def query_ntop_traffic():
    """Query ntopng for traffic metrics (top talkers / bytes over time).
       This is a pragmatic, robust approach: try ntop endpoints; fallback to sample JSON."""
    cached = cache_get("ntop_traffic")
    if cached:
        return cached

    try:
        # Example: get top N hosts (ntopng REST: /lua/rest/v2/ hosts endpoints differ by versions)
        # We'll try a couple of endpoints and parse results safely.
        headers = {}
        if NTOP_KEY:
            headers["X-API-Key"] = NTOP_KEY

        # 1) /lua/rest/v2/hosts/top10? (older/newer ntop may vary)
        urls_to_try = [
            f"{NTOP_URL}/lua/rest/v2/hosts/top10",      # possible ntop v.2 style
            f"{NTOP_URL}/api/1/hosts/toptalkers",      # other variants
            f"{NTOP_URL}/lua/hosts/get_hosts.lua"      # fallback
        ]
        resp_data = None
        for u in urls_to_try:
            try:
                r = requests.get(u, headers=headers, timeout=4)
                if r.status_code == 200:
                    # attempt JSON decode
                    try:
                        resp_data = r.json()
                    except Exception:
                        # some endpoints return plain text; ignore
                        resp_data = None
                    if resp_data:
                        break
            except Exception:
                continue

        if not resp_data:
            raise RuntimeError("No ntop JSON endpoints responded")

        # Build a consistent response for frontend: top_talkers and traffic_timeseries
        top = []
        # attempt to extract hosts and bytes
        if isinstance(resp_data, list):
            for item in resp_data[:10]:
                # heuristics for item dict
                host = item.get("host") or item.get("ip") or item.get("addr") or item.get("name")
                bytes_tx = item.get("bytes") or item.get("tx_bytes") or item.get("traffic")
                top.append({"host": host, "bytes": bytes_tx})
        else:
            # try to normalize if nested
            # can't guarantee structure across ntop versions — return raw
            top = [{"raw": resp_data}]

        result = {"top_talkers": top, "source": "ntop"}
        cache_set("ntop_traffic", result)
        return result

    except Exception as e:
        app.logger.warning("ntop query failed: %s", e)
        if NTOP_FALLBACK:
            sample = read_sample("sample_ntop.json")
            if sample:
                cache_set("ntop_traffic", sample)
                return sample
        return {"top_talkers": [], "source": "none"}

def read_suricata_stats():
    """Return a dict with parsed Suricata stats pulled from eve.json (latest stats event)
    and the stats.log counters (if present).
    """
    result = {"eve": None, "counters": {}}
    # 1) try parse latest stats event from eve.json
    try:
        if os.path.isfile(SURICATA_PATH):
            with open(SURICATA_PATH, 'r') as fh:
                # read lines from end to find first stats event
                for line in reversed(fh.readlines()):
                    if not line.strip():
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    if obj.get('event_type') == 'stats':
                        result['eve'] = obj.get('stats') or obj
                        break
    except Exception as e:
        app.logger.debug(f"read_suricata_stats: failed reading eve.json: {e}")

    # 2) try to parse stats.log counters for a concise list
    stats_log = '/var/log/suricata/stats.log'
    try:
        if os.path.isfile(stats_log):
            with open(stats_log, 'r') as fh:
                lines = fh.readlines()
            # find the table footer header line starting with 'Counter' or the dashed line
            # then parse subsequent lines that follow the table header
            parsing = False
            for ln in lines:
                if 'Counter' in ln and 'TM Name' in ln:
                    parsing = True
                    continue
                if not parsing:
                    continue
                # skip separator lines
                if ln.strip().startswith('---'):
                    continue
                parts = [p.strip() for p in ln.split('|')]
                if len(parts) >= 3:
                    counter = parts[0]
                    value = parts[-1]
                    # try to parse numeric value
                    try:
                        val = int(value)
                    except Exception:
                        try:
                            val = float(value)
                        except Exception:
                            val = value
                    result['counters'][counter] = val
    except Exception as e:
        app.logger.debug(f"read_suricata_stats: failed reading stats.log: {e}")

    return result

def read_suricata_eve(limit=50):
    """Read suricata eve.json and extract latest events with their status."""
    cached = cache_get("suricata_events")
    if cached:
        return cached

    events = []
    try:
        if os.path.isfile(SURICATA_PATH):
            fpath = SURICATA_PATH
            with open(fpath, "r") as fh:
                # eve.json is newline-delimited JSON objects
                lines = fh.readlines() if fh else []
                # take last N non-empty lines
                for line in reversed(lines):
                    if not line.strip(): continue
                    try:
                        obj = json.loads(line)
                        if obj.get("event_type") in ("alert", "dns", "stats", "flow"):
                            # Add status categorization
                            events.append({
                                "timestamp": obj.get("timestamp"),
                                "src_ip": obj.get("src_ip"),
                                "dest_ip": obj.get("dest_ip"),
                                "event_type": obj.get("event_type"),
                                "status": categorize_event(obj),
                                "details": obj.get("alert", {}).get("signature") or obj.get("dns", {}).get("rrname") or obj.get("flow", {}).get("state"),
                                "severity": obj.get("alert", {}).get("severity")
                            })
                        if len(events) >= limit:
                            break
                    except Exception:
                        continue
        else:
            raise FileNotFoundError("eve.json not found")
        cache_set("suricata_events", events)
        return events
    except Exception as e:
        app.logger.warning("suricata read failed: %s", e)
        if SURICATA_FALLBACK:
            sample = read_sample("sample_eve.json")
            if sample:
                cache_set("suricata_events", sample.get("events", []))
                return sample.get("events", [])
        return []


    def read_suricata_stats():
        """Return a dict with parsed Suricata stats pulled from eve.json (latest stats event)
        and the stats.log counters (if present).
        """
        result = {"eve": None, "counters": {}}
        # 1) try parse latest stats event from eve.json
        try:
            if os.path.isfile(SURICATA_PATH):
                with open(SURICATA_PATH, 'r') as fh:
                    # read lines from end to find first stats event
                    for line in reversed(fh.readlines()):
                        if not line.strip():
                            continue
                        try:
                            obj = json.loads(line)
                        except Exception:
                            continue
                        if obj.get('event_type') == 'stats':
                            result['eve'] = obj.get('stats') or obj
                            break
        except Exception as e:
            app.logger.debug(f"read_suricata_stats: failed reading eve.json: {e}")

        # 2) try to parse stats.log counters for a concise list
        stats_log = '/var/log/suricata/stats.log'
        try:
            if os.path.isfile(stats_log):
                with open(stats_log, 'r') as fh:
                    lines = fh.readlines()
                # find the table footer header line starting with 'Counter' or the dashed line
                # then parse subsequent lines that follow the table header
                parsing = False
                for ln in lines:
                    if 'Counter' in ln and 'TM Name' in ln:
                        parsing = True
                        continue
                    if not parsing:
                        continue
                    # skip separator lines
                    if ln.strip().startswith('---'):
                        continue
                    parts = [p.strip() for p in ln.split('|')]
                    if len(parts) >= 3:
                        counter = parts[0]
                        value = parts[-1]
                        # try to parse numeric value
                        try:
                            val = int(value)
                        except Exception:
                            try:
                                val = float(value)
                            except Exception:
                                val = value
                        result['counters'][counter] = val
        except Exception as e:
            app.logger.debug(f"read_suricata_stats: failed reading stats.log: {e}")

        return result

def system_stats():
    # Get detailed system stats for Raspberry Pi
    cpu_temp = 0
    try:
        with open('/sys/class/thermal/thermal_zone0/temp') as temp_file:
            cpu_temp = float(temp_file.read().strip()) / 1000.0  # Convert millicelsius to celsius
    except Exception as e:
        app.logger.warning(f"Could not read CPU temperature: {e}")
        cpu_temp = 0.0  # Ensure it's a float

    # CPU information
    cpu_freq = psutil.cpu_freq()
    cpu_count = psutil.cpu_count()
    cpu_percent_per_core = psutil.cpu_percent(interval=0.2, percpu=True)
    cpu_avg = psutil.cpu_percent(interval=0.2)

    # Memory information
    memory = psutil.virtual_memory()
    swap = psutil.swap_memory()

    # Disk information
    disk = psutil.disk_usage('/')
    
    return {
        "cpu": {
            "temperature": float(round(cpu_temp, 1)),
            "frequency": float(round(cpu_freq.current, 1)) if cpu_freq else 0.0,
            "cores": int(cpu_count),
            "percent": float(cpu_avg),
            "per_core": [float(x) for x in cpu_percent_per_core]
        },
        "memory": {
            "total": int(memory.total),
            "used": int(memory.used),
            "percent": float(memory.percent),
            "swap_percent": float(swap.percent)
        },
        "disk": {
            "total": int(disk.total),
            "used": int(disk.used),
            "percent": float(disk.percent)
        },
        "ts": datetime.utcnow().isoformat() + "Z"
    }

# ---------- API endpoints ----------

@app.route("/api/ntop/health")
def api_ntop_health():
    try:
        app.logger.info(f"Attempting to fetch ntop stats from URL: {NTOP_URL}")
        stats = get_system_health_stats(NTOP_URL)
        app.logger.info(f"Successfully fetched ntop stats: {stats}")
        return jsonify(stats)
    except Exception as e:
        app.logger.error(f"Failed to fetch ntop health stats: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/ntop/traffic")
def api_ntop_traffic():
    return jsonify(query_ntop_traffic())


@app.route('/goto/ntop')
def goto_ntop():
    """Redirect to ntopng UI on the same host the user used to reach this dashboard.
    Opens the URL constructed from request.host and NTOP_UI_PORT.
    """
    host = request.host.split(':')[0]
    scheme = request.scheme or 'http'
    url = f"{scheme}://{host}:{NTOP_UI_PORT}"
    app.logger.info(f"Redirecting user to ntop UI at {url}")
    return redirect(url)


@app.route('/goto/suricata')
def goto_suricata():
    """Redirect to Suricata UI on the same host the user used to reach this dashboard.
    Constructed from request.host and SURICATA_UI_PORT.
    """
    host = request.host.split(':')[0]
    scheme = request.scheme or 'http'
    url = f"{scheme}://{host}:{SURICATA_UI_PORT}"
    app.logger.info(f"Redirecting user to Suricata UI at {url}")
    return redirect(url)

@app.route("/api/suricata/alerts")
def api_suricata_alerts():
    alerts = read_suricata_eve(limit=50)
    return jsonify({"alerts": alerts})

@app.route("/api/system/stats")
def api_system_stats():
    return jsonify(system_stats())

# ---------- UI pages ----------
@app.route("/")
def ui_index():
    # Get ntop system health stats
    ntop_stats = get_system_health_stats(NTOP_URL)
    
    # Get system stats
    sys_stats = system_stats()
    
    # Get network interface stats
    interface_stats = get_network_interfaces(NTOP_URL)
    
    # Get active hosts data
    hosts_data = get_active_hosts(NTOP_URL)
    
    # Get alerts
    alerts = read_suricata_eve(limit=50)
    
    def format_bytes(bytes_value):
        if not bytes_value:
            return "0 B"
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_value < 1024:
                return f"{bytes_value:.1f} {unit}"
            bytes_value /= 1024
        return f"{bytes_value:.1f} TB"
    
    def format_throughput(bps):
        if not bps:
            return "0 bps"
        for unit in ['bps', 'Kbps', 'Mbps', 'Gbps']:
            if bps < 1000:
                return f"{bps:.1f} {unit}"
            bps /= 1000
        return f"{bps:.1f} Gbps"
    
    return render_template(
        "index.html",
        ntop_stats=ntop_stats,
        sys_stats=sys_stats,
        interface_stats=interface_stats,
        hosts_data=hosts_data,
        alerts=alerts,
        format_mb=lambda x: f"{x:.1f} MB" if x else "0 MB",
        format_gb=lambda x: f"{x/1024:.1f} GB" if x else "0 GB",
        format_percent=lambda x: f"{x:.1f}%" if x is not None else "0%",
        format_bytes=format_bytes,
        format_throughput=format_throughput
    )

@app.route("/threat-management.html")
def ui_threats():
    # Gather events from eve.json, alerts from fast.log, and stats
    events = read_suricata_eve(limit=100)
    fast_alerts = read_fast_log(limit=50)
    suri = read_suricata_stats()
    return render_template("threat-management.html", 
                         events=events, 
                         alerts=fast_alerts, 
                         suricata_stats=suri)

@app.route("/analytics.html")
def ui_analytics():
    return render_template("analytics.html")

# Static files are served automatically from /static

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
