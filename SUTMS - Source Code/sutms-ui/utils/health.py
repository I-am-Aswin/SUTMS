import requests
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional

class NtopFetchError(Exception):
    pass

def fetch_ntop_system_stats(
    base_url: str,
    timeout: float = 5.0,
    api_key: Optional[str] = None,
    retries: int = 3,
    backoff: float = 0.5
) -> Dict[str, Any]:
    """
    Fetch and normalise ntopng system health stats from:
      <base_url>/lua/rest/v2/get/system/health/stats.lua

    Returns a dictionary with the most useful fields:
      {
        "raw": <original JSON payload>,
        "epoch": <int>,
        "timestamp": <datetime UTC>,
        "cpu_load": <float>,
        "cpu_states": {...},
        "mem": {
          "total": <int bytes>,
          "used": <int bytes>,
          "free": <int bytes>,
          "cached": <int bytes>,
          "buffers": <int bytes>,
          "shmem": <int bytes>
        },
        "ntopng_mem": {
          "resident": <int bytes>,
          "virtual": <int bytes>
        },
        "storage": {
          "total": <int bytes>,
          "volume_dev": <str>,
          "interfaces": [
            {"name": ..., "total": <int bytes>, "pcap": <int bytes>, "rrd": <int bytes>}, ...
          ]
        },
        "alerts": {
          "queries": <int>,
          "written": <int>,
          "dropped": <int>,
          "stats": {...}
        }
      }

    Raises:
      NtopFetchError on network/format errors.
    """
    if base_url.endswith("/"):
        base_url = base_url[:-1]
    url = f"{base_url}/lua/rest/v2/get/system/health/stats.lua"

    headers = {}
    if api_key:
        headers["X-API-Key"] = api_key

    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            payload = resp.json()
            # assert rc==0 or rc_str
            if not isinstance(payload, dict) or "rc" not in payload or "rsp" not in payload:
                raise NtopFetchError("Unexpected response format from ntopng")
            rsp = payload.get("rsp", {})

            # Basic fields
            epoch = int(rsp.get("epoch")) if rsp.get("epoch") is not None else None
            timestamp = datetime.fromtimestamp(epoch, tz=timezone.utc) if epoch else None
            cpu_load = float(rsp.get("cpu_load")) if rsp.get("cpu_load") is not None else None

            # Memory normalisation (ntop returns small integers — assume bytes already)
            mem = {
                "total": int(rsp.get("mem_total", 0)),
                "used": int(rsp.get("mem_used", 0)),
                "free": int(rsp.get("mem_free", 0)),
                "cached": int(rsp.get("mem_cached", 0)),
                "buffers": int(rsp.get("mem_buffers", 0)),
                "shmem": int(rsp.get("mem_shmem", 0)),
            }

            ntopng_mem = {
                "resident": int(rsp.get("mem_ntopng_resident", 0)),
                "virtual": int(rsp.get("mem_ntopng_virtual", 0)),
            }

            # Storage block
            storage_raw = rsp.get("storage", {}) or {}
            storage = {
                "total": int(storage_raw.get("total", 0)),
                "volume_size": int(storage_raw.get("volume_size", 0)),
                "volume_dev": storage_raw.get("volume_dev"),
                "other": int(storage_raw.get("other", 0)),
                "pcap_total": int(storage_raw.get("pcap_total", 0)),
                "interfaces": []
            }
            # interfaces may be a list with null first element per example
            for iface in storage_raw.get("interfaces", []) or []:
                if not iface:
                    continue
                storage["interfaces"].append({
                    "name": iface.get("name"),
                    "total": int(iface.get("total", 0)),
                    "pcap": int(iface.get("pcap", 0)),
                    "rrd": int(iface.get("rrd", 0))
                })

            alerts = {
                "queries": int(rsp.get("alerts_queries", 0)),
                "written": int(rsp.get("written_alerts", 0)),
                "dropped": int(rsp.get("dropped_alerts", 0)),
                "stats": rsp.get("alerts_stats", {})
            }

            cpu_states = rsp.get("cpu_states", {})

            result = {
                "raw": payload,
                "epoch": epoch,
                "timestamp": timestamp,
                "cpu_load": cpu_load,
                "cpu_states": cpu_states,
                "mem": mem,
                "ntopng_mem": ntopng_mem,
                "storage": storage,
                "alerts": alerts
            }
            return result

        except (requests.RequestException, ValueError) as e:
            last_exc = e
            # simple backoff
            if attempt < retries:
                time.sleep(backoff * attempt)
                continue
            raise NtopFetchError(f"Failed to fetch ntop stats: {e}") from e

    # if fallthrough
    raise NtopFetchError(f"Failed to fetch ntop stats, last error: {last_exc}")

# ----------------------------
# Example usage:
# from ntop_utils import fetch_ntop_system_stats, NtopFetchError
#
# try:
#     stats = fetch_ntop_system_stats("http://10.54.64.34:3000", api_key="YOUR_KEY", timeout=4)
#     print(stats["timestamp"], stats["cpu_load"], stats["mem"])
# except NtopFetchError as e:
#     print("Error:", e)
