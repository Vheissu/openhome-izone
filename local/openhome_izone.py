#!/usr/bin/env python3
"""Local iZone helper for the OpenHome iZone Climate ability."""

import argparse
import base64
import http.client
import json
import os
import re
import socket
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path


DISCOVERY_PORT = 12107
HTTP_TIMEOUT = 5
HTTP_RETRIES = 4
HTTP_RETRY_DELAY = 0.25
HTTP_MIN_GAP = 0.25

MODES = {"cool": 1, "heat": 2, "vent": 3, "dry": 4, "auto": 5}
MODES_REV = {value: key for key, value in MODES.items()}
FAN_SPEEDS = {"low": 1, "medium": 2, "high": 3, "auto": 4, "top": 5}
FAN_REV = {value: key for key, value in FAN_SPEEDS.items()}
ZONE_MODES = {"open": 1, "close": 2, "closed": 2, "auto": 3, "override": 4, "constant": 5}
ZONE_MODES_REV = {value: key for key, value in ZONE_MODES.items()}
TRANSIENT_RESPONSES = {"{ERROR}", "ERROR", "{BUSY}", "BUSY"}
REQUEST_ERRORS = (socket.timeout, TimeoutError, OSError, http.client.HTTPException)

CONFIG_DIR = Path(os.environ.get("OPENHOME_IZONE_CONFIG_DIR", "~/.openhome-izone")).expanduser()
CONFIG_FILE = CONFIG_DIR / "config.json"
BRIDGE_CACHE = CONFIG_DIR / "bridge_ip"

DEFAULT_CONFIG = {
    "bridge_ip": "",
    "location_name": "",
    "country_code": "",
    "latitude": None,
    "longitude": None,
    "zone_aliases": {},
    "defaults": {
        "cool_setpoint_c": 23.0,
        "heat_setpoint_c": 21.0,
        "fan": "auto"
    }
}


def print_json(payload):
    print(json.dumps(payload, indent=None, sort_keys=True))


def merge_dict(base, overlay):
    merged = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config():
    config = dict(DEFAULT_CONFIG)
    if CONFIG_FILE.exists():
        with CONFIG_FILE.open() as handle:
            config = merge_dict(config, json.load(handle))
    if os.environ.get("OPENHOME_IZONE_BRIDGE_IP"):
        config["bridge_ip"] = os.environ["OPENHOME_IZONE_BRIDGE_IP"]
    if os.environ.get("OPENHOME_IZONE_LOCATION"):
        config["location_name"] = os.environ["OPENHOME_IZONE_LOCATION"]
    if os.environ.get("OPENHOME_IZONE_COUNTRY_CODE"):
        config["country_code"] = os.environ["OPENHOME_IZONE_COUNTRY_CODE"]
    if os.environ.get("OPENHOME_IZONE_LATITUDE"):
        config["latitude"] = float(os.environ["OPENHOME_IZONE_LATITUDE"])
    if os.environ.get("OPENHOME_IZONE_LONGITUDE"):
        config["longitude"] = float(os.environ["OPENHOME_IZONE_LONGITUDE"])
    return config


def save_config(config):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with CONFIG_FILE.open("w") as handle:
        json.dump(config, handle, indent=2, sort_keys=True)


def normalize_key(value):
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())


def temp_to_setpoint(value):
    temp = float(value)
    if temp < 15 or temp > 30:
        raise ValueError("temperature must be between 15.0 and 30.0 C")
    return int(round(temp * 2) * 50)


def airflow_value(value):
    airflow = int(round(float(value) / 5) * 5)
    return max(0, min(100, airflow))


def label_temp(value):
    if value is None:
        return None
    return round(float(value) / 100.0, 1)


class IZoneClient:
    def __init__(self, config):
        self.config = config
        self._last_request_started = 0.0

    def bridge_ip(self):
        configured_ip = self.config.get("bridge_ip")
        if configured_ip:
            return configured_ip
        if BRIDGE_CACHE.exists() and time.time() - BRIDGE_CACHE.stat().st_mtime < 3600:
            cached = BRIDGE_CACHE.read_text().strip()
            if cached:
                return cached
        return self.discover_bridge()

    def discover_bridge(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(3)
        try:
            sock.sendto(b"IASD", ("255.255.255.255", DISCOVERY_PORT))
            data, addr = sock.recvfrom(1024)
        except socket.timeout:
            raise RuntimeError("No iZone bridge found on the local network")
        finally:
            sock.close()

        text = data.decode("utf-8", errors="replace")
        parts = dict(part.split("_", 1) for part in text.split(",") if "_" in part)
        ip = parts.get("IP", addr[0])
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        BRIDGE_CACHE.write_text(ip)
        time.sleep(0.5)
        return ip

    def _pace_requests(self):
        now = time.monotonic()
        wait_for = HTTP_MIN_GAP - (now - self._last_request_started)
        if wait_for > 0:
            time.sleep(wait_for)
        self._last_request_started = time.monotonic()

    def _post(self, endpoint, payload):
        ip = self.bridge_ip()
        body = json.dumps(payload)
        self._pace_requests()
        conn = http.client.HTTPConnection(ip, 80, timeout=HTTP_TIMEOUT)
        try:
            conn.request("POST", endpoint, body=body, headers={"Content-Type": "application/json"})
            response = conn.getresponse()
            raw = response.read().decode("utf-8", errors="replace").strip()
        finally:
            conn.close()
        if raw.endswith("{OK}"):
            raw = raw[:-4]
        return raw

    def json_request(self, endpoint, payload, retries=HTTP_RETRIES):
        last_raw = ""
        last_error = None
        for attempt in range(max(1, int(retries))):
            try:
                raw = self._post(endpoint, payload)
            except REQUEST_ERRORS as exc:
                last_error = exc
                if attempt < retries - 1:
                    time.sleep(HTTP_RETRY_DELAY * (attempt + 1))
                    continue
                raise

            last_raw = raw
            if raw.strip().upper() in TRANSIENT_RESPONSES and attempt < retries - 1:
                time.sleep(HTTP_RETRY_DELAY * (attempt + 1))
                continue
            try:
                return json.loads(raw)
            except json.JSONDecodeError as exc:
                last_error = exc
                if attempt < retries - 1:
                    time.sleep(HTTP_RETRY_DELAY * (attempt + 1))
                    continue
                snippet = raw if len(raw) <= 140 else raw[:137] + "..."
                raise RuntimeError("Bridge returned non-JSON response: %r" % snippet)
        raise RuntimeError("Bridge returned non-JSON response: %r" % last_raw) from last_error

    def query_system(self):
        return self.json_request(
            "/iZoneRequestV2",
            {"iZoneV2Request": {"Type": 1, "No": 0, "No1": 0}},
            retries=max(4, HTTP_RETRIES),
        )

    def query_zone(self, index):
        return self.json_request(
            "/iZoneRequestV2",
            {"iZoneV2Request": {"Type": 2, "No": index, "No1": 0}},
            retries=max(3, HTTP_RETRIES),
        )

    def command(self, payload):
        last_raw = ""
        for attempt in range(HTTP_RETRIES):
            try:
                raw = self._post("/iZoneCommandV2", payload)
            except REQUEST_ERRORS:
                if attempt < HTTP_RETRIES - 1:
                    time.sleep(HTTP_RETRY_DELAY * (attempt + 1))
                    continue
                raise

            last_raw = raw
            normalized = raw.strip().upper()
            if normalized in ("", "OK"):
                return raw
            if normalized in TRANSIENT_RESPONSES and attempt < HTTP_RETRIES - 1:
                time.sleep(HTTP_RETRY_DELAY * (attempt + 1))
                continue
            return raw
        return last_raw

    def status(self):
        system_response = self.query_system()
        system = system_response["SystemV2"]
        zones = []
        for index in range(int(system.get("NoOfZones", 0))):
            zone_response = self.query_zone(index)
            zone = zone_response.get("ZonesV2", zone_response)
            zones.append({
                "index": zone.get("Index", index),
                "name": zone.get("Name", "Zone %s" % index),
                "type": zone.get("ZoneType"),
                "mode": ZONE_MODES_REV.get(zone.get("Mode"), str(zone.get("Mode"))),
                "temperature_c": label_temp(zone.get("Temp")),
                "setpoint_c": label_temp(zone.get("Setpoint")),
                "max_airflow": zone.get("MaxAir"),
                "min_airflow": zone.get("MinAir"),
            })
        return {
            "ok": True,
            "bridge_ip": self.bridge_ip(),
            "system": {
                "power": "on" if system.get("SysOn") else "off",
                "mode": MODES_REV.get(system.get("SysMode"), str(system.get("SysMode"))),
                "fan": FAN_REV.get(system.get("SysFan"), str(system.get("SysFan"))),
                "sleep_timer": system.get("SleepTimer"),
                "setpoint_c": label_temp(system.get("Setpoint")),
                "return_air_c": label_temp(system.get("Temp")),
                "supply_air_c": label_temp(system.get("Supply")),
                "humidity": system.get("InRh"),
                "eco2": system.get("IneCO2"),
                "tvoc": system.get("InTVOC"),
                "zone_count": system.get("NoOfZones"),
            },
            "zones": zones,
        }


def build_alias_index(config, zones):
    index = {}
    for zone in zones:
        name = zone["name"]
        keys = {normalize_key(name), normalize_key(zone["index"])}
        aliases = config.get("zone_aliases", {}).get(name, [])
        aliases += config.get("zone_aliases", {}).get(str(zone["index"]), [])
        for alias in aliases:
            keys.add(normalize_key(alias))
        for key in keys:
            if key:
                index.setdefault(key, set()).add(zone["index"])
    return index


def resolve_zone_targets(selector, zones, config):
    if selector is None:
        raise ValueError("zone target requires a name or index")
    if isinstance(selector, int) or str(selector).isdigit():
        index = int(selector)
        if any(zone["index"] == index for zone in zones):
            return [index]
        raise ValueError("zone index %s was not found" % index)

    key = normalize_key(selector)
    if key in ("all", "everywhere", "house", "home", "*"):
        return [zone["index"] for zone in zones]

    alias_index = build_alias_index(config, zones)
    if key in alias_index:
        return sorted(alias_index[key])

    matches = []
    for zone in zones:
        zone_key = normalize_key(zone["name"])
        if key and (key in zone_key or zone_key in key):
            matches.append(zone["index"])
    if len(matches) == 1:
        return matches
    if len(matches) > 1:
        raise ValueError("zone name %r matched multiple zones" % selector)
    raise ValueError("zone %r was not found" % selector)


def normalize_mode(mode):
    if mode is None or mode == "":
        return None
    key = str(mode).strip().lower()
    if key not in MODES:
        raise ValueError("mode must be one of: %s" % ", ".join(sorted(MODES)))
    return key


def normalize_fan(fan):
    if fan is None or fan == "":
        return None
    key = str(fan).strip().lower()
    if key not in FAN_SPEEDS:
        raise ValueError("fan must be one of: %s" % ", ".join(sorted(FAN_SPEEDS)))
    return key


def normalize_zone_mode(mode):
    if mode is None or mode == "":
        return None
    key = str(mode).strip().lower()
    if key == "closed":
        key = "close"
    if key not in ZONE_MODES:
        raise ValueError("zone mode must be open, close, or auto")
    return key


def decode_plan(plan_b64):
    try:
        raw = base64.b64decode(plan_b64.encode("ascii")).decode("utf-8")
        plan = json.loads(raw)
    except Exception as exc:
        raise ValueError("plan-b64 must contain base64 encoded JSON") from exc
    if not isinstance(plan, dict):
        raise ValueError("plan must be a JSON object")
    return plan


def apply_plan(plan, client, config, dry_run=False):
    status = client.status()
    zones = status["zones"]
    actions = []

    def send(label, payload):
        action = {"label": label, "payload": payload}
        if dry_run:
            action["response"] = "DRY_RUN"
        else:
            action["response"] = client.command(payload)
        actions.append(action)

    intent = str(plan.get("intent", "apply")).lower()
    if intent in ("status", "help", "question"):
        return {"ok": True, "actions": [], "status": status}
    if intent != "apply":
        raise ValueError("unsupported intent: %s" % intent)

    system = plan.get("system") or {}
    power = str(system.get("power", "")).lower()

    if power == "off":
        send("system power off", {"SysOn": 0})
        return {"ok": True, "actions": actions}
    if power == "on":
        send("system power on", {"SysOn": 1})
        time.sleep(0.2)
    elif power not in ("", "none"):
        raise ValueError("power must be on or off")

    mode = normalize_mode(system.get("mode"))
    if mode:
        send("system mode %s" % mode, {"SysMode": MODES[mode]})
        time.sleep(0.2)

    fan = normalize_fan(system.get("fan"))
    if fan:
        send("system fan %s" % fan, {"SysFan": FAN_SPEEDS[fan]})
        time.sleep(0.2)

    if system.get("temperature") not in (None, ""):
        setpoint = temp_to_setpoint(system["temperature"])
        send("system setpoint %.1f C" % (setpoint / 100.0), {"SysSetpoint": setpoint})
        time.sleep(0.2)

    if system.get("sleep_timer") not in (None, ""):
        minutes = int(system["sleep_timer"])
        if minutes < 0 or minutes > 720:
            raise ValueError("sleep_timer must be between 0 and 720 minutes")
        send("system sleep timer %s minutes" % minutes, {"SysSleepTimer": minutes})
        time.sleep(0.2)

    zone_plans = plan.get("zones") or []
    target_indexes = set()
    expanded_zone_plans = []
    for zone_plan in zone_plans:
        selector = zone_plan.get("index", zone_plan.get("name"))
        targets = resolve_zone_targets(selector, zones, config)
        for index in targets:
            target_indexes.add(index)
            expanded = dict(zone_plan)
            expanded["index"] = index
            expanded_zone_plans.append(expanded)

    if plan.get("close_other_zones") and target_indexes:
        for zone in zones:
            if zone["index"] not in target_indexes:
                send("close zone %s" % zone["name"], {"ZoneMode": {"Index": zone["index"], "Mode": ZONE_MODES["close"]}})
                time.sleep(0.15)

    for zone_plan in expanded_zone_plans:
        index = int(zone_plan["index"])
        zone_name = next((zone["name"] for zone in zones if zone["index"] == index), "Zone %s" % index)
        zone_mode = normalize_zone_mode(zone_plan.get("mode"))
        if zone_mode:
            send("zone %s mode %s" % (zone_name, zone_mode), {"ZoneMode": {"Index": index, "Mode": ZONE_MODES[zone_mode]}})
            time.sleep(0.15)
        if zone_plan.get("temperature") not in (None, ""):
            setpoint = temp_to_setpoint(zone_plan["temperature"])
            send("zone %s setpoint %.1f C" % (zone_name, setpoint / 100.0), {"ZoneSetpoint": {"Index": index, "Setpoint": setpoint}})
            time.sleep(0.15)
        if zone_plan.get("max_airflow") not in (None, ""):
            airflow = airflow_value(zone_plan["max_airflow"])
            send("zone %s max airflow %s%%" % (zone_name, airflow), {"ZoneMaxAir": {"Index": index, "MaxAir": airflow}})
            time.sleep(0.15)
        if zone_plan.get("min_airflow") not in (None, ""):
            airflow = airflow_value(zone_plan["min_airflow"])
            send("zone %s min airflow %s%%" % (zone_name, airflow), {"ZoneMinAir": {"Index": index, "MinAir": airflow}})
            time.sleep(0.15)

    return {"ok": True, "actions": actions}


def geocode_location(config):
    if config.get("latitude") is not None and config.get("longitude") is not None:
        return {
            "name": config.get("location_name") or "configured location",
            "latitude": float(config["latitude"]),
            "longitude": float(config["longitude"]),
            "timezone": "auto",
        }

    location = config.get("location_name")
    if not location:
        raise RuntimeError("No location configured. Run configure --location \"Suburb, Country\".")

    params = {
        "name": location,
        "count": 1,
        "language": "en",
        "format": "json",
    }
    if config.get("country_code"):
        params["countryCode"] = config["country_code"]
    url = "https://geocoding-api.open-meteo.com/v1/search?%s" % urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=8) as response:
        payload = json.loads(response.read().decode("utf-8"))
    results = payload.get("results") or []
    if not results:
        raise RuntimeError("No geocoding result for %r" % location)
    result = results[0]
    return {
        "name": result.get("name", location),
        "admin1": result.get("admin1", ""),
        "country": result.get("country", ""),
        "latitude": result["latitude"],
        "longitude": result["longitude"],
        "timezone": result.get("timezone", "auto"),
    }


def fetch_weather(config):
    location = geocode_location(config)
    params = {
        "latitude": location["latitude"],
        "longitude": location["longitude"],
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,rain,weather_code,cloud_cover,wind_speed_10m,wind_gusts_10m,is_day",
        "daily": "temperature_2m_max,temperature_2m_min,apparent_temperature_max,precipitation_probability_max",
        "forecast_days": 1,
        "timezone": "auto",
    }
    url = "https://api.open-meteo.com/v1/forecast?%s" % urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=8) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return {
        "ok": True,
        "location": location,
        "current": payload.get("current", {}),
        "current_units": payload.get("current_units", {}),
        "daily": payload.get("daily", {}),
        "daily_units": payload.get("daily_units", {}),
    }


def configure(args):
    config = load_config()
    if args.bridge_ip:
        config["bridge_ip"] = args.bridge_ip
    if args.location:
        config["location_name"] = args.location
    if args.country_code:
        config["country_code"] = args.country_code.upper()
    if args.latitude is not None:
        config["latitude"] = args.latitude
    if args.longitude is not None:
        config["longitude"] = args.longitude
    for alias_spec in args.alias or []:
        if "=" not in alias_spec:
            raise ValueError("alias must look like Zone Name=alias one,alias two")
        zone_name, aliases = alias_spec.split("=", 1)
        config.setdefault("zone_aliases", {})[zone_name.strip()] = [
            alias.strip() for alias in aliases.split(",") if alias.strip()
        ]
    save_config(config)
    return {"ok": True, "config_file": str(CONFIG_FILE), "config": config}


def command_status(args):
    config = load_config()
    client = IZoneClient(config)
    return client.status()


def command_apply(args):
    config = load_config()
    client = IZoneClient(config)
    plan = decode_plan(args.plan_b64)
    return apply_plan(plan, client, config, dry_run=args.dry_run)


def command_weather(args):
    config = load_config()
    return fetch_weather(config)


def command_self_test(args):
    sample_plan = {
        "intent": "apply",
        "system": {"power": "on", "mode": "cool", "fan": "auto", "temperature": 23},
        "zones": [{"name": "Study", "mode": "auto", "temperature": 23}],
        "close_other_zones": False,
    }
    encoded = base64.b64encode(json.dumps(sample_plan).encode("utf-8")).decode("ascii")
    decoded = decode_plan(encoded)
    assert decoded["system"]["mode"] == "cool"
    assert temp_to_setpoint(22.3) == 2250
    assert airflow_value(83) == 85
    return {"ok": True, "message": "self-test passed"}


def build_parser():
    parser = argparse.ArgumentParser(description="OpenHome iZone local helper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    configure_parser = subparsers.add_parser("configure", help="Create or update local helper config")
    configure_parser.add_argument("--bridge-ip")
    configure_parser.add_argument("--location", help="Weather location, for example: Brisbane, Australia")
    configure_parser.add_argument("--country-code", help="Optional ISO country code for geocoding, for example AU")
    configure_parser.add_argument("--latitude", type=float)
    configure_parser.add_argument("--longitude", type=float)
    configure_parser.add_argument("--alias", action="append", help="Zone alias mapping, e.g. Study=office,work room")
    configure_parser.set_defaults(func=configure)

    status_parser = subparsers.add_parser("status", help="Read iZone system and zone state")
    status_parser.add_argument("--json", action="store_true")
    status_parser.set_defaults(func=command_status)

    apply_parser = subparsers.add_parser("apply", help="Apply a base64 JSON iZone plan")
    apply_parser.add_argument("--plan-b64", required=True)
    apply_parser.add_argument("--dry-run", action="store_true")
    apply_parser.add_argument("--json", action="store_true")
    apply_parser.set_defaults(func=command_apply)

    weather_parser = subparsers.add_parser("weather", help="Read configured local weather")
    weather_parser.add_argument("--json", action="store_true")
    weather_parser.set_defaults(func=command_weather)

    self_test_parser = subparsers.add_parser("self-test", help="Run helper self-test without touching iZone")
    self_test_parser.set_defaults(func=command_self_test)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        payload = args.func(args)
        print_json(payload)
        return 0
    except Exception as exc:
        print_json({"ok": False, "error": str(exc)})
        return 1


if __name__ == "__main__":
    sys.exit(main())

