#!/usr/bin/python
import os
import json
import re
import pprint

import aeolus.common

from armonic.xmpp.client import XMPPCallSync, XMPPAgentApi, XMPPError
import logging
format = '%(levelname)-7s %(module)s %(message)s'
logging.basicConfig(level=logging.INFO, format=format)

logger = logging.getLogger()

logging.getLogger("sleekxmpp").setLevel(logging.INFO)

DEPLOYMENT_ID = "aeolus"

def transform_nodeid_to_cn(replay):
    """Transform nodeid to component name"""
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
    plan = []
    cmd = {}
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
            cmd = {'cmd':"state-goto", "jid":location, "xpath": remove_location(xpath)}

            xpath = xpath + "/enter"

        elif action['type'] == "binding":
            location = get_location(replay, action['component_target'])
            xpath = "%s/%s" % (
                action['component_target'],
                action['provide_target'])

            cmd = {'cmd':"provide-call", "jid":location, "xpath": remove_location(xpath)}
            logger.info(cmd)

        cmd['args'] = [get_variable(replay, xpath, "variables"), {'source' : 'metis', 'id': DEPLOYMENT_ID}]
        logger.debug("Variables of %s %s %s: %s" % (cmd['jid'], cmd['cmd'], cmd['xpath'], cmd['args']))
        cmd['args_host'] = get_variable(replay, xpath, "variables_host")

        plan.append(cmd)

    return plan


def run(plan, locations, provide_ret):
    for p in plan:
        try:
            logger.info("Managing the provide %s/%s" % (p['jid'], p['xpath']))
            client = XMPPAgentApi(master, p['jid']+"/agent", deployment_id=DEPLOYMENT_ID)
            ret = {}
            
            vars = get_variable_from_provide_ret(provide_ret, p['jid'] + '/' + p['xpath'])
            p['args'][0] += vars
            
            vars_host = p['args_host']
            if vars_host != []:
                logger.info("Translating JID to IP...")
            for v in vars_host:
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
            p['args'][0] += vars_host

            if p['cmd'] == "provide-call":
                logger.info("Provide call: %s %s" % (p['jid'], p['xpath']))
                logger.debug(json.dumps(p['args']))

                ret = client.provide_call(p['xpath'], p['args'])
                #if p['xpath'] == "Httpd/Configured/get_document_root":
                #    ret = {'url': "wordpress"}

                for d in provide_ret:
                    if p["jid"] + "/" + p['xpath'] == d['provided']:
                        for var, value in ret.items():
                            if var == d['variable_name']:
                                d['variable_value'] = value
                                logger.debug("The provide ret variable %s has been updated with value %s" % (d['requirer'], d['variable_value']))

            if p['cmd'] == "state-goto":
                logger.info("State goto  : %s/%s" % (p['jid'], p['xpath']))
                logger.debug(json.dumps(p['args']))
                ret = client.state_goto(p['xpath'], p['args'])

            print ret
        except (XMPPError, Exception):
            print "armocli", p['cmd'], '-J ', p['jid'] , p['xpath'], "'%s'" % json.dumps(p['args'])
            raise
