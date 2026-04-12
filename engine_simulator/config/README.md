# Engine Configurations

## SDM25_final.json
**Last year's car (2024-2025 season)**
- 4-1 exhaust: 661.7mm × 38.1mm (1.5") primaries, 100mm × 50.8mm (2") collector
- 3.0L plenum
- 161.5mm × 38mm intake runners
- 20mm restrictor, Cd=0.926 (calibrated)
- Drivetrain efficiency: 91% (calibrated)
- Stock 2007 CBR600RR cams (corrected to service manual specs)
- **Calibrated against DynoJet data from May 3, 2025**
- Mean error: 2.5 HP (3.7%), max error: 4.3 HP at 11,000 RPM

## SDM26_working_v1.json
**This year's car (2025-2026 season)**
- 4-2-1 exhaust: 308mm × 32-34mm primaries, 392mm × 38mm secondaries, 100mm × 50mm collector
- 1.5L plenum
- 245mm × 38mm intake runners
- 20mm restrictor, Cd=0.967 (vapor-smoothed ASA insert)
- Drivetrain efficiency: 1.0 (not yet calibrated — no dyno data for this config)
- Stock 2007 CBR600RR cams (corrected to service manual specs)
- **Not yet validated against dyno data**

## cbr600rr.json
Working config — currently a copy of SDM26_working_v1. This is what the GUI and default scripts load.
