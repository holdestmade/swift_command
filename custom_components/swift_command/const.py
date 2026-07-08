"""Constants for the Swift Command integration."""
from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "swift_command"
PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.DEVICE_TRACKER,
    Platform.LIGHT,
    Platform.SENSOR,
    Platform.SWITCH,
]

# API URLs
LOGIN_URL = "https://www.swiftcommand.co.uk/api/login"
CUSTOMER_DATA_URL = "https://www.swiftcommand.co.uk/api/customers/{customer_id}/1"
CAN_BUS_BASE_URL = "https://www.swiftcommand.co.uk/api/can/{asset_id}"

# Options keys
CONF_UPDATE_INTERVAL = "update_interval"
CONF_CAN_BUS_TIMEOUT = "can_bus_timeout"
CONF_NIGHT_START = "night_start_hour"
CONF_NIGHT_END = "night_end_hour"
CONF_CAN_SECTIONS = "can_sections"

# Services
SERVICE_SEND_CAN_COMMAND = "send_can_command"
ATTR_ENDPOINT = "endpoint"
ATTR_PAYLOAD = "payload"

# CAN endpoint used for the toggle commands sent by the light/switch entities
CAN_COMMAND_ENDPOINT = 11

# Timeouts and Intervals
DEFAULT_API_TIMEOUT = 10  # seconds
DEFAULT_CAN_BUS_TIMEOUT = 15  # seconds
DEFAULT_UPDATE_INTERVAL = 60  # minutes
DEFAULT_NIGHT_START = 20  # 8 PM
DEFAULT_NIGHT_END = 8  # 8 AM

# Minimum time between CAN bus fetches during night hours
NIGHT_CAN_UPDATE_INTERVAL = timedelta(hours=4)

# CAN sections exposed by default
DEFAULT_CAN_SECTIONS = [
    "psuStatus1",
    "psuStatus2",
    "psuWarnings1",
    "psuWarnings2",
    "levels2",
    "levels3",
    "currentOptionsBank3",
    "currentOptionsBank1",
    "currentOptionsBank2",
]
