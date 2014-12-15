#!/usr/bin/python
import os
import json
import re
import pprint

import aeolus.provisionning
import aeolus.common
import utils

from armonic.xmpp.client import XMPPCallSync, XMPPAgentApi, XMPPError
import logging
logger = logging.getLogger("aeolus." + __name__)

logging.getLogger("sleekxmpp").setLevel(logging.INFO)

DEPLOYMENT_ID = "aeolus"


def transform_nodeid_to_cn(replay):
    """Transform nodeid to component name by modifiying the replay
    structure."""
    mappings = replay['mapping']

    def transform(section):
        for v in replay[section]:
            nodeid = get_location_from_xpath(v[0])
            cn = get_cn_from_mapping(mappings, nodeid)
            v[0] = cn + "/" + get_relative_xpath(v[0])

    transform("variables_host")
    transform("variables")
    transform("lfm")

    for v in replay["provide_ret"]:
        nodeid = get_location_from_xpath(v[0])
        cn = get_cn_from_mapping(mappings, nodeid)
        v[0] = cn + "/" + get_relative_xpath(v[0])

        nodeid = get_location_from_xpath(v[1])
        cn = get_cn_from_mapping(mappings, nodeid)
        v[1] = cn + "/" + get_relative_xpath(v[1])


def component_name_to_lifecycle(component_name):
    lifecycle = re.search('([\w_]*)', component_name).group(1)
    #lifecycle = lifecycle[0].upper() + lifecycle[1:]
    return lifecycle


def get_location_from_xpath(xpath):
    return xpath.split('/')[0]


def get_cn_from_mapping(mappings, nodeid):
    for m in mappings:
        if nodeid == m[1]:
            return m[0]
    raise Exception("%s not found in mapping!" % nodeid)


def get_variable(replay, xpath, section):
    def consumed(m):
        try:
            return m[2]
        except IndexError:
            m.append(True)
            logger.debug("Variable %s has been consumed" % m[0])
            return False

    acc = []
    variables = replay[section]
    for v in variables:
        if v[0].startswith(xpath):
            var = "/".join(v[0].split("/")[1:])
            if var not in [a[0] for a in acc] and not consumed(v):
                acc.append((var, v[1]))
    return acc


def get_jid_from_node_id(replay, node_id):
    for n, j in replay['lfm']:
        if n.startswith(node_id + "/"):
            return j


def remove_location(xpath):
    return "/".join(xpath.split("/")[1:])


def get_location(replay, cn):
    for item in replay['lfm']:
        if item[0].startswith(cn):
            return item[1]
    raise Exception("Location of %s not found in the replay file!" % cn)


def get_full_provide_from_full_xpath(xpath):
    return "/".join(xpath.split("/")[0:4])


def get_relative_xpath(xpath):
    return "/".join(xpath.split("/")[1:])


def get_provide_ret(replay):
    ret = []

    for var_to, var_from in replay['provide_ret']:
        node_id_to = get_location_from_xpath(var_to)
        node_id_from = get_location_from_xpath(var_from)

        jid_to = get_jid_from_node_id(replay, node_id_to)
        jid_from = get_jid_from_node_id(replay, node_id_from)

        xpath_to = jid_to + "/" + remove_location(var_to)
        
        provide_from = jid_from + "/" + remove_location(get_full_provide_from_full_xpath(var_from))
        variable_name = var_from.split("/")[-1]

        ret.append({"requirer": xpath_to, "provided": provide_from, "variable_name": variable_name})

    return ret


def get_all_locations(replay):
    dct = {}
    for l in replay['lfm']:
        dct[l[1]] = None
    return dct


def get_variable_from_provide_ret(provide_ret, xpath):
    acc = []
    for d in provide_ret:
        if d['requirer'].startswith(xpath):
            if "variable_value" in d:
                logger.info("Upgrade variables list with provide ret variable %s=%s" % (d['requirer'], d['variable_value']))
                acc.append((get_relative_xpath(d['requirer']), {0: d['variable_value']}))
            else:
                logger.info("The value of variable %s has not been upgraded by provide ret." % (d['requirer']))
    return acc


# ([
#     ("//xpath/to/variable", {0: value}),
#     ("//xpath/to/variable", {0: value})
#  ], {'source' : xpath, 'id': uuid})
def metis_to_armonic(metis_plan, replay):
    """The plan from metis is completed with variables that comes from
    the replay file.

    This returns a list of armonic commands where each command is a
    dict which contains keys
    cmd: state-goto or provide-call
    jid: the agent location
    xpath: the provide or state xpath
    args: the variables
    args_host: variables that contain host value (need to be translated jid -> ip)
    """
    aeolus.launcher.transform_nodeid_to_cn(replay)

    plan = []
    for action in metis_plan:
        cn = action['component_name']
        location = get_location(replay, cn)
        lifecycle = component_name_to_lifecycle(cn)
        if action['type'] in ["create", "change"]:
            if action['type'] == "create":
                state = action['state']
            else:
                state = action['state_to']

            xpath ="%s/%s/%s" % (
                cn,
                lifecycle,
                state)
            cmd = StateGoto(jid=location, xpath=remove_location(xpath))
            xpath = xpath + "/enter"

        elif action['type'] == "binding":
            location = get_location(replay, action['component_target'])
            xpath = "%s/%s" % (
                action['component_target'],
                action['provide_target'])

            cmd = ProvideCall(jid=location, xpath=remove_location(xpath), component_name_target=action['component_target'])
            logger.info(cmd)

        cmd.component_name = cn
        cmd.args = get_variable(replay, xpath, "variables")
        logger.debug(cmd)
        cmd.args_host = get_variable(replay, xpath, "variables_host")

        plan.append(cmd)

    # We manually add the provide called by the user since it is not
    # managed by Metis
    xpath = ""
    for s in replay['specialize']:
        if s[0] == "node_0///*":
            xpath = remove_location(s[1])
    for l in replay['lfm']:
        if l[0] == "node_0///*":
            location = s[1]
    cmd = ProvideCall(jid=location,
                      xpath=xpath,
                      component_name_target=get_cn_from_mapping(replay['mapping'], "node_0"))
    cmd.component_name = "User"
    cmd.args = get_variable(replay, xpath, "variables")
    cmd.args_host = get_variable(replay, xpath, "variables_host")

    plan.append(cmd)

    return plan


def visualisation_plan(workspace_path):
    file_replay = workspace_path + "/" + aeolus.common.FILE_ARMONIC_REPLAY_FILLED
    file_metis_plan = workspace_path + "/" +  aeolus.common.FILE_METIS_PLAN_JSON

    with open(file_replay, 'r') as f:
        replay = json.load(f)
    with open(file_metis_plan, 'r') as f:
        metis_plan = json.load(f)

    plan = aeolus.launcher.metis_to_armonic(metis_plan, replay)

    def is_final_state(jid, cpt, plan):
        # Used to know if a component state change is the last one or not.
        for p in plan:
            if p.type == 'state-goto' and p.jid == jid and utils.get_lifecycle(p.xpath) == cpt:
                return False
        return True

    ret = []

    for idx, action in enumerate(plan):
        if type(action) == StateGoto:
            action.location = action.jid
            action.component_type = utils.get_lifecycle(action.xpath)
            action.state = utils.get_state(action.xpath)
            action.final = is_final_state(action.location, action.component_type, plan[idx+1:])
            action.last_one = (idx == len(plan) - 1)

        else:
            pass

    plan.insert(0, Start(len(plan)))
    plan.append(End())

    return plan


class Plan(object):
    def __init__(self, replay, metis_plan, configuration):
        self.actions = metis_to_armonic(metis_plan, replay)
        self.provide_ret = aeolus.launcher.get_provide_ret(replay)
        self.locations = get_all_locations(replay)
        self.nova_locations = self._get_nova_locations(configuration)

        self.actions = self.nova_locations + self.actions
        self.create_visualisation_attributes()

    def update_provide_ret_values(self, current_action, provide_ret_values):
        for d in self.provide_ret:
            if current_action.jid + "/" + current_action.xpath == d['provided']:
                for var, value in provide_ret_values.items():
                    if var == d['variable_name']:
                        d['variable_value'] = value
                        logger.debug("The provide ret variable %s has been updated with value %s" % (d['requirer'], d['variable_value']))

    def _get_nova_locations(self, configuration):
        machines = []
        for location in self.locations:
            for l in configuration['locations']:
                if l['name'] == location:
                    r = l['repository']
                    image = aeolus.common.repositories_to_openstack[r]
                    server_name = re.search("(.*)@.*", location).group(1)
                    machines.append(NovaBoot(name=server_name, image=image, jid=location))

        wait = []
        for location in self.locations:
            wait.append(WaitAgent(location))
        return machines + wait

    def run(self, master, room_id="aeolus"):
        hack = False

        for p in self.actions:
            # This is a hack. See commit message.
            if issubclass(type(p), ActionArmonic) and hack is False:
                # Get IPs of locations
                self.get_locations(master)
                hack = True

            yield p

            if issubclass(type(p), WaitAgent):
                p.apply(master)
                continue

            if issubclass(type(p), NovaBoot):
                p.apply()
                continue

            if not issubclass(type(p), ActionArmonic):
                continue

            try:
                logger.debug("Managing action %s" % p)
                client = XMPPAgentApi(master, p.jid+"/agent", deployment_id=room_id)

                # Get variable from provide ret
                p.args_from_provide_ret = get_variable_from_provide_ret(self.provide_ret, p.jid + '/' + p.xpath)
                p.translate_args_host(self.locations)

                provide_ret_values = p.apply(client)

                # Send provide_ret value to the room
                if provide_ret_values not in [{}, None] and p.type == "provide-call":
                    msg = master.Message()
                    msg['body'] = json.dumps(ProvideRet(p.component_name_target, provide_ret_values).view())
                    master.send_muc_message(room_id, msg)
                self.update_provide_ret_values(p, provide_ret_values)

            except (XMPPError, Exception):
                print "armocli", p.type, '-J ', p.jid, p.xpath, "'%s'" % json.dumps(p.armonic_args())
                raise

    def get_locations(self, master):
        logger.info("Retrieving public IP from JID...")
        for k in self.locations:
            self.locations[k] =  XMPPAgentApi(master, k+"/agent", deployment_id=DEPLOYMENT_ID).info()['public-ip']
            logger.info("\t%s: %s" % (k, self.locations[k]))

    def create_visualisation_attributes(self):
        def is_final_state(jid, cpt, actions):
            # Used to know if a component state change is the last one or not.
            for p in actions:
                if p.type == 'state-goto' and p.jid == jid and utils.get_lifecycle(p.xpath) == cpt:
                    return False
            return True

        for idx, action in enumerate(self.actions):
            if type(action) == StateGoto:
                action.location = action.jid
                action.component_type = utils.get_lifecycle(action.xpath)
                action.state = utils.get_state(action.xpath)
                action.final = is_final_state(action.location, action.component_type, self.actions[idx+1:])
                action.last_one = (idx == len(self.actions) - 1)
            else:
                pass

        # Add header and footer used to inform interface deployment has started and is ended
        self.actions.insert(0, Start(len(self.actions)))
        self.actions.append(End())


class Action(object):
    type = "undefined"

    def view(self):
        return {"action": self.type}

    def armonic_command(self, jid=None, password=None):
        return ""

    def apply(self):
        return


class NovaBoot(Action):
    type = "nova-boot"

    def __init__(self, jid, name, image):
        self.jid = jid
        self.name = name
        self.image = image

    def view(self):
        return {"action": self.type, 'image': self.image, 'name': self.name, 'jid': self.jid}

    def apply(self):
        return aeolus.provisionning.boot(self.name, self.image)


class WaitAgent(Action):
    type = "wait-agent"

    def __init__(self, jid):
        self.jid = jid

    def view(self):
        return {"action": self.type, 'jid': self.jid}

    def apply(self, client):
        logger.debug("Waiting for agent %s..." % self.jid)
        return client.wait_available(self.jid)


class Start(Action):
    type = "begin"
    def __init__(self, length=None):
        self.length = length

    def view(self):
        return {"action": self.type, "length": self.length}


class End(Action):
    type = "end"


class ProvideRet(Action):
    type = "provide_ret"

    def __init__(self, component_name, value):
        self.component_name = component_name
        self.value = value

    def view(self):
        return {"action": self.type, "component_name": self.component_name, "value": self.value}


class ActionArmonic(Action):
    args_host_translated = False
    args_from_provide_ret = []

    def translate_args_host(self, locations):
        """Translate JID to IP by using a locations dict. The value of the
        variable is upgraded with the IP associated to the JID
        location key.
        """
        if self.args_host_translated:
            logger.warning("args_host variables have been already translated!")
            return
        if self.args_host != []:
            logger.info("Translating JID to IP...")
        for v in self.args_host:
            logger.info("\t%s %s..." % (v[0], id(v)))
            for k in v[1]:
                try:
                    if type(v[1][k]) == list:
                        acc = []
                        for e in v[1][k]:
                            acc.append(locations[e])
                        v[1][k] = acc
                    else:
                        v[1][k] = locations[v[1][k]]
                    logger.info("%s : %s" % (v[0], v[1][k]))
                except KeyError:
                    logger.info("%s host is already transformed to IP" % v[1])
        self.args_host_translated = True

    def all_vars(self):
        return self.args + self.args_host + self.args_from_provide_ret

    def armonic_args(self):
        """This generate full armonic args, ie. with source and id"""
        return [self.all_vars(), {'source': 'metis', 'id': DEPLOYMENT_ID}]

    def armonic_command(self, jid=None, password=None):
        return "armocli -j %s -p %s  %s -J %s %s --json %s " % (jid, password, self.method, self.jid, self.xpath, json.dumps(self.armonic_args()))

    def apply(self, client):
        """Execute the armonic comand by using the client as a XMPP client"""
        logger.info(self.armonic_command())
        return getattr(client, self.method)(self.xpath, self.armonic_args())


class StateGoto(ActionArmonic):
    type = "state-goto"
    method = "state_goto"

    def __init__(self, jid=None, xpath=None, component_name=None):
        self.jid = jid
        self.xpath = xpath
        self.component_name = component_name

        self.location = None
        self.component_type = None
        self.state = None
        self.final = None
        self.last_one = None

    def view(self):
        return {"component_name": self.component_name,
                "location": self.location,
                "component_type": self.component_type,
                "state": self.state,
                "final": self.final,
                "action": self.type,
                "last_one": self.last_one}


class ProvideCall(ActionArmonic):
    type = "provide-call"
    method = "provide_call"

    def __init__(self, jid=None, xpath=None, component_name=None, component_name_target=None):
        self.jid = jid
        self.xpath = xpath
        self.component_name = component_name
        self.component_name_target = component_name_target

    def view(self):
        return {"component_name": self.component_name,
                "component_name_target": self.component_name_target,
                "port": self.xpath,
                "action": self.type}
