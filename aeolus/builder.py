import os
import json
import logging
import common

import armonic.utils
from utils import get_lifecycle, get_state
from pprint import pprint
import workspace

logger = logging.getLogger("aeolus." + __name__)


class Binding(object):
    """
    :param require: Provide object that require something
    :type require: Provide
    :param provide: Provide object that provide something
    :type provide: Provide
    :type type: "local | external"
   """
    def __init__(self, require_xpath, type, provide_xpath, arity):
        self.require_xpath = require_xpath
        self.provide_xpath = provide_xpath
        self.type = type
        self.arity = arity

    def __repr__(self):
        return "%s [%s] -> %s (%s)" % (self.require_xpath, self.type, self.provide_xpath, self.arity)


class Component(object):
    def __init__(self, name, lfm):
        self.name = name
        # Contain a state path list.
        self.lfm = lfm
        self.states = []
        self.bindings = []

    def get_state(self, name):
        """Add a state to the component and return it. The path to reach this
        state is computed and each states of this path is added to the
        component state path list."""
        state_xpath = "//"+self.name+"/"+name
        path = self.lfm.state_goto_path(state_xpath)[0]['paths']
        if len(path) != 1:
            raise Exception("Number of paths to reach %s must be 1" % state_xpath)
        path = [p[0] for p in path[0]]

        self._merge_path(path)


        state = None
        for s in self.states:
            if s.name == name:
                state = s

        if state is None:
            state = State(name)
            self.states.append(state)

        return state

    def _propagate(self):
        """This proagate require and provide to successor states"""
        requires = []
        provides = []
        for s in self.states:
            r = requires + s.requires
            p = provides + s.provides
            s.requires += requires
            s.provides += provides
            requires = r
            provides = p

    def to_json(self):
        states = []
        self._propagate()
        prev = self.states[0].to_json()
        prev.update({'initial': True})
        states.append(prev)
        for s in self.states[1:]:
            cur = s.to_json()
            prev.update({'successors': [s.name]})
            states.append(cur)
            prev = cur

        return {'name': self.name,
                'states': states}

    def _merge_path(self, paths):
        """We try to append paths to state list"""
        if len(self.states) > len(paths):
            for i in range(len(paths)):
                if self.states[i].name != paths[i]:
                    print "Pathss can not be merged:"
                    print "states: %s" % [s.name for s in self.states]
                    print "paths  : %s" % paths
                    raise Exception("Paths can not be merged")
        else:
            i = 0
            while i < len(self.states):
                if self.states[i].name != paths[i]:
                    print "Pathss can not be merged:"
                    print "states: %s" % [s.name for s in self.states]
                    print "paths  : %s" % paths
                    raise Exception("Paths can not be merged")
                i = i+1
            # We append new states to state list
            for p in paths[i:]:
                self.states.append(State(p))


class Require(object):
    def __init__(self, port, multiplicity):
        self.port = port
        self.multiplicity = multiplicity


class Provide(Require):
    def __init__(self, port, multiplicity):
        self.port = port
        self.multiplicity = multiplicity


class State():
    def __init__(self, name):
        self.name = name
        self.requires = []
        self.provides = []

    def __repr__(self):
        return "{state: %s, requires: %s}" % (self.name, self.requires)

    def to_json(self):
        requires = {}
        for r in self.requires:
            requires.update({'@'+r.port: r.multiplicity})
        provides = {}
        for r in self.provides:
            provides.update({'@'+r.port: r.multiplicity})

        return {'name': self.name,
                'require': requires,
                'provide': provides}


def get_component(components, xpath):
    name = get_lifecycle(xpath)
    
    # First, we create components that provide something
    os = [armonic.utils.OsTypeMBS(), armonic.utils.OsTypeDebian()]
    lfms = []
    for o in os:
        l = armonic.serialize.Serialize(os_type=o)
        lf = name
        state = get_state(xpath)
        state_xpath = "%s/%s" % (lf, state)
        path = l.state_goto_path(state_xpath)[0]['paths']
        if len(path) > 1:
            raise Exception("Number of paths to reach %s must not be greather than 1" % state_xpath)
        if len(path) == 1:
            lfms.append(l)

    if len(lfms) > 1:
        logger.error("%s is available the following OS:" % xpath)
        for l in lfms:
            logger.error("  %s" % l.lf_manager.os_type)
        raise Exception("%s is available on several OS and this is not supported (yet)." % xpath)
    lfm = lfms[0]

    c = None
    for i in components:
        if i.name == name:
            c = i
            break
    if c is None:
        c = Component(name, lfm)
        components.append(c)
    return c


def implementation_v1stateless_json(components):
    implementations = {}
    for c in components:
        implementations.update({
            c.name: [['repository',
                      'stub_package']]})
    return implementations


def implementation_json(components):
    """Wrong version ... ? """
    implementations = {}
    for c in components:
        implementations.update({
            c.name: [
                {'repository': c.lfm.lf_manager.os_type.id,
                 'package': '%s_stub_package' % c.lfm.lf_manager.os_type.id}]})

    return implementations


def repositories_json(implementations):
    """Create repository from implementations. Not well tested..."""
    def append_package(repository, package):
        """Append a package if it is not already in the list"""
        for p in repository['packages']:
            if p['name'] == package:
                return
        repository['packages'].append({'name': package})

    repositories = []
    for component in implementations.itervalues():
        for i in component:
            found = False
            for r in repositories:
                if r['name'] == i['repository']:
                    append_package(r, i['package'])
                    found = True
                    break
            if not found:
                repositories.append({'name': i['repository'], 'packages': [{'name': i['package']}]})
    return repositories


def create_components(initial, bindings):
    """From bindings list, it creates components and return a component list"""
    components = []


    for binding in bindings:
        #r, p, n = binding.require, binding.provide, binding.arity

        state = get_state(binding.provide_xpath)
        c = get_component(components, binding.provide_xpath)
        s = c.get_state(state)
        if binding.type == 'local':
            arity = 1
        else:
            arity = common.INFINITY
        s.provides.append(Provide(binding.provide_xpath, arity))

        # Secondly, we create components that require something
        state = get_state(binding.require_xpath)
        c = get_component(components, binding.require_xpath)
        s = c.get_state(state)
        s.requires.append(Require(binding.provide_xpath, binding.arity))

    # We manually add the state that contains the provide required by
    # the user. It is not necessary added via Bindings because if this
    # state doens't contain any require, it doesn't appear in
    # bindings.
    c = get_component(components, initial.xpath)
    s = c.get_state(get_state(initial.xpath))

    return components


def get_component_cardinality(bindings):
    """Return the list of provide xpath which can be required several
    time. This will be used by the user to choose how many time he
    wants a service.
    """
    cardinality = []
    for b in bindings:
        if b.arity != 1 and b.arity != common.INFINITY:
            cardinality.append(b.provide_xpath)
    return cardinality


def get_non_local_provide(initial, bindings):
    """Return the list of lifecycle and state that are not local
    provide. They will be used by specification.

    :rtype: [{"component":lifecycle, "state": state}]

    """
    non_local = []
    i = initial.xpath
    non_local.append({"component": get_lifecycle(i), "state": get_state(i)})
    for b in bindings:
        if b.type == "external":
            non_local.append({"component": get_lifecycle(b.provide_xpath), "state": get_state(b.provide_xpath)})
    return non_local


def merge_local_require(bindings):
    """"Merge local require in bindings. This takes a list of bindings, and return a new list of bindings."""
    created_bindings = []
    removed_bindings = []
    merge = []
    local = []
    # For all bindings,
    for b in bindings:
        # if it is a local binding
        if b.type == "local":
            # we try to find this provide as a require in an other binding
            for b1 in bindings:
                if b1.require_xpath == b.provide_xpath:
                    logger.debug("created bindings %s" % b)
                    created_bindings.append(Binding(b.require_xpath, "external", b1.provide_xpath, b1.arity))
                    # We create merge information which will be used
                    # for unmerge operation.
                    # We store the port that is merged, the orginal require and the new require.
                    merge.append(("@"+b1.provide_xpath, get_lifecycle(b1.require_xpath), get_lifecycle(b.require_xpath)))
                    removed_bindings.append(b1)
            # We create a tuple (requirer, provider) of local
            # require. This will be used to update location of the
            # local require to be the same than the provider component.
            local.append((get_lifecycle(b.require_xpath), get_lifecycle(b.provide_xpath)))
    # Finally, we removed merged bindings
    for b in bindings:
        if b not in created_bindings:
            if b not in removed_bindings:
                created_bindings.append(b)

    return (created_bindings, merge, local)


def generate_files(initial, bindings, specialisation, multiplicity, workspace_name=None):
    """
    :param workspace_name: If None, a workspace is created based on component names.
    """

    logger.info("initial XPath: %s" % initial.xpath)
    components = create_components(initial, bindings)
    logger.info("List of Components created by Armonic:")
    for c in components:
        logger.info("\t%s on %s" % (c.name, c.lfm.lf_manager.os_type.name))

    if workspace_name is None:
        workspace_name = workspace.create_workspace([c.name for c in components])
        logger.debug("Workspace have been created: %s" % workspace_name)

    file_output_universe = workspace_name + "/" + common.FILE_UNIVERSE
    file_output_universe_merged = workspace_name + "/universe-merged.json"
    file_output_armonic_info = workspace_name + "/armonic-info.json"

    if not os.path.exists(workspace_name):
        logger.info("*** Creating directory '%s' for output files..." % workspace_name)
        os.makedirs(workspace_name)
    else:
        logger.info("*** Using directory '%s' for output files..." % workspace_name)

    fd_output_universe = open(file_output_universe, 'w')
    fd_output_universe_merged = open(file_output_universe_merged, 'w')
    fd_output_armonic_info = open(file_output_armonic_info, 'w')


    implementations = implementation_json(components)
    logger.info("List of bindings created by Armonic:")
    for b in bindings:
        logger.info("\t%s" % str(b))

    logger.info("Writing universe file %s... done." % file_output_universe)
    json.dump(
        {'version': 1,
         'component_types': [c.to_json() for c in components],
         'implementation': implementations,
         'repositories': repositories_json(implementations)},
        fd_output_universe, indent=2)

    bindings_merged, merge, local = merge_local_require(bindings)
    components = create_components(initial, bindings_merged)
    implementations = implementation_json(components)
    logger.info("Merged bindings:")
    for b in bindings_merged:
        logger.info("\t%s" % str(b))
    logger.info("specialisation:")
    for s in specialisation:
        logger.info("\t%s" % str(s))

    logger.info("Writing universe merged file %s... done." % file_output_universe_merged)
    json.dump(
        {'version': 1,
         'component_types': [c.to_json() for c in components],
         'implementation': implementations,
         'repositories': repositories_json(implementations)},
        fd_output_universe_merged, indent=2)

    logger.info("Writing Armonic info file %s... done." % file_output_armonic_info)
    json.dump({'merge': merge,
               'specialisation': specialisation,
               'initial': initial.xpath,
               'multiplicity': multiplicity,
               'local': local,
               'non_local': get_non_local_provide(initial, bindings),
               'cardinality': get_component_cardinality(bindings)
           },
              fd_output_armonic_info, indent=2)

    return workspace_name
