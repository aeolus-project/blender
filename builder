#!/usr/bin/python

import argparse
from armonic.client.smart import Provide, smart_call
from armonic.utils import OsTypeAll
import armonic.common

import logging

import aeolus.builder
import aeolus.utils
import aeolus.common

import json

logger = logging.getLogger("aeolus." + __name__)

logging.getLogger("armonic").setLevel(logging.WARNING)


def user_input_choose_amongst(choices, prefix=''):
    """Ask the user if he confirm the msg question.

    :rtype: True if user confirm, False if not"""
    while True:
        for i, c in enumerate(choices) :
            print "  %s%d) %s" % (prefix, i, c)
        answer = raw_input("%sChoice [0-%d]: " % (prefix, len(choices)-1))
        try:
            return choices[int(answer)]
        except Exception as e:
            print e
            print "%sInvalid choice. Do it again!" % (prefix)



parser = argparse.ArgumentParser(prog='armonic-aeolus')
parser.add_argument('--os-type', choices=['mbs', 'debian', 'arch', 'any'], default=None, help="Manually specify an OsType. This is just used when no-remote is also set. If not set, the current OsType is used.")
parser.add_argument('--lifecycle-dir', '-l', type=str, action='append',
                    help="A lifecycle directory")
parser.add_argument('--lifecycle-repo', '-L', type=str, action='append',
                    help="A lifecycle repository")


parser.add_argument('--xpath', '-x', dest='xpath', type=str, default="//*",
                    help='A provide Xpath. If not specified, "//*" is used.')

parser.add_argument('-w', '--workspace', type=str, required=True)

parser.add_argument('--verbose', '-v', action='store_true', help="Verbose")

args = parser.parse_args()

if args.verbose:
    logger.setLevel(logging.DEBUG)

directory_output = args.workspace

import armonic.serialize
import armonic.common
armonic.common.load_default_lifecycles()
if args.lifecycle_dir is not None:
    for l in args.lifecycle_dir:
        armonic.common.load_lifecycle(l)

if args.lifecycle_repo is not None:
    for l in args.lifecycle_repo:
        armonic.common.load_lifecycle_repository(l)


class MyProvide(Provide):
    def on_manage(self, data):
        self.manage = True

    def do_validation(self):
        return False

    def do_lfm(self):
        self.lfm = armonic.serialize.Serialize(OsTypeAll())
        self.lfm_host = "all"
        return False

    def on_lfm(self, data):
        pass

def call(provide):
    bindings = []
    initial = None
    specialisation = []
    multiplicity = {}

    generator = smart_call(provide)
    data = None
    while True:
        try:
            provide, step, args = generator.send(data)
            if isinstance(args, Exception):
                raise args
            data = None
        except StopIteration:
            break

        if step == "multiplicity":
            require = args
            while True:
                answer = raw_input("How many time to call %s? " % require.skel.provide_xpath)
                try:
                    answer = int(answer)
                    break
                except Exception as e:
                    print e
                    print provide.depth, "Invalid choice. Do it again!"
            require.nargs = answer
            if require.skel.type == 'external':
                data = [None]
            else:
                data = 1

        if step == "done":
            if not provide.has_requirer():
                initial = provide
            # We get the name of the lifecycle which will be used as component name
            p = provide.lfm.uri("//" + provide.xpath, relative=True, resource="provide")
            for r in provide.remotes:
                nargs = 1
                try:
                    nargs = r.nargs
                except AttributeError:
                    pass
                binding = aeolus.builder.Binding(
                    aeolus.utils.get_provide_xpath(r[0].xpath),
                    r[0].provide.require.type,
                    r[0].provide.xpath,
                    nargs)
                bindings.append(binding)
                logger.info("Append binding:")
                logger.info(binding)
                
            specialisation.append((provide.generic_xpath, provide.xpath))

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
                multiplicity[xpath] = None
                for r in requires:
                    multiplicity[xpath] = r.provide.xpath

        if step == "specialize":
            print "Please specialize xpath %s" % provide.generic_xpath
            data = user_input_choose_amongst([a['xpath'] for a in args])

    return (initial, bindings, specialisation, multiplicity)


provide = MyProvide(args.xpath)
Initial, Bindings, Specialisation, Multiplicity = call(provide)

aeolus.builder.generate_files(Initial, Bindings, Specialisation, Multiplicity, directory_output)

