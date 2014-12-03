import logging
logger = logging.getLogger(__name__)

def get_providers_from_bindings(universe, requirer):
    """Return the list of components name that provide something to the
    requirer."""
    return [b['provider'] for b in universe['bindings'] if b['requirer'] == requirer]
 

def used_locations(configuration):
    """Remove locations that are not used by some components. Sometimes,
    the unmerge can remove all components of a location. This location
    is then empty and is removed from the location list.
    """
    used = []
    for c in configuration['components']:
        if c['location'] not in used:
            used.append(c['location'])

    locations = []
    for l in configuration['locations']:
        if l['name'] in used:
            locations.append(l)

    return locations

def unmerge(universe_merged, merge, local):
    def c_suffix(component_name):
        return int(component_name.split('-')[-1])

    # We upgrade location of local require
    for (binding, origin, temp) in merge:
        for c in universe_merged['components']:
            if c['type'] == origin:
                for c1 in universe_merged['components']:
                    if c1['type'] == temp and c_suffix(c1['name']) == c_suffix(c['name']):
                        logger.debug("Changing location of (local) component %s:  %s -> %s" % (c['name'], c['location'], c1['location']))
                        c['location'] = c1['location']

    for binding in universe_merged['bindings']:
        for (b, origin, temp) in merge:
            if binding['port'] == b:
                binding['requirer'] = origin+"-"+str(c_suffix(binding['requirer']))

    # We update the location of local require by using 'local' info.
    # For instance, the component Http has to be deployed on the same
    # locaiton of component Wordpress.
    for c1, c2 in local:
        location = None
        logger.debug("Upgrading local component type %s (local to %s type)" % (c2, c1))
        for c in universe_merged['components']:
            # We are looking for the location of source component
            if c['type'] == c1:
                location = c['location']
                requirer_name = c['name']
                logger.debug("\tProcessing source component '%s'..." % requirer_name)

                providers_name = get_providers_from_bindings(universe_merged, requirer_name)
                for c in universe_merged['components']:
                    if c['name'] in providers_name and c['type'] == c2:
                        logger.debug("Changing location of component %s:  %s -> %s" % (c['name'], c['location'], location))
                        c['location'] = location

    # We remove unused locations
    universe_merged['locations'] = used_locations(universe_merged)

    return universe_merged
