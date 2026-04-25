# Voice Command Guide

OpenHome handles the device wake word separately. This ability is activated by
dashboard trigger words such as `aircon`, `air conditioning`, `climate`,
`climate control`, `iZone`, `heater`, `cooling`, `heating`, and `ducted air`.

Use the trigger word naturally at the start of the request:

```text
Aircon, cool the study to 22.
Climate, what rooms are active?
iZone, only heat the master bedroom tonight.
```

## Core controls

| Goal | Example phrase | Behaviour |
| --- | --- | --- |
| Turn the system on | `Aircon, turn on cooling.` | Powers on and keeps existing settings unless a mode or temperature is requested. |
| Turn the system off | `Aircon, turn off the system.` | Powers off the whole iZone system. |
| Cool | `Aircon, cool the house to 23.` | Uses cool mode, fan auto, and the requested setpoint. |
| Heat | `Heater, warm the house to 21.` | Uses heat mode, fan auto, and the requested setpoint. |
| Fan only | `Climate, ventilate the house.` | Uses vent mode. |
| Dry mode | `Aircon, dry out the house.` | Uses dry mode for humid weather. |
| Fan speed | `Aircon, set fan to low.` | Supports low, medium, high, auto, and top. |
| Sleep timer | `Aircon, turn off in two hours.` | Sets the iZone sleep timer. Long timers require confirmation. |

## Zone controls

Use your real iZone zone names, or configure aliases with the local helper.

| Goal | Example phrase | Behaviour |
| --- | --- | --- |
| Control one zone | `Aircon, cool the study to 22.` | Powers on, targets that zone, and sets it to auto control. |
| Open a zone | `Aircon, open the dining room.` | Opens the named zone. |
| Close a zone | `Aircon, close upstairs.` | Closes the named zone without turning off the whole system. |
| Only one area | `Aircon, only cool the lounge.` | Targets the named zone and closes the other zones after confirmation. |
| Multiple zones | `Climate, heat the lounge and dining to 21.` | Targets each named zone. |
| Whole house | `Aircon, open all zones.` | Applies the zone action to every zone. |
| Airflow cap | `Aircon, limit the study airflow to 60 percent.` | Sets the zone max airflow. |

## Comfort phrases

These are translated into concrete iZone settings:

- `Make it cooler` lowers the relevant setpoint by 1 C.
- `Make it much cooler` lowers it by 2 C.
- `Make it warmer` raises the relevant setpoint by 1 C.
- `Make it much warmer` raises it by 2 C.
- `Quiet mode` sets fan speed to low.
- `Boost` sets fan speed to high.
- `Top fan` uses iZone's top fan speed.
- `Bedtime` or `good night` prefers quiet fan and limited-zone control when a room is named.

## Weather-aware commands

Weather optimisation uses Open-Meteo with the location configured in the local
helper. It does not require an API key.

```text
Climate, optimise the aircon for today's weather.
Aircon, what setting is best with the weather outside?
Aircon, it is humid. Dry out the house.
```

Broad weather optimisation asks for confirmation before changing the system.

## Status questions

```text
iZone, is the aircon on?
Climate, what rooms are active?
Aircon, what is the current temperature?
Aircon, what is the humidity inside?
```

The ability reports the system power, mode, setpoint, and active zones.
