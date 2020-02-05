import ishiki_client.shared.tinkerforge_mqtt as tf
from copy import deepcopy

INFO_NAMES = ["uid",
              "connected_uid",
              "position",
              "hardware_version",
              "firmware_version",
              "device_identifier",
              "enumeration_type",
              "_display_name"]


class BaseBrick:

    def __init__(self, client_id, info):
        self.client_id = client_id
        self.info = deepcopy(info)
        self.brick_class = tf.devices.get(self.info["device_identifier"])

    def __getattr__(self, name):
        if name in INFO_NAMES:
            return self.info[name]
        else:
            raise AttributeError("Not found %s" % name)
