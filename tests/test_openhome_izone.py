import base64
import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "local" / "openhome_izone.py"
SPEC = importlib.util.spec_from_file_location("openhome_izone", MODULE_PATH)
izone = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(izone)


class FakeClient:
    def __init__(self):
        self.commands = []

    def status(self):
        return {
            "ok": True,
            "system": {"power": "off", "mode": "cool", "fan": "low", "setpoint_c": 23.0},
            "zones": [
                {"index": 0, "name": "Dining"},
                {"index": 1, "name": "Study"},
                {"index": 2, "name": "Master"},
            ],
        }

    def command(self, payload):
        self.commands.append(payload)
        return "OK"


class HelperTests(unittest.TestCase):
    def test_decode_plan(self):
        plan = {"intent": "apply", "system": {"power": "on"}}
        encoded = base64.b64encode(json.dumps(plan).encode("utf-8")).decode("ascii")
        self.assertEqual(izone.decode_plan(encoded), plan)

    def test_rounding(self):
        self.assertEqual(izone.temp_to_setpoint(22.3), 2250)
        self.assertEqual(izone.temp_to_setpoint(22.24), 2200)
        self.assertEqual(izone.airflow_value(83), 85)

    def test_resolve_zone_alias(self):
        zones = [{"index": 0, "name": "Dining"}, {"index": 1, "name": "Study"}]
        config = {"zone_aliases": {"Study": ["office", "work room"]}}
        self.assertEqual(izone.resolve_zone_targets("office", zones, config), [1])
        self.assertEqual(izone.resolve_zone_targets("din", zones, config), [0])
        self.assertEqual(izone.resolve_zone_targets("all", zones, config), [0, 1])

    def test_apply_plan_dry_run(self):
        client = FakeClient()
        plan = {
            "intent": "apply",
            "system": {"power": "on", "mode": "cool", "fan": "auto", "temperature": 22.3},
            "zones": [{"name": "Study", "mode": "auto", "temperature": 22}],
            "close_other_zones": True,
        }
        result = izone.apply_plan(plan, client, {"zone_aliases": {}}, dry_run=True)
        self.assertTrue(result["ok"])
        labels = [action["label"] for action in result["actions"]]
        self.assertIn("system power on", labels)
        self.assertIn("system setpoint 22.5 C", labels)
        self.assertIn("close zone Dining", labels)
        self.assertIn("close zone Master", labels)
        self.assertIn("zone Study mode auto", labels)
        self.assertEqual(client.commands, [])


if __name__ == "__main__":
    unittest.main()

