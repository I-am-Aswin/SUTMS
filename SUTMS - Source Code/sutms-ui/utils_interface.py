import requests

NTOP_USER = "admin"
NTOP_PASS = "ntopng"

def get_network_interfaces(base_url="http://127.0.0.1:3000", token=None):
    """
    Fetch and parse network interface details from ntopng.
    
    Args:
        base_url (str): Base URL of the ntopng instance.
        token (str): Optional API token if authentication is required.
    
    Returns:
        dict: Dictionary containing a list of network interface details.
    """
    endpoint = f"{base_url}/lua/rest/v2/get/ntopng/interfaces.lua"
    headers = {}

    # Add auth token if required
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        response = requests.get(endpoint, auth=(NTOP_USER, NTOP_PASS), headers=headers, timeout=10)
        response.raise_for_status()

        try:
            data = response.json()
        except ValueError:
            print("⚠️ Invalid JSON response. Raw output:\n", response.text[:1000])
            return {"error": "Invalid JSON response"}

        if data.get("rc") != 0 or "rsp" not in data:
            print("⚠️ Unexpected response structure:", data)
            return {"error": "Invalid or incomplete response"}

        interfaces = []
        for iface in data["rsp"]:
            interfaces.append({
                "interface_id": iface.get("ifid"),
                "name": iface.get("name"),
                "is_pcap": iface.get("is_pcap_interface"),
                "is_packet": iface.get("is_packet_interface"),
                "is_zmq": iface.get("is_zmq_interface"),
            })

        return {"interfaces": interfaces}

    except requests.RequestException as e:
        return {"error": f"Request failed: {e}"}


if __name__ == "__main__":
    stats = get_network_interfaces()
    print(stats)
