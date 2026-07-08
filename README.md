# Swift Command Home Assistant Integration

This repository contains a custom [Home Assistant](https://www.home-assistant.io/) integration for [Swift Command / Swift Remote](https://www.swiftcommand.co.uk/) connected caravans and motorhomes. It exposes telemetry from the Swift Command cloud, including CAN bus values, and allows limited remote control of on-board systems such as the PSU and lighting.

## Features

* **Account based config flow** – authenticate with your Swift Command credentials directly from the Home Assistant UI.
* **Coordinated polling** – a shared update coordinator manages customer data and CAN bus refreshes with built-in throttling for night hours.
* **Entity coverage** – automatically generates sensors, binary sensors, switches, lights and buttons based on the values present in the API payloads.
* **Diagnostics** – exposes coordinator counters and timestamp sensors, plus a full redacted diagnostics download via the Home Assistant diagnostics panel.
* **Custom service** – call `swift_command.send_can_command` to push manual CAN payloads to your vehicle when needed.

## Requirements

* A working Swift Command / Swift Remote account with a compatible vehicle.
* Home Assistant 2024.11 or newer (the integration relies on modern config flow, options flow and re-authentication helpers).

## Installation

### HACS (recommended)

1. In Home Assistant, open **HACS → Integrations**.
2. Click the overflow menu (⋮) in the top-right and choose **Custom repositories**.
3. Add `https://github.com/holdestmade/swift_command` with the category **Integration**.
4. Search for **Swift Command** in HACS, install it, and restart Home Assistant.

### Manual

1. Copy the `custom_components/swift_command` directory into your Home Assistant `config/custom_components` folder.
2. Restart Home Assistant to load the component.

## Configuration

1. Navigate to **Settings → Devices & Services → + Add Integration** in Home Assistant.
2. Search for **Swift Command** and sign in with the same email address and password you use for the official Swift Command mobile app.
3. After the integration is created you can open the entry's **Configure** dialog to tweak:
   * Update interval (minutes)
   * CAN bus timeout (seconds)
   * Night mode start/end hours (reduces CAN polling overnight)
   * CAN sections to expose (choose which nested sections create entities)

## Available Entities

Depending on the telemetry returned for your vehicle you may see:

* **Sensors** – customer metadata (brand, model, voltages) plus derived power readings calculated from amps × volts.
* **Binary sensors** – PSU states, warning flags, CAN availability and token status.
* **Switches & lights** – remote toggles for the main PSU output and lighting circuits, using optimistic updates for a responsive UI.
* **Buttons** – a manual refresh button that forces an immediate CAN + customer data update.
* **Device tracker** – vehicle GPS coordinates reported by Swift Command.

All entities are attached to a single device representing the vehicle chassis number.

## Services

The integration registers one service: `swift_command.send_can_command`. Supply an `endpoint` (integer appended to the CAN URL) and a JSON-compatible `payload` array. This calls the same helper used by the built-in switch and light platforms.

## Troubleshooting

* Check **Settings → Devices & Services → Swift Command → Diagnostics** for the latest coordinator timestamps and API counters.
* If authentication errors persist, re-run the config flow's re-auth step when prompted and ensure MFA is disabled on the Swift Command website.
* The integration intentionally throttles CAN refreshes overnight – use the **Update Now** button entity to force an on-demand refresh when needed.

## Development

Issues and feature requests can be logged on the [project issue tracker](https://github.com/holdestmade/swift_command/issues). Contributions are welcome; please open a pull request describing your change.
