#!/usr/bin/env python3
"""
SUTMS IoC Updater (OpenTAXII + Local Fallback)
-----------------------------------------------
Fetches Indicators of Compromise (IoCs) from an OpenTAXII server,
extracts malicious IPs from STIX data, and adds iptables DROP rules.
Falls back to local IoC file if TAXII fetch fails.
"""

import subprocess
import json
import os
import re
from datetime import datetime
from cabby import create_client
from stix2 import parse

# ================= CONFIGURATION =================

# OpenTAXII server configuration
TAXII_SERVER = "http://10.54.64.166:5000"   # replace with your TAXII server IP or hostname
DISCOVERY_PATH = "/taxii/collections/default_collection/objects"       # default OpenTAXII discovery path
COLLECTION = "default-collection"            # name of your collection

# Authentication (optional; leave blank if not required)
USERNAME = "admin"
PASSWORD = "admin"

# Local fallback IoC file
LOCAL_IOC_FILE = "sample_stix.json"

# iptables command
IPTABLES_CMD = "/sbin/iptables"

# Log file
LOG_FILE = "ioc_update.log"

# =================================================

# Regex for IPv4 addresses
IPV4_RE = re.compile(r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b")


# ---------------- Utility Functions ----------------

def log(msg):
    """Write logs to console and file."""
    print(msg)
    with open(LOG_FILE, "a") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}  {msg}\n")


def extract_ips_from_stix(stix_data):
    """Extract IPv4 addresses from STIX bundle."""
    indicators = []
    try:
        bundle = parse(stix_data, allow_custom=True)
        for obj in bundle.objects:
            if obj.type == "indicator" and "pattern" in obj:
                ips = IPV4_RE.findall(obj.pattern)
                indicators.extend(ips)
    except Exception as e:
        log(f"[!] Failed to parse STIX data: {e}")
    return list(set(indicators))


def fetch_iocs_from_taxii():
    """Fetch IoCs from OpenTAXII server."""
    log(f"[+] Connecting to OpenTAXII server: {TAXII_SERVER}{DISCOVERY_PATH}")
    client = create_client(
        TAXII_SERVER,
        discovery_path=DISCOVERY_PATH,
        username=USERNAME,
        password=PASSWORD
    )

    log("[+] Discovering available collections...")
    collections = client.get_collections()
    found = False
    indicators = []

    for collection in collections:
        if COLLECTION.lower() in collection.name.lower():
            found = True
            log(f"[+] Polling collection: {collection.name}")
            content_blocks = client.poll(collection.name)
            for block in content_blocks:
                try:
                    stix_data = json.loads(block.content)
                    indicators.extend(extract_ips_from_stix(stix_data))
                except Exception as e:
                    log(f"[!] Error parsing content block: {e}")
            break

    if not found:
        raise RuntimeError(f"Collection '{COLLECTION}' not found on server.")

    return list(set(indicators))


def load_local_iocs():
    """Load IoCs from local fallback JSON file."""
    log(f"[+] Loading local IoCs from {LOCAL_IOC_FILE}")
    if not os.path.isfile(LOCAL_IOC_FILE):
        log(f"[!] Local IoC file not found: {LOCAL_IOC_FILE}")
        return []

    with open(LOCAL_IOC_FILE, "r") as f:
        data = f.read()

    ips = IPV4_RE.findall(data)
    return list(set(ips))


def rule_exists(ip):
    """Check if iptables rule already exists."""
    cmd = [IPTABLES_CMD, "-C", "INPUT", "-s", ip, "-j", "DROP"]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return result.returncode == 0


def add_rule(ip):
    """Add DROP rule for a specific IP address."""
    cmd = ["sudo", IPTABLES_CMD, "-A", "INPUT", "-s", ip, "-j", "DROP"]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return result.returncode == 0


# ---------------- Main Logic ----------------

def main():
    log("\n--- SUTMS OpenTAXII IoC Updater ---")

    try:
        ioc_ips = fetch_iocs_from_taxii()
        if not ioc_ips:
            log("[!] No IoCs fetched from TAXII. Switching to local file...")
            ioc_ips = load_local_iocs()
    except Exception as e:
        log(f"[!] TAXII fetch failed: {e}")
        log("[*] Using local fallback IoC file instead.")
        ioc_ips = load_local_iocs()

    if not ioc_ips:
        log("[!] No IoCs available to process.")
        return

    log(f"[+] Total IoCs loaded: {len(ioc_ips)}")
    added = 0

    for ip in ioc_ips:
        if not IPV4_RE.match(ip):
            continue
        if rule_exists(ip):
            log(f"[SKIP] {ip} already blocked.")
            continue
        if add_rule(ip):
            log(f"[BLOCKED] {ip}")
            added += 1
        else:
            log(f"[ERROR] Failed to block {ip}")

    log(f"[+] Completed. {added} new IPs blocked.")
    log("[+] Firewall rules updated successfully.\n")


if __name__ == "__main__":
    main()
