import os
from io import BytesIO
import time
import requests

from ishiki_client.shared.tinkerforge_controller import TinkerforgeController
from tinkerforge.bricklet_air_quality import BrickletAirQuality
from tinkerforge.bricklet_sound_pressure_level import BrickletSoundPressureLevel
from tinkerforge.bricklet_motion_detector_v2 import BrickletMotionDetectorV2

from tinkerforge.ip_connection import IPConnection

class InitController(TinkerforgeController):

    def __init__(self, host, port, prefix):
        self.prefix = prefix
        self.pre_connect = {}
        super().__init__(host, port)


    def get_init_json(self):
        self.stop()
        return {
            "pre_connect": self.pre_connect,
            "post_connect": {}
        }

    def cb_enumerate(self,
                     uid,
                     connected_uid,
                     position,
                     hardware_version,
                     firmware_version,
                     device_identifier,
                     enumeration_type):

        if device_identifier == BrickletAirQuality.DEVICE_IDENTIFIER:
            name = "%sregister/air_quality_bricklet/%s/all_values" % (self.prefix, uid)
            self.pre_connect[name] = { "register": true }
            name = "%srequest/air_quality_bricklet/%s/set_all_values_callback_configuration" % (self.prefix, uid)
            self.pre_connect[name] = {"period": 10000, "value_has_to_change": True}
        if device_identifier == BrickletSoundPressureLevel.DEVICE_IDENTIFIER:
            name = "%sregister/sound_pressure_level_bricklet/%s/decibel" % (self.prefix, uid)
            self.pre_connect[name] = { "register": true }
            name = "%srequest/sound_pressure_level_bricklet/%s/set_decibel_callback_configuration" % (self.prefix, uid)
            self.pre_connect[name] = {"period": 10000, "value_has_to_change": True}
        if device_identifier == BrickletMotionDetectorV2.DEVICE_IDENTIFIER:
            name = "%sregister/motion_detector_v2_bricklet/%s/motion_detected" % (self.prefix, uid)
            self.pre_connect[name] = { "register": true }
            name = "%srequest/motion_detector_v2_bricklet/%s/set_sensitivity" % (self.prefix, uid)
            self.pre_connect[name] = {"sensitivity": 50}
