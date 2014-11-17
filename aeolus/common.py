import logging

INFINITY = 1000

FILE_ARMONIC_INFO = "armonic-info.json"
FILE_UNIVERSE_MERGED = "universe-merged.json"
FILE_UNIVERSE_UNMERGED = "universe.json"
FILE_UNIVERSE = "universe.json"

FILE_CONFIGURATION = "configuration-unmerged.json"

FILE_ARMONIC_REPLAY = "replay.json"
FILE_ARMONIC_REPLAY_FILLED = "replay-filled.json"

FILE_METIS_PLAN_JSON = "plan-metis.json"


logger = logging.getLogger("aeolus")
logger.setLevel(logging.INFO)
ch = logging.StreamHandler()
format = '%(levelname)-7s %(module)s %(message)s'
ch.setFormatter(logging.Formatter(format))
logger.addHandler(ch)

repositories_to_openstack = {"mbs": "mbs-armonic-latest", "debian": "debian-wheezy-armonic-latest"}
