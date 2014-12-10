import logging

INFINITY = 1000
REQUIRE_CARDINALITY_PATTERN = "42"

FILE_ARMONIC_INFO = "armonic-info.json"
FILE_UNIVERSE_MERGED = "universe-merged.json"
FILE_UNIVERSE_UNMERGED = "universe.json"
FILE_UNIVERSE = "universe.json"

FILE_CONFIGURATION = "configuration-unmerged.json"

FILE_ARMONIC_REPLAY = "replay.json"
FILE_ARMONIC_REPLAY_FILLED = "replay-filled.json"

FILE_METIS_PLAN_JSON = "plan-metis.json"

FILE_SPECIFICATION = "specification.spec"
FILE_INITIAL_CONFIGURATION = "initial_configuration.json"

logger = logging.getLogger("aeolus")
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
format = '%(levelname)-7s %(module)s %(message)s'
ch.setFormatter(logging.Formatter(format))
logger.addHandler(ch)


def remove_default_handlers():
    logger.removeHandler(ch)


def get_root_logger():
    return logger


repositories_to_openstack = {"mbs": "mbs-armonic-latest", "debian": "debian-wheezy-armonic-latest"}

# How many machine if each repository we create
MACHINE_NUMBER = 4

# This is used to create machine name based on the repositories.
repositories_to_server_name = {
    "mbs": "mbs%d@aeiche.innovation.mandriva.com",
    "debian": "debian%d@aeiche.innovation.mandriva.com"}
