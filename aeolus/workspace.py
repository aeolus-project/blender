import logging
import uuid
import os
import os.path

import json
import common

BASE_DIR = "workspaces/"

logger = logging.getLogger("aeolus." + __name__)


class WorkspaceException(Exception):
    pass


class Workspace(object):
    def __init__(self, name=None):
        if name is None:
            self.name = str(uuid.uuid4())
            self.path = BASE_DIR + self.name
            logger.info("Workspace %s has been created" % self.name)
            os.makedirs(self.path)
        else:
            self.name = name
            self.path = BASE_DIR + self.name

    @staticmethod
    def use(name):
        if name is None:
            raise WorkspaceException("Workspace name can not be None!")
        for wp in Workspace.all():
            if wp.name == name:
                return wp
        raise WorkspaceException("Workspace '%s' has not be found!" % name)

    @staticmethod
    def all():
        """Return all workspaces."""

        def is_workspace(path):
            """A directory is a workspace if it contains an Armonic info file"""
            return os.path.exists(path + "/" + common.FILE_ARMONIC_INFO)

        dirpath, dirnames, filenames = os.walk(BASE_DIR).next()
        return [Workspace(name=d) for d in dirnames if is_workspace(dirpath + d)]

    def infos(self):
        info = None

        initial = ""
        with open(self.path + "/" + common.FILE_ARMONIC_INFO) as f:
            info = json.load(f)
            initial = info['initial']

        components = []
        with open(self.path + "/" + common.FILE_UNIVERSE) as f:
            universe = json.load(f)
            for c in universe['component_types']:
                components.append(c['name'])

        return {'initial': initial, 'components': components}

    def _get_json_from_file(self, filename):
        path = os.path.join(self.path, filename)
        with open(path, 'r') as f:
            return json.load(f)

    def get_replay_filled(self):
        return self._get_json_from_file(common.FILE_ARMONIC_REPLAY_FILLED)

    def get_metis_plan(self):
        return self._get_json_from_file(common.FILE_METIS_PLAN_JSON)

    def get_filepath(self, filename):
        return os.path.join(self.path, filename)
