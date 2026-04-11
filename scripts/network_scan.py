#!/usr/bin/env python3
"""BigClaw Network Security Scanner — Weekly IoT monitoring."""

import subprocess
import json
import os
from datetime import datetime

BASELINE_FILE = os.path.expanduser("~/.openclaw/workspace/config/network_baseline.json")
SCAN_LOG = os.path.expanduser("~/.openclaw/workspace/logs/network_scans.log")

def scan_network():
    """Run nmap ping scan and return device list."""
    result = subprocess.run(
        ["sudo", "nmap", "-sn", "192.168.1.0/24"],
        capture_output=True, text=True, timeout=30
    )
    devices = []
    current = {}
    for line in result.stdout.splitlines():
        if "Nmap scan report for" in line:
            if current:
                devices.append(current)
            parts = line.split("for ")[-1]
            if "(" in parts:
                hostname = parts.split(" (")[0]
                ip = parts.split("(")[1].rstrip(")")
            else:
                hostname = ""
                ip = parts
            current = {"ip": ip, "hostname": hostname, "mac": "", "vendor": ""}
        elif "MAC Address:" in line:
            mac = line.split("MAC Address: ")[1].split(" ")[0]
            vendor = line.split("(")[-1].rstrip(")") if "(" in line else "Unknown"
            current["mac"] = mac
            current["vendor"] = vendor
    if current:
        devices.append(current)
    return devices

def load_baseline():
    """Load known device baseline."""
    if os.path.exists(BASELINE_FILE):
        with open(BASELINE_FILE) as f:
            return json.load(f)
    return {"devices": {}, "last_scan": None}

def save_baseline(baseline):
    """Save baseline."""
    os.makedirs(os.path.dirname(BASELINE_FILE), exist_ok=True)
    with open(BASELINE_FILE, "w") as f:
        json.dump(baseline, f, indent=2)

def compare_to_baseline(devices, baseline):
    """Compare scan results to baseline, return new/missing devices."""
    known_macs = set(baseline.get("devices", {}).keys())
    current_macs = {d["mac"]: d for d in devices if d["mac"]}
    
    new_devices = []
    for mac, dev in current_macs.items():
        if mac not in known_macs:
            new_devices.append(dev)
    
    missing_devices = []
    for mac, info in baseline.get("devices", {}).items():
        if mac not in current_macs:
            missing_devices.append(info)
    
    return new_devices, missing_devices

def main():
    print(f"🔐 Network Security Scan — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    
    devices = scan_network()
    print(f"Found {len(devices)} devices\n")
    
    baseline = load_baseline()
    
    if not baseline["devices"]:
        # First run — save as baseline
        print("📋 Creating initial baseline...")
        baseline["devices"] = {d["mac"]: d for d in devices if d["mac"]}
        baseline["last_scan"] = datetime.now().isoformat()
        save_baseline(baseline)
        for d in devices:
            print(f"  {d['ip']:16} {d.get('hostname',''):35} {d['mac']:18} {d['vendor']}")
        print(f"\nBaseline saved with {len(baseline['devices'])} devices.")
        return json.dumps({"status": "baseline_created", "device_count": len(devices), "alerts": []})
    
    new_devices, missing_devices = compare_to_baseline(devices, baseline)
    
    alerts = []
    
    if new_devices:
        print("🚨 NEW DEVICES DETECTED:")
        for d in new_devices:
            msg = f"NEW: {d['ip']} — {d.get('hostname', 'Unknown')} ({d['vendor']}) MAC: {d['mac']}"
            print(f"  ⚠️ {msg}")
            alerts.append({"type": "new_device", "detail": msg, "device": d})
    
    if missing_devices:
        print("\n📴 MISSING DEVICES (previously seen):")
        for d in missing_devices:
            msg = f"GONE: {d['ip']} — {d.get('hostname', 'Unknown')} ({d['vendor']})"
            print(f"  ℹ️ {msg}")
            alerts.append({"type": "missing_device", "detail": msg, "device": d})
    
    if not new_devices and not missing_devices:
        print("✅ All clear — no changes from baseline.")
    
    # Update baseline with current scan
    baseline["devices"] = {d["mac"]: d for d in devices if d["mac"]}
    baseline["last_scan"] = datetime.now().isoformat()
    save_baseline(baseline)
    
    # Log
    os.makedirs(os.path.dirname(SCAN_LOG), exist_ok=True)
    with open(SCAN_LOG, "a") as f:
        f.write(f"{datetime.now().isoformat()} | devices={len(devices)} | new={len(new_devices)} | missing={len(missing_devices)}\n")
    
    return json.dumps({"status": "complete", "device_count": len(devices), 
                       "new": len(new_devices), "missing": len(missing_devices), "alerts": alerts})

if __name__ == "__main__":
    result = main()
    if "--json" in __import__("sys").argv:
        print(result)
