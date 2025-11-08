#!/usr/bin/env python3
"""
Simple diagnostic script to print the current network status of all devices
as reported by the Technicolor CGA router.

Usage:
  python3 test.py --username <user> --password <pass> [--host 192.168.0.1]

This script uses the same router client as the Home Assistant integration
(technicolor_cga.TechnicolorCGA), logs in, fetches the host table (aDev),
and prints a readable table including online/offline status.
"""

import argparse
import sys
from datetime import datetime

from technicolor_cga import TechnicolorCGA


def _is_active(value) -> bool:
    s = str(value).strip().lower()
    return s not in ("false", "0", "no", "off", "none", "")


def _ip_sort_key(ip: str):
    try:
        return tuple(int(x) for x in ip.split("."))
    except Exception:
        return (999, 999, 999, 999)


def main() -> int:
    parser = argparse.ArgumentParser(description="Print Technicolor CGA device network status")
    parser.add_argument("--username", required=True, help="Router username")
    parser.add_argument("--password", required=True, help="Router password")
    parser.add_argument("--host", default="192.168.87.1", help="Router IP/host (default: 192.168.87.1)")

    args = parser.parse_args()

    cli = TechnicolorCGA(args.username, args.password, args.host)

    try:
        if not cli.login():
            print("Login failed (unexpected)", file=sys.stderr)
            return 2
    except Exception as e:
        print(f"Login error: {e}", file=sys.stderr)
        return 2

    try:
        data = cli.aDev()  # {'hostTbl': [...], ...}
    except Exception as e:
        print(f"Failed to fetch host table: {e}", file=sys.stderr)
        return 3

    hosts = data.get("hostTbl", []) or []

    # Normalize and sort by IP then hostname
    normalized = []
    for dev in hosts:
        mac = dev.get("physaddress") or "unknown"
        ip = dev.get("ipaddress") or "unknown"
        hostname = dev.get("hostname") or "unknown"
        active_raw = dev.get("active", "false")
        online = _is_active(active_raw)
        normalized.append({
            "mac": mac,
            "ip": ip,
            "hostname": hostname,
            "active": str(active_raw),
            "online": online,
        })

    normalized.sort(key=lambda x: (_ip_sort_key(x["ip"]), x["hostname"]))

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"Technicolor CGA — Device Status @ {ts} (host: {args.host})")
    print("")

    # Table header
    cols = ("MAC", "IP", "Hostname", "Active", "Status")
    widths = [17, 15, 32, 8, 10]
    header = " ".join(s.ljust(w) for s, w in zip(cols, widths))
    print(header)
    print("-" * len(header))

    online_count = 0
    for row in normalized:
        status = "ONLINE" if row["online"] else "offline"
        if row["online"]:
            online_count += 1
        line = " ".join([
            str(row["mac"]).ljust(widths[0]),
            str(row["ip"]).ljust(widths[1]),
            str(row["hostname"]).ljust(widths[2]),
            str(row["active"]).ljust(widths[3]),
            status.ljust(widths[4]),
        ])
        print(line)

    print("")
    print(f"Total devices: {len(normalized)} — Online: {online_count} — Offline: {len(normalized) - online_count}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
