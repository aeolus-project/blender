import re
import json
import logging
import pprint

logger = logging.getLogger(__name__)


def format_xpath(xpath):
    return re.search('@(.*)', xpath).group(1)


def absolute_xpath(component_name, xpath):
    return component_name + "/" + xpath


def split_absolute_xpath(xpath):
    """Return the tuple (component_name, xpath)"""
    s = xpath.split("/")
    component_name = s[0]
    xpath = "/".join(s[1:])
    return (component_name, xpath)

def find_generic(specialisation, specialized):
    """Returns the generic xpath associated to the specialized xpath in the bindings list."""
    for b in specialisation:
        if b[1] == specialized:
            return b[0]
    raise Exception("The generic xpath associated to '%s' has not been found." % specialized)


def get_root_component_from_configuration(configuration):
    bindings = configuration['bindings']
    components = []
    
    for b in bindings:
        cn = b['requirer']
        if cn not in components:
            components.append(cn)

    for b in bindings:
        cn = b['provider']
        if cn in components:
            components.remove(cn)

    if len(components) != 1:
        logger.error("More than one root component:")
        for c in components:
            logger.error("\t%s" % c)
        raise Exception("More than one root component.")
    
    return components[0]


def generate_specialization_initial(configuration, armonic_info):
    root_component = get_root_component_from_configuration(configuration)
    initial = armonic_info["initial"]
    return [root_component + "///*",
            root_component + "/" + initial]


def generate_specialization(configuration, armonic_info):
    bindings = configuration['bindings']
    specialisation = armonic_info['specialisation']
    specialize = []
    
    configuration = []
    for b in bindings:
        xpath = format_xpath(b['port'])
        b['requirer']
        g = absolute_xpath(b['provider'], find_generic(specialisation, xpath))
        s = absolute_xpath(b['provider'], xpath)
        specialize.append([g, s])
        #configuration.append()

    return {'specialize': specialize}


def generate_lfm(specialisation, configuration):
    lfm = []
    for s in specialisation:
        generic_xpath = split_absolute_xpath(s[0])[1]
        cn = split_absolute_xpath(s[1])[0]

        # We search the location of this component name in the
        # configuration files
        for c in configuration['components']:
            if c['name'] == cn:
                lfm.append([
                    absolute_xpath(cn, generic_xpath),
                    c['location']])


    # We have to order the list of LFM in order to respect the child in next steps.
    ordered_components = generate_ordered_deployment_list(configuration)

    ordered_lfms = []
    for c in ordered_components:
        for l in lfm:
            if l[0].startswith(c):
                ordered_lfms.append(l)
                lfm.remove(l)
                break

    return ordered_lfms


def get_location(configuration, component_name):
    for c in configuration['components']:
        if c['name'] == component_name:
            return c['location']
    raise Exception("Component %s not found in configuration" % component_name)


def generate_multiplicity(configuration, armonic_info):
    multiplicity = {}
    for require, provider in armonic_info['multiplicity'].items():
        for binding in configuration['bindings']:
            xpath = format_xpath(binding['port'])
            if xpath == provider:
                abs_xpath = binding['requirer'] + "/" + require
                location = get_location(configuration, binding['provider'])
                if abs_xpath in multiplicity:
                    multiplicity[abs_xpath].append(location)
                else:
                    multiplicity[abs_xpath]=[location]

    acc = []
    for k, v in multiplicity.items():
        acc.append([k, v])

    return acc


def generate_ordered_deployment_list(configuration):
    """Return a ordered list of component. The first one is the root
    component. Then the graph is walked in depth first."""
    def walk(bindings, component_name):
        acc = []
        for b in bindings:
            if b['requirer'] == component_name:
                acc.append(b['provider'])
                acc += walk(bindings, b['provider'])
        return acc

    root_component = get_root_component_from_configuration(configuration)
    return [root_component] + walk(configuration['bindings'], root_component)


def generate_replay(configuration, armonic_info):
    """Take configuration and armonic_info in json and return a replay
    json struct.

    """
    replay = generate_specialization(configuration, armonic_info)

    initial = generate_specialization_initial(configuration, armonic_info)
    replay['specialize'].insert(0, initial)


    lfm = generate_lfm(replay['specialize'], configuration)
    replay['lfm'] = lfm
    replay['multiplicity'] = generate_multiplicity(configuration, armonic_info)
    return replay

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--configuration', type=str, required=True)
    parser.add_argument('--armonic-info', type=str, required=True)
    
    args = parser.parse_args()

    file_configuration = args.configuration
    file_armonic_info = args.armonic_info

    with open(file_configuration, 'r') as f:
        configuration = json.load(f)

    with open(file_armonic_info, 'r') as f:
        armonic_info = json.load(f)

    replay = generate_replay(configuration, armonic_info)

    print json.dumps(replay, indent=2)

    import pprint
    pprint.pprint(generate_multiplicity(configuration, armonic_info))

