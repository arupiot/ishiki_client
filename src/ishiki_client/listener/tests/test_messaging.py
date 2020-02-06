import unittest

from tinkerforge import device_factory

from ishiki_client.listener.mqtt_connection import MqttConnection
from ishiki_client.listener.bricks.brick_wrapper import BrickWrapper


class TestMessages(unittest.TestCase):

    def setUp(self):

        self.connection = MqttConnection("ishiki", "username", "password", "cert", True)

    def test_write_function_call(self):

        client_id = "orca.st:hardware_123456789"
        info = {
            "uid": "CxW",
            "connected_uid": "6yMtxW",
            "position": "c",
            "hardware_version": [
                1,
                1,
                0
            ],
            "firmware_version": [
                2,
                0,
                2
            ],
            "device_identifier": "rgb_led_button_bricklet",
            "enumeration_type": "available",
            "_display_name": "RGB LED Button Bricklet"
        }

        wrapper = BrickWrapper(self.connection, client_id, info)
        wrapper.set_color(255, 127, 0)
        expected_topic = "ishiki/orca.st:hardware_123456789/request/rgb_led_button_bricklet/CxW/set_color"
        expected_message = '{"red": 255, "green": 127, "blue": 0}'

        self.assertEqual(expected_topic, self.connection.last_topic)
        self.assertEqual(expected_message, self.connection.last_message)