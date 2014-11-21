import uuid
import os

SEPARATOR = "_"


def create_workspace(component_names):
    d = SEPARATOR.join(component_names).lower()

    if os.path.exists(d):
        d = d + SEPARATOR + str(uuid.uuid1())

    os.makedirs(d)

    return d
