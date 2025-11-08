import logging
from datetime import datetime, timedelta
from typing import Dict, List

from homeassistant.components.device_tracker import TrackerEntity
from homeassistant.components.device_tracker.const import SourceType
from homeassistant.const import CONF_HOST, STATE_HOME, STATE_NOT_HOME
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, CoordinatorEntity, UpdateFailed

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

DEFAULT_SCAN_SECONDS = 60


def _normalize_mac(mac: str) -> str:
    mac = (mac or "").strip().lower().replace("-", ":")
    parts = [p.zfill(2) for p in mac.split(":") if p]
    return ":".join(parts)


def _normalize_ip(ip: str) -> str:
    ip = (ip or "").strip()
    return ip

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up device tracker entities for Technicolor CGA from a config entry."""
    _LOGGER.debug("[TCGA][TRACKER] async_setup_entry starting")

    technicolor_cga = hass.data[DOMAIN].get(config_entry.entry_id)
    if technicolor_cga is None:
        _LOGGER.error("[TCGA][TRACKER] Technicolor CGA instance not found in hass.data for entry %s", config_entry.entry_id)
        return

    host = config_entry.data[CONF_HOST]

    # Determine scan interval from options
    scan_seconds = int(config_entry.options.get("scan_interval", DEFAULT_SCAN_SECONDS))
    if scan_seconds < 10:
        scan_seconds = 10
    scan_interval = timedelta(seconds=scan_seconds)

    # Filtering and naming options (prefer IP-based; keep MAC for backward compatibility)
    disabled_ips = set(_normalize_ip(i) for i in config_entry.options.get("disabled_ips", []))
    name_overrides_ip: Dict[str, str] = { _normalize_ip(k): v for k, v in config_entry.options.get("name_overrides_ip", {}).items() }
    # Back-compat
    disabled_macs = set(_normalize_mac(m) for m in config_entry.options.get("disabled_macs", []))
    name_overrides_mac: Dict[str, str] = { _normalize_mac(k): v for k, v in config_entry.options.get("name_overrides", {}).items() }

    _LOGGER.info(
        "[TCGA][TRACKER] Setup for host=%s scan_interval=%ss disabled_ips=%d name_overrides_ip=%d (legacy disabled_macs=%d name_overrides_macs=%d)",
        host, scan_seconds, len(disabled_ips), len(name_overrides_ip), len(disabled_macs), len(name_overrides_mac)
    )
    _LOGGER.debug("[TCGA][TRACKER] Options detail disabled_ips=%s name_overrides_ip=%s disabled_macs=%s name_overrides_mac=%s", list(disabled_ips), name_overrides_ip, list(disabled_macs), name_overrides_mac)

    # Shared DataUpdateCoordinator that fetches the host table once per interval
    async def _async_update_data():
        try:
            data = await hass.async_add_executor_job(technicolor_cga.aDev)
            table = data.get("hostTbl", []) or []
            _LOGGER.debug("[TCGA][COORD] fetched hostTbl size=%d", len(table))
            return data
        except Exception as err:
            _LOGGER.exception("[TCGA][COORD] Error fetching host table")
            raise UpdateFailed(err) from err

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="[TCGA][COORD] hostTbl",
        update_method=_async_update_data,
        update_interval=scan_interval,
    )

    await coordinator.async_config_entry_first_refresh()

    devices: List[dict] = (coordinator.data or {}).get("hostTbl", []) or []
    _LOGGER.info("[TCGA][TRACKER] Initial hostTbl size=%d", len(devices))

    entities: Dict[str, TechnicolorCGATrackerEntity] = {}

    def _add_entity_from_dev(dev: dict):
        ip_raw = dev.get("ipaddress")
        if not ip_raw:
            return
        ip = _normalize_ip(ip_raw)
        if ip in entities:
            return
        if ip in disabled_ips:
            _LOGGER.info("[TCGA][TRACKER] Skipping disabled IP=%s", ip)
            return
        mac_raw = dev.get("physaddress")
        mac = _normalize_mac(mac_raw) if mac_raw else None
        # Prefer IP overrides; fall back to MAC overrides for back-compat
        name_override = name_overrides_ip.get(ip) if 'name_overrides_ip' in locals() else None
        if not name_override and mac:
            name_override = name_overrides_mac.get(mac) if 'name_overrides_mac' in locals() else None
        entity = TechnicolorCGATrackerEntity(
            coordinator=coordinator,
            technicolor_cga=technicolor_cga,
            hass=hass,
            config_entry_id=config_entry.entry_id,
            host=host,
            ip=ip,
            mac=mac,
            initial=dev,
            name_override=name_override,
        )
        entities[ip] = entity
        _LOGGER.info(
            "[TCGA][TRACKER] Adding tracker entity for IP=%s hostname=%s mac=%s name_override=%s",
            ip, dev.get('hostname'), mac, name_override
        )
        async_add_entities([entity], False)

    for dev in devices:
        _add_entity_from_dev(dev)

    _LOGGER.info("[TCGA][TRACKER] Added %d tracker entities", len(entities))

    # Listen to coordinator updates to discover new devices
    def _on_coordinator_update():
        table = (coordinator.data or {}).get("hostTbl", []) or []
        for dev in table:
            _add_entity_from_dev(dev)

    coordinator.async_add_listener(_on_coordinator_update)


class TechnicolorCGATrackerEntity(CoordinatorEntity, TrackerEntity):
    """A device tracker for a single IP from the Technicolor CGA router (coordinator‑backed)."""

    def __init__(self, coordinator: DataUpdateCoordinator, technicolor_cga, hass, config_entry_id, host, ip: str, mac: str | None, initial: dict | None = None, name_override: str | None = None):
        super().__init__(coordinator)
        self.technicolor_cga = technicolor_cga
        self.hass = hass
        self._config_entry_id = config_entry_id
        self._host = host
        self._ip = ip
        self._mac = mac
        self._hostname = None
        self._is_connected = False
        self._status_raw = None
        self._active_raw = None
        self._name_override = name_override
        self._last_seen = None
        self._attr_should_poll = False  # coordinator drives updates
        if initial is not None:
            self._apply_device(initial)
        _LOGGER.debug("[TCGA][TRACKER] Entity created ip=%s mac=%s hostname=%s name_override=%s (coordinator)", self._ip, self._mac, self._hostname, self._name_override)

    @property
    def should_poll(self) -> bool:
        # Coordinator drives updates; no direct polling per entity
        return False

    @property
    def unique_id(self) -> str:
        safe_ip = (self._ip or "unknown").replace(":", "_").replace("/", "_")
        return f"{self._config_entry_id}_tracker_ip_{safe_ip}"

    @property
    def name(self) -> str:
        # Return current display name (hostname preferred), also synced to _attr_name for registry display
        base = self._name_override or self._hostname or self._ip
        display = f"{base} Network Presence"
        # Keep _attr_name in sync so UI shows hostname if it becomes available
        try:
            if getattr(self, "_attr_name", None) != display:
                self._attr_name = display
        except Exception:
            pass
        return display

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    @property
    def state(self):
        # Explicitly map connection boolean to HA device_tracker states
        try:
            return STATE_HOME if self._is_connected else STATE_NOT_HOME
        except Exception:
            # Fallback to let HA compute if something unexpected happens
            return None

    @property
    def source_type(self):
        # Reflect that presence is determined by the router
        return SourceType.ROUTER

    @property
    def available(self) -> bool:
        # Available when the coordinator successfully fetched data
        return bool(getattr(self.coordinator, "last_update_success", True))

    @property
    def device_info(self):
        # Group all trackers under the router device
        return {
            "identifiers": {(DOMAIN, self._host)},
            "name": "Technicolor CGA Gateway",
            "manufacturer": "Technicolor",
            "configuration_url": f"http://{self._host}/",
        }

    @property
    def extra_state_attributes(self):
        return {
            "mac": self._mac,
            "ip": self._ip,
            "hostname": self._hostname,
            "status_raw": self._status_raw,
            "active_raw": self._active_raw,
            "last_seen": self._last_seen,
            "source": "router",
        }

    def _process_table(self, table: list[dict]):
        # Find by IP first
        found = None
        for dev in table:
            if _normalize_ip(dev.get("ipaddress")) == self._ip:
                found = dev
                break
        if found:
            prev = self._is_connected
            self._apply_device(found)
            _LOGGER.debug(
                "[TCGA][TRACKER] update ip=%s hostname=%s active_raw=%s status_raw=%s -> is_connected=%s",
                self._ip, self._hostname, self._active_raw, self._status_raw, self._is_connected,
            )
            if prev != self._is_connected:
                _LOGGER.info("[TCGA][TRACKER] state change ip=%s %s -> %s", self._ip, prev, self._is_connected)
        else:
            # Not present in table => not connected
            if self._is_connected:
                _LOGGER.info("[TCGA][TRACKER] ip=%s not found in hostTbl; marking not connected", self._ip)
            self._is_connected = False

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        data = self.coordinator.data or {}
        table = data.get("hostTbl", []) or []
        _LOGGER.info("[TCGA][TRACKER] coordinator tick ip=%s table_size=%d avail=%s", self._ip, len(table), self.available)
        self._process_table(table)
        self.async_write_ha_state()

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        _LOGGER.info("[TCGA][TRACKER] async_added_to_hass ip=%s (coordinator)", self._ip)
        # Process current data immediately to avoid 'unknown'
        self._handle_coordinator_update()

    def _coerce_bool(self, value):
        """Mirror sensor.py: map common strings to bool; empty string -> False; unknown -> None."""
        if isinstance(value, bool):
            return value
        s = str(value).strip().lower()
        if s in ("true", "1", "yes", "on"):
            return True
        if s in ("false", "0", "no", "off", "none", ""):
            return False
        return None

    def _is_online(self, dev: dict) -> bool:
        """Mirror sensor presence logic: prefer boolean Active, then Status ONLINE/offline, else fallback."""
        active_val = dev.get("active")
        if active_val is None:
            active_val = dev.get("Active")
        active_bool = self._coerce_bool(active_val)
        if active_bool is not None:
            return bool(active_bool)
        status = str(dev.get("Status", dev.get("status", "")))
        if status.upper() == "ONLINE":
            return True
        if status.lower() == "offline":
            return False
        # fallback: truthy active means online
        return bool(self._coerce_bool(active_val))

    def _apply_device(self, dev: dict):
        self._hostname = dev.get("hostname") or self._hostname
        self._ip = dev.get("ipaddress") or self._ip
        # capture raw fields
        self._active_raw = dev.get("Active", dev.get("active"))
        # Status might come as 'Status' or 'status'
        self._status_raw = dev.get("Status", dev.get("status"))
        # Mirror sensor presence decision
        self._is_connected = self._is_online(dev)
        # Update last seen timestamp when we have a row for this IP
        self._last_seen = datetime.now().isoformat()
