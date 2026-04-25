#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_DIR="${OPENHOME_IZONE_INSTALL_DIR:-$HOME/.openhome-izone}"

mkdir -p "$INSTALL_DIR"
cp "$ROOT_DIR/local/openhome_izone.py" "$INSTALL_DIR/openhome_izone.py"
chmod +x "$INSTALL_DIR/openhome_izone.py"

if [[ ! -f "$INSTALL_DIR/config.json" ]]; then
  cat > "$INSTALL_DIR/config.json" <<'JSON'
{
  "bridge_ip": "",
  "location_name": "",
  "country_code": "",
  "latitude": null,
  "longitude": null,
  "zone_aliases": {},
  "defaults": {
    "cool_setpoint_c": 23.0,
    "heat_setpoint_c": 21.0,
    "fan": "auto"
  }
}
JSON
fi

echo "Installed helper to $INSTALL_DIR/openhome_izone.py"
echo "Configure weather with:"
echo "  python3 $INSTALL_DIR/openhome_izone.py configure --location \"Your suburb, Australia\" --country-code AU"
echo "Test iZone discovery with:"
echo "  python3 $INSTALL_DIR/openhome_izone.py status --json"

