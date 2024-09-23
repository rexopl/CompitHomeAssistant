from homeassistant.const import Platform

MANURFACER_NAME = "Compit"
DOMAIN = "compit"
API_URL = "https://inext.compit.pl/mobile/v2/compit"
REGULAR_API_URL = "https://inext.compit.pl/api"

PLATFORMS = [
    Platform.CLIMATE,
    Platform.SELECT,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH
]

PARAMS_GROUPS = [
    "Wentylacja - odczyty"
]