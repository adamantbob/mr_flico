# Project Instructions: KiCad Konnect Automation & Hardware Standards

This workspace is an active KiCad 10 avionics and flight computer hardware design (`mike_rocket`). All AI agents working in this repository must strictly adhere to the KiCad Konnect workflow and skills.

---

## 1. Mandatory KiCad Konnect Skill Activation

Before performing any action or answering non-trivial hardware design questions, always consult and activate the appropriate **KiCad Konnect skills**:

- **`kicad-schematic`**: Mandatory whenever viewing, modifying, wiring, or annotating schematics, hierarchical sheets, or running Electrical Rules Check (ERC).
- **`kicad-pcb`**: Mandatory whenever placing footprints, routing traces, creating/modifying zones and ground planes, adjusting stackup, or running Design Rules Check (DRC).
- **`kicad-review`**: Mandatory when performing hardware design reviews, auditing power distribution networks (PDN), checking decoupling capacitors, or validating signal integrity.
- **`kicad-library`**: Mandatory when searching parts, sourcing components (LCSC / JLCPCB), creating symbols, or assigning footprints.
- **`kicad-manufacture`**: Mandatory when exporting Gerbers, drill files, Pick-and-Place (CPL) centroid data, or Bill of Materials (BOM) for fabrication.

*(If executing complex autonomous tasks or delegating work, invoke the `pcb-designer` subagent).*

---

## 2. Project Architecture & Hierarchy

- **Project Root**: `mike_rocket.kicad_pro`
- **Main Schematic**: `mike_rocket.kicad_sch`
- **PCB Layout**: `mike_rocket.kicad_pcb`
- **Hierarchical Sheets**:
  - `RP2350.kicad_sch` (Main MCU, clocks, decoupling, boot strapping)
  - `powerusb.kicad_sch` (Power management, LDO/buck regulators, USB-C protection)
  - `ALT&IMU.kicad_sch` (Barometer / Altimeter & 6-DoF/9-DoF IMU sensors)
  - `GPS.kicad_sch` (GNSS receiver & antenna matching circuit)
  - `rfm95.kicad_sch` (LoRa telemetry transceiver & RF matching)
  - `flash.kicad_sch` (SPI NOR Flash memory for flight logging)
- **Custom Libraries**:
  - Footprints: `rocket.pretty/`
  - Symbols: `rocket.kicad_sym`

---

## 3. KiCad Konnect MCP Integration Guidelines

1. **Native IPC Over Raw File Edits**:
   - Always prefer using the KiCad Konnect MCP tools (`kicad-konnect_kicad-konnect_*`) via the KiCad 10 IPC API over manual regex/text edits on `.kicad_sch` or `.kicad_pcb` files.
   - When raw edits are unavoidable, preserve all existing UUIDs (`uuid`) and element identifiers. Never regenerate or reorder unchanged blocks.
   - Ensure KiCad 10 is running with the KiCad API enabled (**Edit -> Preferences -> Plugins -> Enable KiCad API**).

2. **Automated Verification**:
   - **Post-Schematic Edits**: Always run ERC (`kicad-cli sch erc` or Konnect review tools) to detect floating pins, duplicate designators, or power driver conflicts.
   - **Post-Layout Edits**: Always run DRC (`kicad-cli pcb drc` or Konnect review tools) to detect clearance violations, unrouted nets, or fabrication boundary infractions.
   - Never silence or dismiss warnings without reporting them clearly to the user.

3. **Design Best Practices**:
   - **Decoupling**: Keep bypass capacitors as physically close as possible to their corresponding IC power pins with short, direct returns to the ground plane.
   - **Ground Reference**: Maintain an unbroken solid ground plane (`GND`) beneath MCU high-speed traces (SPI, QSPI, USB, RF). Avoid crossing split planes.
   - **Thermal Reliefs**: Utilize spoke relief on through-hole connections to copper pours unless dedicated high-current thermal transfer is required.
