import requests
import urllib3

NTOP_USER = "admin"
NTOP_PASS = "ntopng"


# Disable SSL warnings for self-signed certificates (optional)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def get_active_hosts(base_url="http://127.0.0.1:3000", interface_id=2, token=None):
    """
    Fetch and parse active host data from ntopng.
    
    Args:
        base_url (str): Base URL of the ntopng instance.
        interface_id (int): Interface ID to fetch host stats for.
        token (str): Optional authentication token.
    
    Returns:
        dict: Dictionary containing active host metrics.
    """
    endpoint = f"{base_url}/lua/rest/v2/get/host/active.lua?ifid=2"
    headers = {}

    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        response = requests.get(endpoint,  auth=(NTOP_USER, NTOP_PASS), headers=headers, timeout=15, verify=False)
        response.raise_for_status()

        try:
            data = response.json()
        except ValueError:
            print("⚠️ Invalid JSON response. Raw output:\n", response.text[:1000])
            return {"error": "Invalid JSON response"}

        if data.get("rc") != 0 or "rsp" not in data:
            print("⚠️ Unexpected response structure:", data)
            return {"error": "Invalid or incomplete response"}

        host_entries = data["rsp"].get("data", [])
        hosts = []

        for host in host_entries:
            hosts.append({
                "ip": host.get("ip"),
                "name": host.get("name"),
                "mac": host.get("mac"),
                "country": host.get("country"),
                "bytes_received": host.get("bytes", {}).get("recvd"),
                "bytes_sent": host.get("bytes", {}).get("sent"),
                "total_bytes": host.get("bytes", {}).get("total"),
                "throughput_bps": host.get("thpt", {}).get("bps"),
                "throughput_pps": host.get("thpt", {}).get("pps"),
                "flows": host.get("num_flows", {}).get("total"),
                "score": host.get("score", {}).get("total"),
                "is_localhost": host.get("is_localhost"),
                "is_blacklisted": host.get("is_blacklisted"),
                "last_seen": host.get("last_seen"),
            })

        return {"interface_id": interface_id, "active_hosts": hosts}

    except requests.RequestException as e:
        return {"error": f"Request failed: {e}"}


if __name__ == "__main__":
    result = get_active_hosts()
    print(result)
