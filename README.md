# openhome-izone

OpenHome ability for controlling iZone ducted air conditioning with voice.

This project is built for community sharing: it contains the OpenHome ability
package, a small local helper for iZone's LAN API, install instructions, and
tests. It does not require cloud credentials or paid weather APIs.

## What it can do

- Turn the iZone system on or off.
- Set mode: cool, heat, vent, dry, or auto.
- Set fan speed: low, medium, high, auto, or top.
- Set whole-system temperatures.
- Open, close, or auto-control individual zones.
- Set per-zone temperatures and airflow limits.
- Close all other zones for "only this room" style commands.
- Read current system and zone status.
- Optimise conservative settings using local weather from Open-Meteo.

Example phrases:

- "Aircon, turn on cooling."
- "Air conditioning, cool the study to 22."
- "Climate, make the lounge a bit warmer."
- "iZone, only cool the master bedroom tonight."
- "Aircon, set fan speed to low."
- "Aircon, boost cooling."
- "Climate, dry out the house."
- "Aircon, open all zones."
- "Aircon, close upstairs."
- "Climate, optimise the aircon based on today's weather."
- "iZone, what rooms are active?"

See [docs/voice-commands.md](docs/voice-commands.md) for a fuller command map.

## Architecture

OpenHome abilities run in the OpenHome runtime. Local iZone bridges live on a
home LAN, so this ability uses OpenHome Local Connect and `exec_local_command()`
to call a local helper on the user's computer.

```text
OpenHome voice request
  -> ability/main.py
  -> OpenHome Local Connect exec_local_command()
  -> ~/.openhome-izone/openhome_izone.py
  -> iZone bridge on local network
```

The local helper uses iZone's V2 local API:

- UDP discovery on port 12107 with `IASD`.
- HTTP `POST /iZoneRequestV2` for status.
- HTTP `POST /iZoneCommandV2` for commands.

## Install the local helper

Run this on the computer that has OpenHome Local Connect running and can reach
the iZone bridge on the same LAN:

```bash
./scripts/install-local-helper.sh
python3 ~/.openhome-izone/openhome_izone.py configure --location "Your suburb, Australia" --country-code AU
python3 ~/.openhome-izone/openhome_izone.py status --json
```

If discovery does not find your bridge, set it explicitly:

```bash
python3 ~/.openhome-izone/openhome_izone.py configure --bridge-ip 192.168.1.50
```

Optional zone aliases:

```bash
python3 ~/.openhome-izone/openhome_izone.py configure \
  --alias "Master=main bedroom,bedroom" \
  --alias "Study=office,work room"
```

## Upload to OpenHome

Package the ability:

```bash
./scripts/package-ability.sh
```

Then in the OpenHome dashboard:

- Go to `My Abilities`.
- Choose `Add Custom Ability`.
- Name it `iZone Climate`.
- Select category `Skill`.
- Choose `Upload Custom Ability`.
- Upload `dist/openhome-izone-ability.zip`.
- Add trigger words: `aircon`, `air conditioning`, `climate`, `climate control`, `iZone`, `heater`, `cooling`, `heating`, `ducted air`.
- No third-party API keys are required.

More detailed dashboard notes are in [docs/openhome-dashboard.md](docs/openhome-dashboard.md).

## Local helper commands

Read status:

```bash
python3 ~/.openhome-izone/openhome_izone.py status --json
```

Read weather:

```bash
python3 ~/.openhome-izone/openhome_izone.py weather --json
```

Run the helper self-test without touching the AC:

```bash
python3 ~/.openhome-izone/openhome_izone.py self-test
```

## Safety notes

- The ability asks for confirmation before broad inferred changes, such as
  weather optimisation or closing multiple zones.
- The language model produces a JSON plan, not shell commands.
- The local helper validates modes, temperatures, airflow ranges, and zone names
  before sending anything to the iZone bridge.
- Unknown zones are rejected rather than guessed.
- Temperatures are limited to 15.0-30.0 C.

## Development

Run tests:

```bash
python3 -m unittest discover -s tests
```

Package check:

```bash
./scripts/package-ability.sh
unzip -l dist/openhome-izone-ability.zip
```

## References

- OpenHome ability docs: https://docs.openhome.com/ability
- OpenHome build guide: https://docs.openhome.com/building-abilities/how-to-build
- OpenHome Local Connect: https://docs.openhome.com/building-abilities/local-connect
- Open-Meteo forecast API: https://open-meteo.com/en/docs
- Open-Meteo geocoding API: https://open-meteo.com/en/docs/geocoding-api
