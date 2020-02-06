from tinkerforge import device_factory
from copy import deepcopy

INFO_NAMES = ["uid",
              "connected_uid",
              "position",
              "hardware_version",
              "firmware_version",
              "device_identifier",
              "enumeration_type",
              "_display_name"]


class BrickWrapper:

    def __init__(self, connection, client_id, info):
        self.client_id = client_id
        self.info = deepcopy(info)
        self.connection = connection
        brick_class = connection.device_classes[self.info["device_identifier"]]
        self.devices = {}
        self.brick = brick_class(info["uid"], self)

    def __getattr__(self, name):
        if name in INFO_NAMES:
            return self.info[name]
        else:
            if hasattr(self.brick, name):
                return getattr(self.brick, name)
            else:
                raise AttributeError("Not found %s" % name)


    def send_request(self, device, function_id, data, form, form_ret):
        self.connection.send_request(self.client_id, self.uid, device, function_id, data, form, form_ret)