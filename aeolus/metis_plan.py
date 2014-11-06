import json
import re


def cn_to_armonic(cn):
    return cn[0].upper() + cn[1:]

def xpath_to_armonic(xpath):
    """Remove initial @ and the suffix. Be careful, this is shitty...
    @Wordpress/ActiveWithNfs/get_website_Wordpress-1 -> Wordpress/ActiveWithNfs/get_website
    @Nfs_server/Active/get_dir -> Nfs_server/Active/get_dir
    """
    lifecycle = re.search('@(.*)/.*/.*', xpath).group(1)
    ret = re.search('@(.*)', xpath).group(1)
    regex = '(.*)(_%s.*)' % lifecycle
    tmp = re.search(regex, ret)
    if tmp is not None:
        ret = tmp.group(1)
    return ret


def plan_to_json(metis_output_file):
    """Convert the Metis output to json."""
    plans = []
    with open(metis_output_file, 'r') as f:
        for l in f:
            if re.match('.*Create instance.*', l):
                component_name = re.search('instance (.*):.*:', l).group(1)
                component_name = cn_to_armonic(component_name)
                state_name = re.search(':.*:(.*)]', l).group(1)
                plans.append({'type': 'create','component_name': component_name, 'state': state_name})
            elif re.match('.*change state.*', l):
                component_name = re.search('= \[(.*) :', l).group(1)
                component_name = cn_to_armonic(component_name)
                state_from = re.search('from (.*) to', l).group(1)
                state_to = re.search('to (.*)]', l).group(1)
                plans.append({'type': 'change', 'component_name': component_name, 'state_from': state_from, 'state_to': state_to})
            elif re.match('.*invoke.*', l):
                component_name = re.search('= \[(.*) :', l).group(1)
                component_name = cn_to_armonic(component_name)
                provide_target = re.search('method (.*) of', l).group(1)
                provide_target = xpath_to_armonic(provide_target)
                component_target = re.search('of (.*)]', l).group(1)
                component_target = cn_to_armonic(component_target)

                plans.append({'type': 'binding', 'component_name': component_name, 'provide_target': provide_target, 'component_target': component_target})
            else:
                pass

    return plans


class Binding(object):
    def __init__(self, component_target, provide_target):
        self.component_target = component_target
        self.provide_target = provide_target

    def __repr__(self):
        return "(%s, %s)" % (self.component_target, self.provide_target)

class State(object):
    def __init__(self, name):
        self.name = name
        self.bindings = []

    def __repr__(self):
        return "State(%s) -> %s" % (self.name, self.bindings)

def provide_metis_to_armonic(provide_xpath):
    return re.search('@(.*)_.*-.*$', provide_xpath).group(1)

def build_tree(event_list):
    components = {}
    bindings = []
    for e in event_list:
        if e['type'] == 'create':
            components[e['component_name']] = [State(e['state'])]
        elif e['type'] == 'change':
            components[e['component_name']].append(State(e['state_to']))
            if bindings != []:
                for b in bindings:
                    
                    components[b['component_name']][-1].bindings.append(
                        Binding(b['component_target'],
                                provide_metis_to_armonic(b['provide_target'])))
                bindings = []
        elif e['type'] == 'binding':
            bindings.append(e)
            #components[e['component_name']][-1].bindings.append((e['component_target'], e['provide_target']))
        
    import pprint
    pprint.pprint(components)
    
    return components


#def generate_specialisation(components, root_components):
    


# def walk(components):

#     for (k, c) in components.iteritems():
#         for s in c:
#             if s.bindings != []:
#                 print s

def get_root_component(components):
    """Return the component that is never required."""
    print components.keys()
    # The list of all components
    comp = [k for k in components.keys()]

    for (k, c) in components.iteritems():
        for s in c:
            for b in s.bindings:
                try:
                    # We remove from the components name list required components
                    comp.remove(b.component_target)
                except ValueError:
                    pass
        
    if len(comp) != 1:
        raise Exception("get_root_component() fails!")
    return comp[0]

# import sys

# file_metis = sys.argv[1]
# root_provide = sys.argv[2]
# plan = plan_to_json(file_metis)


# for p in  plan:
#     print p


# print
# components = build_tree(plan)

# root_component = get_root_component(components)
# print "Root Component: %s" % root_component

# #walk(components)


    
