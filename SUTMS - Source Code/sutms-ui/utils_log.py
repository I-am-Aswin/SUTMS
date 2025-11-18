"""
Utility functions for reading and parsing Suricata log files.
"""
import os
import json

def read_fast_log(log_path="/var/log/suricata/fast.log", limit=50):
    """Read and parse Suricata fast.log alerts."""
    alerts = []
    try:
        if os.path.isfile(log_path):
            with open(log_path, 'r') as f:
                # Read last N lines
                lines = f.readlines()[-limit:]
                for line in lines:
                    try:
                        # Fast.log format: timestamp  [**] [id] description [**] [Classification: name] [Priority: n] {proto} src:port -> dst:port
                        parts = line.split('[**]')
                        if len(parts) < 2:
                            continue
                        
                        timestamp = parts[0].strip()
                        alert_parts = parts[1].split(']')
                        
                        # Extract alert ID and description
                        alert_id = alert_parts[0].replace('[', '').strip()
                        description = alert_parts[1].replace('[', '').strip()
                        
                        # Extract classification and priority
                        class_priority = parts[2].split(']')
                        classification = class_priority[0].replace('[Classification:', '').strip()
                        priority = class_priority[1].replace('[Priority:', '').replace(']', '').strip()
                        
                        # Extract protocol and IPs
                        traffic = parts[2].split('}')[-1].strip()
                        src_dst = traffic.split('->')
                        
                        alerts.append({
                            'timestamp': timestamp,
                            'id': alert_id,
                            'description': description,
                            'classification': classification,
                            'priority': int(priority),
                            'source': src_dst[0].strip() if len(src_dst) > 0 else 'unknown',
                            'destination': src_dst[1].strip() if len(src_dst) > 1 else 'unknown'
                        })
                    except Exception:
                        continue
    except Exception as e:
        print(f"Error reading fast.log: {e}")
    
    return alerts

def categorize_event(event):
    """Categorize a Suricata event based on its type and severity."""
    event_type = event.get('event_type', '')
    
    # For alert events, check severity
    if event_type == 'alert':
        severity = event.get('alert', {}).get('severity', 0)
        if severity >= 3:
            return 'high-risk'
        elif severity >= 2:
            return 'medium-risk'
        return 'low-risk'
    
    # For flow events
    elif event_type == 'flow':
        state = event.get('flow', {}).get('state', '')
        if state in ['new', 'established']:
            return 'normal'
        return 'suspicious'
    
    # For DNS events
    elif event_type == 'dns':
        if event.get('dns', {}).get('rcode') == 'NXDOMAIN':
            return 'warning'
        return 'normal'
    
    # Default case
    return 'normal'