"""Constants for Voxprint."""

from typing import Final

DOMAIN: Final = "voxprint"

APP_SLUG: Final = "voxprint"
APP_PORT: Final = 10340
API_VERSION: Final = 1
# The embedding model the app must run. Voiceprints and replies from any other model are never compared.
MODEL: Final = "wespeaker_resnet34_lm"

STORAGE_KEY: Final = DOMAIN
STORAGE_VERSION: Final = 1

CONF_SATELLITES: Final = "satellites"
CONF_THRESHOLD: Final = "threshold"
CONF_PERSON: Final = "person"

SUBENTRY_SPEAKER: Final = "speaker"

# A starting point, measured on recordings rather than at a satellite. docs/enrollment.md says how to set it.
DEFAULT_THRESHOLD: Final = 0.5
# Two speakers both above the threshold and closer than this to each other: nobody is named.
AMBIGUITY_MARGIN: Final = 0.05
MIN_SPEECH_S: Final = 0.5
# While enrolling, audio this unlike the speaker's voiceprint so far (music, noise) is skipped.
ENROLL_FLOOR: Final = 0.1
ENROLL_MINUTES: Final = 30
REQUEST_TIMEOUT_S: Final = 3
