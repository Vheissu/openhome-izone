# OpenHome Dashboard Setup

1. Package the ability:

   ```bash
   ./scripts/package-ability.sh
   ```

2. Open the OpenHome dashboard and go to `My Abilities`.

3. Choose `Add Custom Ability`.

4. Use these fields:

   - Name: `iZone Climate`
   - Category: `Skill`
   - Description: `Voice control for iZone ducted air conditioning through OpenHome Local Connect.`
   - Trigger Words: `aircon`, `air conditioning`, `AC`, `climate`, `iZone`, `heater`, `cooling`
   - Template: `Upload Custom Ability`
   - Code upload: `dist/openhome-izone-ability.zip`
   - Third Party API Keys: none

5. Install the local helper on the machine running OpenHome Local Connect:

   ```bash
   ./scripts/install-local-helper.sh
   python3 ~/.openhome-izone/openhome_izone.py configure --location "Your suburb, Australia" --country-code AU
   python3 ~/.openhome-izone/openhome_izone.py status --json
   ```

The helper must run on a computer that can reach the iZone bridge on the local
network. It uses the iZone V2 local API and Open-Meteo for optional weather
optimisation.

