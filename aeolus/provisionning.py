import novaclient.v1_1.client
import novaclient.exceptions
import novaclient.client

import logging
import os

# HACK TO AVOID DEBUG MSG OF NOVALICLIENT
# novaclient.client._logger.setLevel(logging.INFO)

USER = os.getenv("OS_USERNAME")
PASSWORD = os.getenv("OS_PASSWORD")
TENANT = os.getenv("OS_TENANT_NAME")
AUTH_URL = os.getenv("OS_AUTH_URL")

logger = logging.getLogger("aeolus." + __name__)

FLAVOR = "m1.tiny"


def boot(name, image_name):
    client = novaclient.v1_1.client.Client(
        USER,
        PASSWORD,
        TENANT,
        auth_url=AUTH_URL,
        service_type="compute")

    image = None
    for i in client.images.list():
        if i.name == image_name:
            image = i
            break
    if image is None:
        msg = "Image %s not found" % image_name
        logger.error(msg)
        raise Exception(msg)

    flavor = None
    for i in client.flavors.list():
        if i.name == FLAVOR:
            flavor = i
            break
    if flavor is None:
        msg = "Flavor %s doen't exist" % FLAVOR
        logger.error(msg)
        raise Exception(msg)

    logger.debug("Booting location %s", name)
    return client.servers.create(
        name,
        image,
        flavor,
        meta={"armonic_xmpp_domain": "aeiche.innovation.mandriva.com"})
