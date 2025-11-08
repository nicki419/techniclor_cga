import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD, CONF_HOST
from .const import DOMAIN

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Technicolor CGA."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=vol.Schema({
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Required(CONF_HOST, default="192.168.0.1"): str,
            }))

        return self.async_create_entry(title="Technicolor CGA", data=user_input)

    @staticmethod
    def async_get_options_flow(config_entry):
        """Return the options flow handler."""
        return TechnicolorCGAOptionsFlowHandler(config_entry)

class TechnicolorCGAOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle Technicolor CGA options."""

    @staticmethod
    def async_supports_options_flow(config_entry: config_entries.ConfigEntry) -> bool:
        # Indicate to HA that this integration supports an Options flow
        return True

    def __init__(self, config_entry: config_entries.ConfigEntry):
        self.config_entry = config_entry

    def _normalize_mac(self, mac: str) -> str:
        mac = (mac or "").strip().lower().replace("-", ":")
        # zero-pad segments
        parts = [p.zfill(2) for p in mac.split(":") if p]
        return ":".join(parts)

    def _normalize_ip(self, ip: str) -> str:
        return (ip or "").strip()

    def _parse_disabled_macs(self, text: str) -> list[str]:
        items = []
        for raw in (text or "").replace("\n", ",").split(","):
            val = raw.strip()
            if not val:
                continue
            items.append(self._normalize_mac(val))
        return sorted(set(items))

    def _parse_disabled_ips(self, text: str) -> list[str]:
        items = []
        for raw in (text or "").replace("\n", ",").split(","):
            val = raw.strip()
            if not val:
                continue
            items.append(self._normalize_ip(val))
        return sorted(set(items))

    def _parse_name_overrides_mac(self, text: str) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for line in (text or "").splitlines():
            if not line.strip():
                continue
            if "=" in line:
                mac, name = line.split("=", 1)
            elif ":" in line:
                # allow mac: name
                mac, name = line.split(":", 1)
            else:
                # ignore invalid line
                continue
            mac = self._normalize_mac(mac)
            name = name.strip()
            if mac and name:
                mapping[mac] = name
        return mapping

    def _parse_name_overrides_ip(self, text: str) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for line in (text or "").splitlines():
            if not line.strip():
                continue
            if "=" in line:
                ip, name = line.split("=", 1)
            elif ":" in line:
                ip, name = line.split(":", 1)
            else:
                continue
            ip = self._normalize_ip(ip)
            name = name.strip()
            if ip and name:
                mapping[ip] = name
        return mapping

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            # Validate values
            scan = int(user_input.get("scan_interval", 300))
            if scan < 10:
                scan = 10
            disabled_macs_text = user_input.get("disabled_macs", "")
            names_macs_text = user_input.get("name_overrides", "")
            disabled_ips_text = user_input.get("disabled_ips", "")
            names_ips_text = user_input.get("name_overrides_ip", "")
            disabled_macs = self._parse_disabled_macs(disabled_macs_text)
            names_macs = self._parse_name_overrides_mac(names_macs_text)
            disabled_ips = self._parse_disabled_ips(disabled_ips_text)
            names_ips = self._parse_name_overrides_ip(names_ips_text)
            return self.async_create_entry(
                title="Options",
                data={
                    "scan_interval": scan,
                    "disabled_macs": disabled_macs,
                    "name_overrides": names_macs,
                    "disabled_ips": disabled_ips,
                    "name_overrides_ip": names_ips,
                },
            )

        current_scan = self.config_entry.options.get("scan_interval", 300)
        current_disabled_macs = ", ".join(self.config_entry.options.get("disabled_macs", []))
        current_names_map_macs: dict = self.config_entry.options.get("name_overrides", {})
        current_names_macs = "\n".join(f"{mac} = {name}" for mac, name in current_names_map_macs.items())

        current_disabled_ips = ", ".join(self.config_entry.options.get("disabled_ips", []))
        current_names_map_ips: dict = self.config_entry.options.get("name_overrides_ip", {})
        current_names_ips = "\n".join(f"{ip} = {name}" for ip, name in current_names_map_ips.items())

        schema = vol.Schema({
            vol.Required("scan_interval", default=current_scan): int,
            vol.Optional("disabled_ips", default=current_disabled_ips): str,
            vol.Optional("name_overrides_ip", default=current_names_ips): str,
            vol.Optional("disabled_macs", default=current_disabled_macs): str,
            vol.Optional("name_overrides", default=current_names_macs): str,
        })
        return self.async_show_form(step_id="init", data_schema=schema)

