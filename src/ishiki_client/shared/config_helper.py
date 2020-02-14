import os


class ConfigHelper:

    def __init__(self, local_config):

        self.local_config = local_config

    def _lookup_var(self, name, default=None):
        if self.local_config is not None:
            return os.environ.get(name, getattr(self.local_config, name, default))
        else:
            return os.environ.get(name, default)

    def string(self, name, default=None):
        return self._lookup_var(name, default=default)

    ## always defaults to false
    def bool(self, name):
        var = self._lookup_var(name)
        if var == "false":
            return False
        return bool(var)

    def int(self, name, default=None):
        var = self._lookup_var(name, default=default)
        if var is not None:
            return int(var)
        return var

