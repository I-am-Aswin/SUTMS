#!/usr/bin/env python3
"""
SUTMS Logging Engine – minimal version
Collects logs from Suricata, ntop, and your Flask app into one file (/var/log/sutms/app.log).
"""

import os, json, time, platform, requests, psutil, subprocess, logging
from pythonjsonlogger import jsonlogger

LOG_FILE = "/var/log/sutms/app.log"
SURICATA_EVE = "/var/log/suricata/eve.json"
NTOP_BASE = "http://10.54.64.34:3000"   # change if your ntopng runs elsewhere
NTOP_STATS = f"{NTOP_BASE}/lua/rest/v2/get/system/health/stats.lua"

# ---------- setup logger ----------
logger = logging.getLogger("sutms")
logger.setLevel(logging.INFO)
fh = logging.FileHandler(LOG_FILE)
formatter = jsonlogger.JsonFormatter('%(asctime)s %(levelname)s %(name)s %(message)s')
fh.setFormatter(formatter)
logger.addHandler(fh)

def get_cpu_temp():
    try:
        out = subprocess.check_output(["vcgencmd", "measure_temp"]).decode()
        return float(out.replace("temp=","").replace("'C","").strip())
    except Exception:
        return 0.0

def system_health():
    return {
        "hostname": platform.node(),
        "uptime": round(time.time() - psutil.boot_time(),1),
        "cpu_percent": psutil.cpu_percent(interval=0.5),
        "mem_percent": psutil.virtual_memory().percent,
        "disk_percent": psutil.disk_usage("/").percent,
        "cpu_temp": get_cpu_temp(),
    }

def log_system_health():
    data = system_health()
    logger.info("system_health", extra={"source":"sutms","event":"system_health","payload":data})

def log_suricata_alerts():
    if not os.path.isfile(SURICATA_EVE): return
    with open(SURICATA_EVE,"r") as f:
        for line in f.readlines()[-10:]:  # last 10 alerts
            try:
                obj = json.loads(line)
                if obj.get("event_type") == "alert":
                    logger.info("suricata_alert", extra={
                        "source":"suricata",
                        "event":"alert",
                        "payload":{
                            "sig":obj.get("alert",{}).get("signature"),
                            "src_ip":obj.get("src_ip"),
                            "dest_ip":obj.get("dest_ip"),
                            "severity":obj.get("alert",{}).get("severity")
                        }})
            except Exception:
                continue

def log_ntop_stats():
    try:
        r = requests.get(NTOP_STATS, timeout=4)
        r.raise_for_status()
        j = r.json()
        logger.info("ntop_stats", extra={"source":"ntop","event":"system_stats","payload":j.get("rsp",{})})
    except Exception as e:
        logger.warning("ntop_fetch_fail", extra={"source":"ntop","event":"error","payload":{"error":str(e)}})

if __name__ == "__main__":
    print("[+] SUTMS Logging Engine started. Writing logs to", LOG_FILE)
    while True:
        log_system_health()
        log_suricata_alerts()
        log_ntop_stats()
        time.sleep(60)  # every minute
