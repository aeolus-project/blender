#!/usr/bin/python

import logging
import configargparse as argparse
from uuid import uuid4
import json
import time

from sleekxmpp.thirdparty import OrderedDict
from sleekxmpp.exceptions import IqTimeout, IqError

import armonic.common
from armonic.serialize import Serialize
from armonic.client.smart import Provide, smart_call, SmartException, STEP_DEPLOYMENT_VALUES
from armonic.utils import OsTypeAll
import armonic.frontends.utils
from armonic.xmpp import XMPPCallSync

from pprint import pprint
import aeolus.builder
import aeolus.maker
import aeolus.utils
from aeolus.common import REQUIRE_CARDINALITY_PATTERN
import aeolus.workspace
import aeolus.launcher

aeolus.common.remove_default_handlers()
agent_handler = logging.StreamHandler()
format = '%(ip)-15s %(levelname)-19s %(module)s %(message)s'
agent_handler.setFormatter(armonic.frontends.utils.ColoredFormatter(format))
xmpp_client = None
logger = logging.getLogger()

AEOLUS_WORKSPACE = "xmpp_builder"
INPUT_CONFIGURATION = "data/configurations/many-locations-multiple-repos.json"

armonic.common.SIMULATION = True
armonic.common.DONT_VALIDATE_ON_CALL = True

class BuildProvide(Provide):

    def do_manage(self):
        self.manage = True
        return False

    def do_validation(self):
        return False

    def do_call(self):
        return False

    def do_post_specialize(self):
        return True

    def on_lfm(self, data):
        pass

    def do_lfm(self):
        self.lfm = armonic.serialize.Serialize(OsTypeAll())
        self.lfm_host = "all2"
        return False

    def do_multiplicity(self):
        return False

    def on_multiplicity(self, requires, data):
        if requires.skel.type == "external":
            requires.nargs = REQUIRE_CARDINALITY_PATTERN
            return [None]
        else:
            return 1

lfms = {}

class FillProvide(Provide):

    def on_lfm(self, host):
        self.lfm_host = host
        self.host = host
        if host not in lfms:
            logger.info("Creating a new lfm for host %s" % host)
            lfms[host] = Serialize(os_type=armonic.utils.OsTypeAll())
        self.lfm = lfms[host]

    def ignore_error_on_variable(self, variable):
        if variable.type in ['armonic_host', 'host', 'armonic_hosts'] or variable.belongs_provide_ret:
            return True
        return False

    def do_manage(self):
        self.manage = True
        return False

    def on_call(self, data):
        # We call it but in SIMULATION MODE!
        self.call = True
        return True

    def do_multiplicity(self):
        return False

    def do_post_specialize(self):
        return True

    def do_post_validation(self):
        return True


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
        self['xep_0050'].add_command(node='graph',
                                     name='Set the specification',
                                     handler=self._handle_command_graph)
        self['xep_0050'].add_command(node='workspaces',
                                     name='Get the list of workspaces',
                                     handler=self._handle_command_workspaces)
        self['xep_0050'].add_command(node='deployment',
                                     name='Launch a deployment',
                                     handler=self._handle_command_deployment)
        self['xep_0050'].add_command(node='fill',
                                     name='Fill the specification',
                                     handler=self._handle_command_fill)

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

    def _handle_command_deployment(self, iq, session):
        """ To launch a deployument, we first get a workspace ID. This workspace ID is then used to
        """
        logger.debug("Command deployment starts...")
        form = self['xep_0004'].makeForm('form', 'Specify a deployment id')
        form['instructions'] = 'specify'
        form.add_field(var="workspace")
        session['payload'] = form
        session['next'] = self._handle_command_deployment_start
        session['has_next'] = True
        return session

    def _handle_command_deployment_start(self, payload, session):
        logger.debug("Command deployment workspace...")

        form = self['xep_0004'].makeForm('form', 'Set specification')
        form['instructions'] = 'set specification'

        # Deployment mode are
        # normal
        # simulation
        mode = payload['values']['mode']
        workspace_name = payload['values']['workspace']
        workspace = aeolus.workspace.Workspace.use(workspace_name)
        session['workspace'] = workspace

        logger.debug("Starting command deploy with id: '%s'" % workspace.name)
        self.join_muc_room(workspace.name)

        plan = aeolus.launcher.Plan(
            workspace.get_replay_filled(),
            workspace.get_metis_plan(),
            workspace.get_configuration())

        if mode == "normal":
            actions = plan.run(self, workspace.name)
        elif mode == "simulation":
            actions = plan.actions

        for p in actions:
            msg = self.Message()
            msg['body'] = json.dumps(p.view())
            logger.debug("Sending: %s", msg['body'])
            self.send_muc_message(workspace.name, msg)
            if mode == "simulation":
                time.sleep(1)

        session['payload'] = form
        session['next'] = None
        session['has_next'] = False
        return session

    def _handle_command_workspaces(self, iq, session):
        form = self['xep_0004'].makeForm('form', 'List of workspaces')
        form['instructions'] = 'Choose amongst them'
        form.add_reported("name")
        form.add_reported("initial")
        form.add_reported("components")

        logger.debug("Getting the list of workspaces")
        for wp in aeolus.workspace.Workspace.all():
            logger.debug("\t%s" % wp.name)
            infos = wp.infos()
            form.add_item(OrderedDict({
                "name": wp.name,
                "initial": infos['initial'],
                "components": " ".join(infos['components'])
            }))

        session['payload'] = form
        session['next'] = None
        session['has_next'] = False

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

        session['next'] = self._handle_command_init_build_next
        session['has_next'] = True

        # If the root provide step is done, this is the last answer.
        if step == 'done' and provide == self.root_provide:
            session['next'] = None
            session['has_next'] = False

            workspace = aeolus.workspace.Workspace()
            aeolus.builder.generate_files(
                self.initial, self.bindings, self.specialisation,
                self.multiplicity, workspace.path)

            form.add_field(var="workspace",
                           ftype="fixed",
                           value=workspace.name)

        session['payload'] = form

        return session

    def _handle_command_specification(self, iq, session):
        logger.debug("Command %s specification starts..." % session['id'])
        form = self['xep_0004'].makeForm('form', 'Specify a deployment id')
        form['instructions'] = 'specify'
        form.add_field(var="workspace")
        session['payload'] = form
        session['next'] = self._handle_command_specification_components
        session['has_next'] = True
        return session

    def _handle_command_specification_components(self, payload, session):
        logger.debug("Command specification components...")

        form = self['xep_0004'].makeForm('form', 'Set specification')
        form['instructions'] = 'set specification'

        workspace_name = payload['values']['workspace']
        workspace = aeolus.workspace.Workspace.use(workspace_name)
        session['workspace'] = workspace
        logger.info("Directory %s is used to generate specification files" % workspace.path)

        fd_armonic_info = open(workspace.path + "/" + aeolus.common.FILE_ARMONIC_INFO, 'r')
        armonic_info = json.load(fd_armonic_info)

        x = armonic_info['initial']
        initial = {"component": aeolus.utils.get_lifecycle(x),
                   "state": aeolus.utils.get_state(x)}

        cardinality = []
        for c in armonic_info['cardinality']:
            p = lfm.provide(c)[0]
            label = p['extra'].get('label', p['name'])
            cardinality.append({'xpath': c, 'label': label})

        form.add_field(var="initial",
                       ftype="fixed",
                       value=str(json.dumps(initial)))
        form.add_field(var="components",
                       ftype="fixed",
                       value=str(json.dumps(armonic_info['non_local']) or ""))
        form.add_field(var="cardinality",
                       ftype="fixed",
                       value=str(json.dumps(cardinality) or ""))

        session['payload'] = form

        session['next'] = self._handle_command_specification_final
        session['has_next'] = True
        return session

    def _handle_command_specification_final(self, payload, session):
        workspace = session['workspace']
        logger.debug("Command specification final with workspace '%s'" % workspace.path)
        spec = payload['values']['specification']
        spec_file = workspace.path + "/" + aeolus.common.FILE_SPECIFICATION

        # Creating a initial configuration file
        initial_conf_filepath = workspace.get_filepath(aeolus.common.FILE_INITIAL_CONFIGURATION)
        logger.info("Writing initial configuration file %s..." % initial_conf_filepath)
        initial_conf = aeolus.utils.create_initial_configuration(
            workspace.get_universe_merged())
        f = open(initial_conf_filepath, 'w')
        f.write(json.dumps(initial_conf, indent=2))
        f.close()

        # Adding some clauses...
        logger.info("Adding force_repositories clauses to specification file to '%s'" % spec_file)
        spec = spec + "\n".join(aeolus.utils.force_repositories(initial_conf_filepath))

        # Generating specification file based on user criterion
        logger.info("Writing specification file to '%s'" % spec_file)
        f = open(spec_file, 'w')
        f.write(spec)

        # Upgrade universe file to take into account cardinality requested by user
        card = json.loads(payload['values']['cardinality'])
        print card
        logger.debug("Cardinalities specified by user are:")
        for c in card:
            logger.debug("\t%s" % c)
        f = workspace.path + "/" + aeolus.common.FILE_UNIVERSE
        logger.info("Apply cardinalities to '%s'" % f)
        aeolus.utils.apply_cardinality(f, card)
        f = workspace.path + "/" + aeolus.common.FILE_UNIVERSE_MERGED
        logger.info("Apply cardinalities to '%s'" % f)
        aeolus.utils.apply_cardinality(f, card)

        aeolus.maker.run(workspace.path,
                         initial_conf_filepath,
                         workspace.path + "/" + aeolus.common.FILE_SPECIFICATION)
        logger.info("Maker has generated all files")
        session['next'] = None
        session['has_next'] = False
        return session

    def _handle_command_graph(self, iq, session):
        logger.debug("Command graph starts...")
        form = self['xep_0004'].makeForm('form', 'Specify a deployment id')
        form['instructions'] = 'specify'
        form.add_field(var="workspace")
        session['payload'] = form
        session['next'] = self._handle_command_graph_final
        session['has_next'] = True
        return session

    def _handle_command_graph_final(self, payload, session):
        logger.debug("Command graph final...")

        form = self['xep_0004'].makeForm('form', 'Set specification')
        form['instructions'] = 'set specification'

        workspace_name = payload['values']['workspace']
        workspace = aeolus.workspace.Workspace.use(workspace_name)
        session['workspace'] = workspace
        logger.info("Directory %s is used to generate specification files" % workspace.path)

        config_file = workspace.path + "/" + aeolus.common.FILE_CONFIGURATION
        logger.info("Opening configuration file '%s'" % config_file)
        f = open(config_file, 'r')

        form.add_field(var="configuration",
                       ftype="fixed",
                       value=str(f.read()))

        session['payload'] = form
        session['next'] = None
        session['has_next'] = False
        return session

    def _handle_command_fill(self, iq, session):
        # for k, l in lfms.items():
        #     del(l)
        lfms.clear()

        self.session_id = str(uuid4())
        self.smart = None
        self.root_provide = None
        self.current_step = None

        self.bindings = []
        self.initial = None
        self.specialisation = []
        self.multiplicity = {}

        logger.debug("Command %s fill starts..." % session['id'])
        form = self['xep_0004'].makeForm('form', 'Specify a deployment id')
        form['instructions'] = 'specify'
        form.add_field(var="workspace")
        session['payload'] = form
        session['next'] = self._handle_command_fill_next
        session['has_next'] = True
        return session

    def _handle_command_fill_next(self, payload, session):
        if self.smart is None:
            logger.debug("Step: Create root_provide")
            xpath = payload['values']['xpath']

            workspace_name = payload['values']['workspace']
            workspace = aeolus.workspace.Workspace.use(workspace_name)
            session['workspace'] = workspace

            self.root_provide = FillProvide(xpath)
            input_file = workspace.get_filepath('replay.json')
            self.deployment_values_output_file = workspace.get_filepath('replay-filled.json')
            with open(input_file) as h:
                values = json.load(h)
            self.smart = smart_call(self.root_provide, values)

        if self.current_step == "validation":
            provide, step, args = self.smart.send(json.loads(payload['values']['validation']))

        elif self.current_step is not None and self.current_step.startswith(("post_", "pre_")):
            # just send something, we don't have any on_ methods anyway
            provide, step, args = self.smart.send(True)
        else:
            provide, step, args = self.smart.next()

        logger.warning("%s %s %s" % (provide, step, args))

        if isinstance(args, SmartException):
            self.report_exception(session['from'], args)
            self.smart.next()

        form = self['xep_0004'].makeForm('form', 'Fill specification')
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

        if step == 'validation':
            for variable in provide.variables():
                idx = variable.from_require.multiplicity_num
                value = json.dumps(variable.value_get_one())
                field = form.add_field(var=str(variable.xpath),
                                       label=str(variable.name),
                                       ftype="list-multi",
                                       options=[
                                           {"label": "value", "value": str(value)},
                                           {"label": "index", "value": str(idx)},
                                           {"label": "type", "value": str(variable.type)},
                                           {"label": "error", "value": str(getattr(variable, "error", ""))},
                                           {"label": "resolved_by", "value": str(getattr(variable._resolved_by, "xpath", ""))},
                                           {"label": "suggested_by", "value": str(getattr(variable._suggested_by, "xpath", ""))},
                                           {"label": "set_by", "value": str(getattr(variable._set_by, "xpath", ""))},
                                           {"label": "belongs_provide_ret", "value": str(variable.belongs_provide_ret)}],
                                       required=variable.required)
                for key, value in variable.extra.items():
                    field.add_option(label=str(key), value=str(value))

        session['payload'] = form
        session['next'] = self._handle_command_fill_next
        session['has_next'] = True

        # If the root provide step is done, this is the last answer.
        if step == 'done' and provide == self.root_provide:

            logger.info("Deployment tree has been created")
            provide, step, args = self.smart.next()
            if step is STEP_DEPLOYMENT_VALUES:
                with open(self.deployment_values_output_file, 'w') as fp:
                    json.dump(args, fp, indent=2)
                    logger.info("Deployment values written in %s" %
                                self.deployment_values_output_file)

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
