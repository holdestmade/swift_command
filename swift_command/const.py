"""Constants for the Swift Command integration."""

DOMAIN = "swift_command"
PLATFORMS = ["sensor", "device_tracker", "binary_sensor", "switch", "light", "button"]

# API URLs
LOGIN_URL = "https://www.swiftcommand.co.uk/api/login"
CUSTOMER_DATA_URL = "https://www.swiftcommand.co.uk/api/customers/{customer_id}/1"
CAN_BUS_BASE_URL = "https://www.swiftcommand.co.uk/api/can/{asset_id}"

# Timeouts and Intervals
DEFAULT_CAN_BUS_TIMEOUT = 15  # seconds
DEFAULT_UPDATE_INTERVAL = 60  # minutes
DEFAULT_NIGHT_START = 20  # 8 PM
DEFAULT_NIGHT_END = 8  # 8 AM

# CAN sections exposed by default
DEFAULT_CAN_SECTIONS = [
    "psuStatus1","psuStatus2","psuWarnings1","psuWarnings2",
    "levels2","levels3","currentOptionsBank3","currentOptionsBank1","currentOptionsBank2"
]
