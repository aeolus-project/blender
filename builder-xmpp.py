#!/usr/bin/python

import logging
import configargparse as argparse
from uuid import uuid4
import json

from sleekxmpp.thirdparty import OrderedDict
from sleekxmpp.exceptions import IqTimeout, IqError

import armonic.common
from armonic.serialize import Serialize
from armonic.client.smart import Provide, smart_call, SmartException
from armonic.utils import OsTypeAll
import armonic.frontends.utils
from armonic.xmpp import XMPPAgentApi, XMPPCallSync

from pprint import pprint
import aeolus.builder
import aeolus.utils

agent_handler = logging.StreamHandler()
format = '%(ip)-15s %(levelname)-19s %(module)s %(message)s'
agent_handler.setFormatter(armonic.frontends.utils.ColoredFormatter(format))
xmpp_client = None
logger = logging.getLogger()

AEOLUS_WORKSPACE = "xmpp_builder"

class BuildProvide(Provide):

    def do_manage(self):
        self.manage = True
        return False

    def do_validation(self):
        return False

    def do_call(self):
        return False

    def on_lfm(self, data):
        pass

    def do_lfm(self):
        self.lfm = armonic.serialize.Serialize(OsTypeAll())
        self.lfm_host = "all2"
        return False

    def do_multiplicity(self):
        return False

    def on_multiplicity(self, require, data):
        if require.type == "external":
            require.nargs = 42
            return [None]
        else:
            return 1

class XMPPMaster(XMPPCallSync):

    def __init__(self, jid, password, plugins=[], muc_domain=None, lfm=None):
        XMPPCallSync.__init__(self, jid, password, plugins, muc_domain)
        # fixed resource name for xmpp master
        self.requested_jid.resource = "master"
        self.lfm = lfm
        self.smart = None

    def session_start(self, event):
        XMPPCallSync.session_start(self, event)

        self['xep_0050'].add_command(node='provides',
                                     name='Get the list of provides',
                                     handler=self._handle_command_provides)
        self['xep_0050'].add_command(node='build',
                                     name='Build a provide',
                                     handler=self._handle_command_build)
        self['xep_0050'].add_command(node='specification',
                                     name='Set the specification',
                                     handler=self._handle_command_specification)

    def handle_armonic_exception(self, exception):
        # Forward exception to client
        logger.error("%s: %s" % (exception['code'],
                                 exception['message']))
        iq = self.Iq()
        iq.error()
        iq['to'] = self['xep_0050'].sessions[exception['deployment_id']]['from']
        iq['exception']['code'] = exception['code']
        iq['exception']['message'] = exception['message']
        try:
            iq.send(block=False)
        except (IqTimeout, IqError):
            pass


    def _handle_command_provides(self, iq, session):
        form = self['xep_0004'].makeForm('form', 'List of provides')
        form['instructions'] = 'Choose a xpath amongst them'
        form.add_reported("xpath")
        form.add_reported("tag")
        form.add_reported("label")
        form.add_reported("help")

        for provide in self.lfm.provide("//*"):
            tags = ""
            if provide['extra'].get('tags'):
                tags = ",".join(provide['extra']['tags'])

            form.add_item(OrderedDict({
                "xpath": provide['xpath'],
                "tag": tags,
                "label": provide['extra'].get('label', provide['name']),
                "help": provide['extra'].get('help', '')
            }))

        session['payload'] = form
        session['next'] = None  # self._handle_command_init_walk
        session['has_next'] = False
        session['id'] = str(uuid4())

        return session

    def _handle_command_build(self, iq, session):
        self.session_id = str(uuid4())
        self.smart = None
        self.root_provide = None
        self.current_step = None

        self.bindings = []
        self.initial = None
        self.specialisation = []
        self.multiplicity = {}

        form = self['xep_0004'].makeForm('form', 'Specify a provide to build')
        form['instructions'] = 'specify'
        form.add_field(var="xpath")
        session['payload'] = form
        session['next'] = self._handle_command_init_build_next
        session['has_next'] = True
        session['id'] = self.session_id

        return session

    def _handle_command_init_build_next(self, payload, session):
        if self.smart is None:
            logger.debug("Step: Create root_provide")
            xpath = payload['values']['xpath']
            self.root_provide = BuildProvide(xpath)
            self.smart = smart_call(self.root_provide)

        if self.current_step == "specialize":
            provide, step, args = self.smart.send(payload['values']['xpath'])

        elif self.current_step == "multiplicity":
            provide, step, args = self.smart.send(payload['values']['multiplicity'].split(','))

        elif self.current_step == "call":
            provide, step, args = self.smart.send(payload['values']['call'])

        else:
            provide, step, args = self.smart.next()

        if isinstance(args, SmartException):
            self.report_exception(session['from'], args)
            self.smart.next()

        form = self['xep_0004'].makeForm('form', 'Build a provide')
        self.current_step = step

        logger.debug("Current step is now %s" % step)

        form['instructions'] = step
        form.add_field(var="provide",
                       ftype="fixed",
                       value=provide.xpath or provide.generic_xpath,
                       label=provide.extra.get('label', provide.name))

        form.add_field(var="tree_id",
                       ftype="fixed",
                       value=str(json.dumps(provide.tree_id)))

        form.add_field(var="host",
                       ftype="fixed",
                       value=str(json.dumps(provide.lfm_host) or ""))

        if step == 'specialize':
            field = form.add_field(var="specialize",
                                   ftype="list-single",
                                   label="Choose")
            for provide_match in provide.matches():
                field.add_option(label=str(provide_match['extra'].get('label', provide_match['name'])),
                                 value=str(provide_match['xpath']))

        # If the root provide step is done, this is the last answer.
        if step == 'done':
            if not provide.has_requirer():
                self.initial = provide
            # We get the name of the lifecycle which will be used as component name
            print provide
            print provide.lfm
            p = provide.lfm.uri("//" + provide.xpath, relative=True, resource="provide")
            for r in provide.remotes:
                nargs = 1
                try:
                    nargs = r.nargs
                except AttributeError:
                    pass
                self.bindings.append(aeolus.builder.Binding(
                    aeolus.utils.get_provide_xpath(r[0].xpath),
                    r[0].provide.require.type,
                    r[0].provide.xpath,
                    nargs))
            self.specialisation.append((provide.generic_xpath, provide.xpath))

            # To Create a section multiplicity.
            #
            # For each provide, and for each remote require of this
            # provide, we get its xpath and the xpath of required
            # provide.
            # 
            # The multiplicicty section is a dict where keys are the
            # xpath of a require.
            # At each key is associated the xpath of the required provide.
            for requires in provide.remotes:
                xpath = requires.skel.xpath
                self.multiplicity[xpath] = None
                for r in requires:
                    self.multiplicity[xpath] = r.provide.xpath

            if provide == self.root_provide:
                self.initial = provide
                session['next'] = None
                session['has_next'] = False
                print "\n\n"
                pprint("Initial")
                pprint(self.initial)
                pprint("Bindings:")
                pprint(self.bindings)
                pprint("Multiplicity:")
                pprint(self.multiplicity)
                pprint("Specialisation:")
                pprint(self.specialisation)


        session['payload'] = form
        session['next'] = self._handle_command_init_build_next
        session['has_next'] = True

        # If the root provide step is done, this is the last answer.
        if step == 'done' and provide == self.root_provide:
            session['next'] = None
            session['has_next'] = False

            aeolus.builder.generate_files(
                self.initial, self.bindings, self.specialisation,
                self.multiplicity, AEOLUS_WORKSPACE)

        return session

    def _handle_command_specification(self, iq, session):
        logger.debug("Command specification starts...")
        form = self['xep_0004'].makeForm('form', 'Specify a deployment id')
        form['instructions'] = 'specify'
        form.add_field(var="deployment_id")
        session['payload'] = form
        session['next'] = self._handle_command_specification_components
        session['has_next'] = True
        return session

    def _handle_command_specification_components(self, payload, session):
        logger.debug("Command specification components...")

        form = self['xep_0004'].makeForm('form', 'Set specification')
        form['instructions'] = 'set specification'
        deployment_id = payload['values']['deployment_id']
        logger.info("Directory %s is used to generate specification files" % deployment_id)

        fd_armonic_info = open(AEOLUS_WORKSPACE + "/" + aeolus.common.FILE_ARMONIC_INFO, 'r')
        armonic_info = json.load(fd_armonic_info)
        form.add_field(var="json",
                       ftype="fixed",
                       value=str(json.dumps(armonic_info['non_local']) or ""))

        session['payload'] = form

        session['next'] = self._handle_command_specification_final
        session['has_next'] = True
        return session

    def _handle_command_specification_final(self, payload, session):
        logger.debug("Command specification final...")
        session['next'] = None
        session['has_next'] = False
        return session

if __name__ == '__main__':
    parser = argparse.ArgumentParser(default_config_files=armonic.common.MASTER_CONF)

    cli_base = armonic.frontends.utils.CliBase(parser)
    cli_local = armonic.frontends.utils.CliLocal(parser, disable_options=["--os-type", "--simulation"])
    cli_xmpp = armonic.frontends.utils.CliXMPP(parser)
    args = cli_base.parse_args()
    args = cli_local.parse_args()
    args = cli_xmpp.parse_args()

    lfm = Serialize(os_type=OsTypeAll())
    logging.getLogger('armonic').setLevel(cli_base.logging_level)

    # Use /master resource by default
    xmpp_client = XMPPMaster(args.jid,
                             cli_xmpp.password,
                             plugins=[('xep_0050',)],
                             muc_domain=cli_xmpp.muc_domain,
                             lfm=lfm)
    if not args.host:
        xmpp_client.connect()
    else:
        xmpp_client.connect(address=(args.host, args.port))
    try:
        xmpp_client.process(block=True)
    except KeyboardInterrupt:
        logger.info("Disconnecting...")
        pass
