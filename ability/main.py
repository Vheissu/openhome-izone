import base64
import json
import re

from src.agent.capability import MatchingCapability
from src.agent.capability_worker import CapabilityWorker
from src.main import AgentWorker


HELPER_COMMAND = 'python3 "${OPENHOME_IZONE_HELPER:-$HOME/.openhome-izone/openhome_izone.py}"'


class OpenHomeIZoneCapability(MatchingCapability):
    worker: AgentWorker = None
    capability_worker: CapabilityWorker = None

    # Do not change following tag of register capability
    #{{register capability}}

    def call(self, worker: AgentWorker):
        self.worker = worker
        self.capability_worker = CapabilityWorker(self)
        self.worker.session_tasks.create(self.run())

    async def run(self):
        try:
            user_request = await self.capability_worker.wait_for_complete_transcription()
            if not user_request:
                await self.capability_worker.speak("I did not catch the air conditioning request.")
                return

            status = await self._helper_json("status --json", timeout=20)
            weather = {}
            if self._request_needs_weather(user_request):
                weather = await self._helper_json("weather --json", timeout=20, allow_error=True)

            plan = self._build_plan(user_request, status, weather)
            intent = str(plan.get("intent", "apply")).lower()

            if intent in ("status", "help", "question"):
                await self.capability_worker.speak(
                    plan.get("spoken_summary") or self._status_summary(status)
                )
                return

            if plan.get("requires_confirmation"):
                summary = plan.get("spoken_summary") or "I can update the iZone settings."
                await self.capability_worker.speak("%s Should I go ahead?" % summary)
                confirmation = await self.capability_worker.user_response()
                if not self._is_confirmation(confirmation):
                    await self.capability_worker.speak("No problem. I have left the air conditioning unchanged.")
                    return

            apply_result = await self._apply_plan(plan)
            spoken = self._final_response(plan, apply_result)
            await self.capability_worker.speak(spoken)
        except Exception as exc:
            self._log_error("iZone ability failed: %s" % exc)
            await self.capability_worker.speak(
                "I could not reach the iZone controller. Check that the local iZone helper is running and on the same network as the iZone bridge."
            )
        finally:
            self.capability_worker.resume_normal_flow()

    def _is_confirmation(self, text):
        cleaned = str(text or "").strip().lower()
        if re.search(r"\b(no|nope|nah|cancel|stop|don't|do not|not now)\b", cleaned):
            return False
        return cleaned in (
            "yes",
            "yep",
            "yeah",
            "yea",
            "confirm",
            "confirmed",
            "proceed",
            "go ahead",
            "sure",
            "please do",
            "do it",
        ) or bool(re.search(r"\b(yes|yep|yeah|sure|confirm|proceed)\b", cleaned))

    def _request_needs_weather(self, text):
        lowered = text.lower()
        return any(
            word in lowered
            for word in (
                "weather",
                "outside",
                "outdoor",
                "forecast",
                "optimise",
                "optimize",
                "best setting",
                "best settings",
                "efficient",
                "economical",
                "humidity",
                "humid",
                "rain",
                "storm",
                "hot day",
                "cold day",
            )
        )

    async def _helper_json(self, args, timeout=10, allow_error=False):
        command = "%s %s" % (HELPER_COMMAND, args)
        raw = await self._exec_local(command, timeout=timeout)
        payload = self._parse_json_payload(raw)
        if not allow_error and not payload.get("ok", False):
            raise RuntimeError(payload.get("error") or "iZone helper returned an error")
        return payload

    async def _exec_local(self, command, timeout=10):
        try:
            response = await self.capability_worker.exec_local_command(command, timeout=timeout)
        except TypeError:
            response = await self.capability_worker.exec_local_command(command)
        return self._response_to_text(response)

    def _response_to_text(self, response):
        if isinstance(response, dict):
            for key in ("data", "stdout", "output", "message"):
                if key in response and response[key] is not None:
                    return str(response[key])
            return json.dumps(response)
        return str(response)

    def _parse_json_payload(self, raw):
        raw = raw.strip()
        try:
            return json.loads(raw)
        except Exception:
            start = raw.find("{")
            end = raw.rfind("}")
            if start >= 0 and end > start:
                return json.loads(raw[start : end + 1])
            raise

    def _build_plan(self, user_request, status, weather):
        system_prompt = self._planner_prompt(status, weather)
        raw_plan = self.capability_worker.text_to_text_response(
            user_request,
            [],
            system_prompt,
        )
        plan = self._extract_json(raw_plan)
        if not isinstance(plan, dict):
            raise RuntimeError("Planner did not return a JSON object")
        plan.setdefault("intent", "apply")
        plan.setdefault("requires_confirmation", False)
        plan.setdefault("spoken_summary", "")
        plan.setdefault("system", {})
        plan.setdefault("zones", [])
        plan.setdefault("close_other_zones", False)
        return plan

    def _planner_prompt(self, status, weather):
        return """
You convert a user's iZone ducted air conditioning request into one JSON object.
Return JSON only. Do not include markdown or explanations.

This is a voice-first smart-home ability. The user may speak casually after a trigger word such as
"aircon", "air conditioning", "climate", "climate control", "iZone", "heater", "cooling", "heating", or "ducted air".
Ignore the trigger word itself and focus on the HVAC request.

Current iZone status:
%s

Weather context, when available:
%s

Allowed JSON schema:
{
  "intent": "apply" | "status" | "help" | "question",
  "spoken_summary": "short user-facing summary",
  "requires_confirmation": true | false,
  "system": {
    "power": "on" | "off",
    "mode": "cool" | "heat" | "vent" | "dry" | "auto",
    "fan": "low" | "medium" | "high" | "auto" | "top",
    "temperature": 15.0-30.0,
    "sleep_timer": minutes
  },
  "zones": [
    {
      "name": "zone name from current status",
      "mode": "open" | "close" | "auto",
      "temperature": 15.0-30.0,
      "max_airflow": 0-100,
      "min_airflow": 0-100
    }
  ],
  "close_other_zones": true | false
}

Rules:
- Use only zone names that exist in the current status. If a requested zone is unclear, set intent to "question" and ask which zone.
- If the user asks what is happening, whether the aircon is on, which rooms are active, current temperatures, air quality, humidity, or status, set intent to "status".
- Do not close other zones unless the user says "only", "except", "just", "bedtime", "working in", or otherwise clearly requests a limited-zone setup.
- For "turn on the aircon", set power on and keep existing mode, fan, and temperature unless the user asks for a change.
- For "turn off the aircon", "turn off climate", or "turn off the system", set only {"power": "off"}.
- For "turn off the study", "close the lounge", or "switch off that room", close that zone, not the whole system.
- For cooling, prefer mode "cool", fan "auto", and 23 C unless the user gave another value.
- For heating or "make it warmer", prefer mode "heat", fan "auto", and 21 C unless the user gave another value.
- For "make it cooler", reduce the relevant current setpoint by 1 C and use cool mode. For "much cooler", reduce by 2 C.
- For "make it warmer", increase the relevant current setpoint by 1 C and use heat mode. For "much warmer", increase by 2 C.
- Always output absolute temperatures in the JSON. Do not output deltas.
- For a specific zone comfort request, set system power on, the requested mode if any, and set that zone to auto at the target temperature.
- For "open", use zone mode "open". For "close", "off", or "shut", use zone mode "close". For normal comfort control, use zone mode "auto".
- For "all zones", "whole house", or "everywhere", include every zone from the current status in zones.
- For "only", "just", "bedtime", "sleep", "night", "working in", or "movie mode", target the named room or rooms and set close_other_zones true.
- For "good night" or "bedtime", prefer the bedroom-like zone if named, cool or heat conservatively, quiet fan, and a sleep timer if the user gave a duration.
- For "quiet", "low noise", or "sleep", set fan "low". For "boost", "quick", or "blast", set fan "high"; use "top" only if the user explicitly says top fan.
- For "dehumidify", "humid", or "dry it out", set mode "dry" and power on.
- For "fresh air", "fan only", "ventilate", or "circulate", set mode "vent" and power on.
- For airflow requests, use max_airflow for phrases like "limit airflow", "cap airflow", or "set airflow to N percent"; use min_airflow only when the user explicitly says minimum airflow.
- For weather optimisation, use the weather context plus indoor return air temperature. Prefer a conservative energy-saving setting and explain it in spoken_summary.
- Set requires_confirmation true for broad weather optimisation, closing multiple zones, sleep timers over 4 hours, or any plan that is inferred rather than explicitly requested.
- Set requires_confirmation true if the command would turn the whole system off while any zone appears active.
- If the user asks for something unsupported, set intent "question" with a brief spoken_summary explaining what to ask instead.
- Keep spoken_summary under 24 words.
""" % (
            json.dumps(status, sort_keys=True),
            json.dumps(weather, sort_keys=True),
        )

    def _extract_json(self, text):
        text = str(text).strip()
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
        try:
            return json.loads(text)
        except Exception:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if not match:
                raise
            return json.loads(match.group(0))

    async def _apply_plan(self, plan):
        encoded = base64.b64encode(json.dumps(plan).encode("utf-8")).decode("ascii")
        return await self._helper_json("apply --plan-b64 '%s' --json" % encoded, timeout=30)

    def _status_summary(self, status):
        system = status.get("system", {})
        zones = status.get("zones", [])
        power = "on" if system.get("power") == "on" else "off"
        mode = system.get("mode", "unknown")
        setpoint = system.get("setpoint_c")
        active_zones = [
            zone.get("name")
            for zone in zones
            if str(zone.get("mode", "")).lower() in ("open", "auto", "override", "constant")
        ]
        active_text = "No zones are active."
        if active_zones:
            active_text = "Active zones: %s." % ", ".join(active_zones[:6])
            if len(active_zones) > 6:
                active_text = "%s and %s more." % (active_text.rstrip("."), len(active_zones) - 6)
        return "iZone is %s, %s mode, set to %s C. %s" % (
            power,
            mode,
            setpoint,
            active_text,
        )

    def _final_response(self, plan, apply_result):
        if not apply_result.get("ok", False):
            return "I could not update the iZone system: %s" % (
                apply_result.get("error") or "unknown error"
            )
        actions = apply_result.get("actions", [])
        if plan.get("spoken_summary"):
            return "%s Done." % plan["spoken_summary"]
        if not actions:
            return "No iZone changes were needed."
        return "Done. I applied %s iZone change%s." % (
            len(actions),
            "" if len(actions) == 1 else "s",
        )

    def _log_error(self, message):
        try:
            self.worker.editor_logging_handler.error(message)
        except Exception:
            pass
