# Swift Command

Custom component for [Home Assistant](https://www.home-assistant.io/) integrating Swift Command / Swift Remote systems.

## Installation
1. Copy the `swift_command` directory into your Home Assistant `custom_components` folder.
2. Restart Home Assistant.

## Configuration
The integration uses a config flow available from the Home Assistant UI (`Settings -> Devices & Services -> Add Integration`). Search for **Swift Command** and follow the prompts to complete setup.

## Entities
Depending on your hardware, the component can expose switches, lights, sensors and other entities exposed by the Swift Command API.

## Services
Additional services are defined in `services.yaml` inside the component directory for interacting with the system.
