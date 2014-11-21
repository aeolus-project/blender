import uuid
import os

BASE_DIR = "workspaces/"


class Workspace(object):
    def __init__(self, name=None):
        if name is None:
            self.name = str(uuid.uuid4())
            self.path = BASE_DIR + self.name
            os.makedirs(self.path)
        else:
            self.name = name
            self.path = BASE_DIR + self.name

    @staticmethod
    def list():
        dirpath, dirnames, filenames = os.walk(BASE_DIR).next()
        return dirnames
