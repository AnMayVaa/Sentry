# Phase 8: Alert Station + SOS Button + 3D Enclosures

Full guide (wiring, resistor values, print settings, assembly, demo checklist):
**[docs/Phase8_Alert_Station_SOS_Enclosures.md](../docs/Phase8_Alert_Station_SOS_Enclosures.md)**

```
Phase8_Next_Phase/
├── Phase8_RX_Node/          RX sensor firmware: CSI + siren + hold-2s SOS button
├── Phase8_Alert_Station/    caregiver Alert Station firmware (ESP32 + buzzer + LED + button)
├── previews/            open in a browser: viewer/ (interactive 3D boxes), overview/ (one-page infographic)
├── firmware_tests/          runs both sketches on a PC with simulated pins/UDP/time
│   └── run_tests.sh
└── enclosures/
    ├── scad/                parametric OpenSCAD sources (edit sentry_enclosure.scad)
    ├── stl/                 ready-to-print parts, already in print orientation
    ├── png/                 preview renders
    ├── build.sh             re-export STL + PNG and run the checks
    └── check_stl.py         manifold / printability / fit-collision checks
```

Pins (both devices): LED GPIO 2 (via 220 Ω), active buzzer GPIO 4, button GPIO 17 to GND.

Quick checks:

```bash
bash Phase8_Next_Phase/firmware_tests/run_tests.sh
python3 Phase8_Next_Phase/enclosures/check_stl.py
python -m pytest Phase4_Multi_Node/tests -q
```

Before uploading: copy `secrets.example.h` to `secrets.h` in each sketch folder and fill in your Wi-Fi. `secrets.h` is git-ignored.
