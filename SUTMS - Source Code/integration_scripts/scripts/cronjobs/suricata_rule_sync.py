#!/usr/bin/env python3
"""
Synchronize Suricata rule enable/disable lists based on protocols detected by ntopng.
Now includes whitelist support — categories in /etc/suricata/rule_whitelist.txt are always kept enabled.
"""

import os
import subprocess
import logging
import hashlib
from pathlib import Path

# ---------------- CONFIG ----------------
PROTO_FILE = Path("/var/lib/ntopng/protocols.txt")
SURICATA_RULE_DIR = Path("/etc/suricata/rules")
DISABLE_FILE = Path("/etc/suricata/disable.conf")
WHITELIST_FILE = Path("/etc/suricata/rule_whitelist.txt")
LOG_FILE = Path("/var/log/suricata_rule_sync.log")
SURICATA_SERVICE = "suricata"

# Map ntopng protocols → Suricata rule categories
PROTO_TO_RULE = {
    "HTTP": "http",
    "HTTPS": "tls",
    "TLS": "tls",
    "DNS": "dns",
    "SSH": "ssh",
    "FTP": "ftp",
    "SMTP": "smtp",
    "POP3": "pop3",
    "IMAP": "imap",
    "MDNS": "mdns",
    "SMB": "smb",
    "NTP": "ntp",
    "DHCP": "dhcp",
    "ICMPV6": "icmp",
    "ICMP": "icmp",
    "NETBIOS": "netbios",
    "MICROSOFT365": "http",
    "MQTT": "mqtt",
}
# ----------------------------------------

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

def get_active_protocols():
    if not PROTO_FILE.exists():
        logging.warning("Protocol file not found: %s", PROTO_FILE)
        return []
    with open(PROTO_FILE) as f:
        prots = [line.strip() for line in f if line.strip()]
    logging.info("Active protocols read: %s", prots)
    return prots


def get_all_rule_categories(rule_dir=SURICATA_RULE_DIR):
    categories = set()
    if not rule_dir.exists():
        logging.error("Suricata rule directory not found: %s", rule_dir)
        return categories

    for rfile in rule_dir.glob("*.rules"):
        stem = rfile.stem
        if "-" in stem:
            candidate = stem.split("-")[0].lower()
        else:
            candidate = stem.lower()
        categories.add(candidate)
    logging.info("Discovered rule categories: %s", sorted(categories))
    return categories


def load_whitelist():
    """Load whitelisted rule categories (always enabled)."""
    if not WHITELIST_FILE.exists():
        logging.info("No whitelist found (%s). Continuing without it.", WHITELIST_FILE)
        return set()
    with open(WHITELIST_FILE) as f:
        wl = {line.strip().lower() for line in f if line.strip() and not line.startswith("#")}
    logging.info("Loaded whitelist: %s", sorted(wl))
    return wl


def map_protocols_to_categories(active_protocols, all_categories):
    active_cats = set()
    for p in active_protocols:
        pu = p.upper()
        if pu in PROTO_TO_RULE:
            active_cats.add(PROTO_TO_RULE[pu].lower())
            continue

        pl = p.lower()
        if pl in all_categories:
            active_cats.add(pl)
            continue

        for cat in all_categories:
            if cat in pl or pl in cat:
                active_cats.add(cat)
                break
    logging.info("Mapped active protocols -> categories: %s", sorted(active_cats))
    return active_cats


def build_disable_content(all_categories, enabled_categories, whitelist):
    """Generate disable.conf lines for categories NOT enabled or whitelisted."""
    protected = enabled_categories | whitelist
    disabled = sorted(all_categories - protected)
    lines = [f"re:{cat}\n" for cat in disabled]
    return "".join(lines)


def file_checksum(path):
    if not path.exists():
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def write_if_changed(path, content):
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(content)
    old_sum = file_checksum(path)
    new_sum = hashlib.sha256(content.encode()).hexdigest()
    if old_sum == new_sum:
        logging.info("No change to %s — skipping write.", path)
        tmp.unlink(missing_ok=True)
        return False
    tmp.replace(path)
    logging.info("Updated %s (checksum changed).", path)
    return True


def reload_suricata():
    try:
        subprocess.run(["systemctl", "reload", SURICATA_SERVICE], check=True)
        logging.info("Suricata reloaded successfully.")
    except subprocess.CalledProcessError as e:
        logging.error("Failed to reload Suricata: %s", e)


def suricata_rule_sync():
    active_protocols = get_active_protocols()
    all_categories = get_all_rule_categories()
    whitelist = load_whitelist()

    if not active_protocols:
        logging.warning("No active protocols found; skipping update.")
        return
    if not all_categories:
        logging.error("No rule categories found; aborting.")
        return

    enabled = map_protocols_to_categories(active_protocols, all_categories)
    content = build_disable_content(all_categories, enabled, whitelist)

    if write_if_changed(DISABLE_FILE, content):
        reload_suricata()
    else:
        logging.info("disable.conf unchanged; Suricata not reloaded.")


if __name__ == "__main__":
    suricata_rule_sync()
