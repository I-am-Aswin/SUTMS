import requests

NTOP_USER = "admin"
NTOP_PASS = "ntopng"

def get_system_health_stats(base_url="http://127.0.0.1:3000"):
    """
    Fetch and parse system health stats from ntopng endpoint.
    
    Args:
        base_url (str): Base URL of the ntopng instance.
    
    Returns:
        dict: Dictionary containing parsed system metrics.
    """
    endpoint = f"{base_url}/lua/rest/v2/get/system/health/stats.lua"
    
    try:
        response = requests.get(endpoint, auth=(NTOP_USER, NTOP_PASS), timeout=10)
        response.raise_for_status()  # Raises error for HTTP codes >= 400
        data = response.json()
        
        if data.get("rc") != 0 or "rsp" not in data:
            raise ValueError("Invalid response structure or rc != 0")
        
        rsp = data["rsp"]

        # Extract CPU stats
        cpu_data = {
            "cpu_load": rsp.get("cpu_load"),
            "cpu_idle": rsp.get("cpu_states", {}).get("idle"),
            "cpu_user": rsp.get("cpu_states", {}).get("user"),
            "cpu_system": rsp.get("cpu_states", {}).get("system")
        }

        # Extract memory stats (values in KB, converting to MB for readability)
        memory_data = {
            "mem_total_MB": round(rsp.get("mem_total", 0) / 1024, 2),
            "mem_used_MB": round(rsp.get("mem_used", 0) / 1024, 2),
            "mem_free_MB": round(rsp.get("mem_free", 0) / 1024, 2),
            "mem_cached_MB": round(rsp.get("mem_cached", 0) / 1024, 2),
            "mem_ntopng_resident_MB": round(rsp.get("mem_ntopng_resident", 0) / 1024, 2),
        }

        # Extract storage stats
        storage = rsp.get("storage", {})
        storage_data = {
            "volume_device": storage.get("volume_dev"),
            "volume_size_MB": round(storage.get("volume_size", 0) / (1024 * 1024), 2),
            "storage_total_MB": round(storage.get("total", 0) / 1024, 2),
            "storage_other_MB": round(storage.get("other", 0) / 1024, 2),
        }

        # Combine all data
        system_stats = {
            "cpu": cpu_data,
            "memory": memory_data,
            "storage": storage_data,
            "alerts": {
                "written_alerts": rsp.get("written_alerts"),
                "dropped_alerts": rsp.get("dropped_alerts"),
                "alerts_queries": rsp.get("alerts_queries")
            }
        }

        return system_stats

    except (requests.RequestException, ValueError) as e:
        return {"error": str(e)}


# Example usage:
if __name__ == "__main__":
    stats = get_system_health_stats()
    print(stats)
