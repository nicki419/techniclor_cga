This project provides several **sensor entities** for a Technicolor CGA gateway in Home Assistant. It reads system and DHCP information, lists connected hosts, and offers a **delta sensor** to detect missing/inactive devices. Thanks to `device_info`, all entities are grouped under **one device** in Home Assistant's device and integrations registry.

## Features

- **System status** (e.g., `CMStatus`) including pass-through of additional system attributes
- **DHCP sensors** for all DHCP keys returned by the gateway
- **Host list** with the number of currently detected devices (`hostTbl`)
- **Missing devices / Delta sensor**: shows devices that disappeared or are inactive
- **Clean device grouping** via `device_info` (identifiers = `(DOMAIN, host)`, manufacturer, name, `configuration_url`); model/firmware are added when available
- **Automatic polling** every 5 minutes

## Installation

1. Clone this repo while in `/config/custom_components`.
2. **Restart** Home Assistant.
3. Go to **Settings → Devices & Services → Add Integration** and pick *Technicolor CGA*.
4. Enter your credentials:
   - **Host** (e.g., `192.168.0.1`)
   - **Username**
   - **Password**

> The integration uses **Config Entries** (UI-based setup).

## Created entities

### System sensor

- **Name:** `Technicolor CGA System Status`
- **State:** value of `CMStatus` (or `"Unknown"`)
- **Attributes:** all other system fields (e.g., `ModelName`, `SoftwareVersion`, etc.).
- **Device info:** `model`/`sw_version` are set from system data when present.

### DHCP sensors

- **Name:** `Technicolor CGA DHCP <Key>` (for each key returned by `dhcp()`)
- **State:** corresponding value from DHCP data (or `"Unknown"`).

### Host sensor

- **Name:** `Technicolor CGA Host List`
- **State:** number of entries in `hostTbl`.
- **Attributes:** full host data structure (e.g., `hostTbl`, entries with `physaddress`, `ipaddress`, `hostname`, `active`).

### Delta / Missing devices sensor

- **Name:** `Technicolor CGA Missing Devices`
- **State:** number of detected *missing* or *inactive* devices.
- **Attributes:**
  - `missing_devices`: list of dicts `{mac, last_ip, hostname, status}`
  - `known_devices`: list of learned devices `{mac, last_ip, hostname}`
- **Notes:**
  - The `known_devices` list is **learned at runtime** (no persistence across restarts).
  - Sorting is numeric by IP; invalid IPs are placed at the end.

## Update interval

By default every **5 minutes** (`SCAN_INTERVAL = 300s`).

## Tips / Troubleshooting

- Verify `Host`, `Username`, `Password` and that the web interface is reachable.
- Some gateways return slightly different field names (`ModelName` vs. `Model`, `SoftwareVersion` vs. `SWVersion`/`FirmwareVersion`). The code handles common variants.
- The delta sensor only learns devices after they have been seen at least once.

## Development

- Entities inherit from `SensorEntity` (the base class provides `device_info`).
- **Unique IDs** are based on `config_entry_id` + entity name.
- Polling via `async_track_time_interval`.
- The API class `TechnicolorCGA` is called in the executor (`login`, `system`, `dhcp`, `aDev`).

## Options (Polling rate, per-IP disable, and custom names)

After adding the integration:

- Go to: Settings → Devices & Services → Integrations → Technicolor CGA → Configure (gear icon on the integration card).
- Options available:
  - scan_interval (seconds): How often to poll the router (minimum 10s; default 300s).
  - disabled_ips: Comma- or newline-separated list of IP addresses you do NOT want to track.
    - Examples: `192.168.0.10`, `192.168.0.20`
  - name_overrides_ip: One per line mapping IP to a display name. Either "ip = Name" or "ip: Name" formats are accepted.
    - Example:
      - 192.168.0.10 = Nick iPhone
      - 192.168.0.20: Laptop Work
  - (Backward compatible) disabled_macs / name_overrides: Older MAC-based settings are still accepted. If both IP and MAC overrides are provided for the same device, IP takes precedence.

Notes:

- Trackers are now keyed by IP address. Disabling/renaming by IP is recommended.
- After changing options, reload the integration to apply changes to all entities.
- Configuration is managed at the INTEGRATION level (Configure on the integration). There are no per-entity option panels for these settings.

## Presence detection logic

Presence is determined by the router entry for the device's IP address.
Some firmware returns two relevant fields per device:

- Active: boolean (True/False) or a string variant ("true"/"false"/"0"/"1"/etc.)
- Status: string with values like "ONLINE" or "offline"

The device trackers determine presence as follows:

1) If Active is an explicit boolean → use it directly.
2) Else, if Status is "ONLINE" (uppercase) or "offline" (lowercase) → use that.
3) Else, fall back to common string truthiness for Active.

For transparency, each tracker exposes attributes:

- ip, mac (if known), hostname
- status_raw, active_raw (exact values reported by the router)
- last_seen (timestamp when last row for that IP was observed)
