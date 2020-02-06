import json
from collections import namedtuple, OrderedDict
import paho.mqtt.client as mqtt
from tinkerforge import device_factory
from ishiki_client.shared.tinkerforge_mqtt import mqtt_names, devices, FunctionInfo, HighLevelFunctionInfo

from ishiki_client.listener.bricks.brick_wrapper import BrickWrapper

IP_CONNECTION = "ip_connection"
OPERATION_CALLBACK = "callback"
FUNCTION_ENUMERATE = "enumerate"

ReverseFunctionInfo = namedtuple('ReverseFunctionInfo', ['name',  'arg_names', 'arg_types', 'arg_symbols', 'format_in', 'result_names', 'result_symbols', 'format_out'])

# oo wrapper for callbacks using curried callable
class ConnectCallback:

    def __init__(self, connection):
        self.connection = connection

    def __call__(self, *args, **kwargs):
        self.connection.on_connect(*args, **kwargs)

class MessageCallback:

    def __init__(self, connection):
        self.connection = connection

    def __call__(self, *args, **kwargs):
        self.connection.on_message(*args, **kwargs)


class MqttConnection:

    def __init__(self, prefix, username, password, tls_certificate, tls_insecure):

        self.username = username
        self.password = password
        self.prefix = prefix
        self.tls_certificate = tls_certificate
        self.tls_insecure = tls_insecure
        self.devices = {}
        self.last_topic = None
        self.last_message = None

        # this ugly thing gives a <string_identifer>:<tinkerforge class> lookup
        self.device_classes = {value:device_factory.DEVICE_CLASSES[key] for (key,value) in mqtt_names.items()}
        # and this one gives  <device_id><function_id>:<reverse function info>
        self.mqtt_function_info = {key:self.reverse_function_lookup(devices[value]) for (key, value) in mqtt_names.items()}


    def reverse_function_lookup(self, callback_class):

        return {self.find_info_id(info): self.make_reverse_info(name, info) for (name, info) in callback_class.functions.items()}


    def find_info_id(self, info):

        if isinstance(info, FunctionInfo):
            return info.id
        elif isinstance(info, HighLevelFunctionInfo):
            return info.low_level_id
        else:
            return None


    def make_reverse_info(self, name, info):

        if isinstance(info, FunctionInfo):
            return ReverseFunctionInfo(name,
                                info.arg_names,
                                info.arg_types,
                                info.arg_symbols,
                                info.payload_fmt,
                                info.result_names,
                                info.result_symbols,
                                info.response_fmt)
        elif isinstance(info, HighLevelFunctionInfo):
            return ReverseFunctionInfo(name,
                                info.arg_names,
                                info.arg_types,
                                info.arg_symbols,
                                info.format_in,
                                info.result_names,
                                info.result_symbols,
                                info.format_out)
        else:
            return None



    def send_request(self, client_id, uid, device, function_id, data, form, form_ret):
        self.last_topic, self.last_message = self.topic_and_message_for_request(client_id, uid, device, function_id, data, form, form_ret)


    def topic_and_message_for_request(self, client_id, uid, device, function_id, data, form, form_ret):
        function_info = self.mqtt_function_info[device.DEVICE_IDENTIFIER][function_id]
        device_name = mqtt_names[device.DEVICE_IDENTIFIER]
        function_name = function_info.name
        data_dict =  {key:value for (key,value) in zip(function_info.arg_names, data)}
        message = json.dumps(data_dict)
        topic = "%s/%s/request/%s/%s/%s" % (self.prefix, client_id, device_name, uid, function_name)
        return topic, message


    def start(self):

        client = mqtt.Client()
        client.username_pw_set(self.username, self.password)

        if self.tls_certificate is not None:
            client.tls_set(self.tls_certificate)

        if self.tls_insecure:
            client.tls_insecure_set(True)

        client.on_connect = ConnectCallback(self)
        client.on_message = MessageCallback(self)
        client.connect("localhost", 8883, 60)
        client.loop_forever()


    # The callback for when the client receives a CONNACK response from the server.
    def on_connect(self, client, userdata, flags, rc):
        print("Connected with result code " + str(rc))
        # Subscribing in on_connect() means that if we lose the connection and
        # reconnect then subscriptions will be renewed.
        client.subscribe("ishiki/+/callback/ip_connection/enumerate")


    def on_message(self, client, userdata, msg):

        print("******************************")
        # print(msg.topic + " " + str(msg.payload))

        parts = msg.topic.split("/")

        ishiki_id = parts[1]
        operation = parts[2]
        device = parts[3]  ## brick/let type name eg oled_64x48_bricklet or ip_connection
        if device == IP_CONNECTION:
            uuid = None
            function = parts[4]
        else:
            uuid = parts[4]
            function = parts[5]

        print("device: ", device)
        print("operation: ", operation)
        print("function: ", function)

        message = msg.payload.decode("utf-8")
        message_dict = json.loads(message)

        if device == IP_CONNECTION and operation == OPERATION_CALLBACK and function == FUNCTION_ENUMERATE:
            self.device_enumerated(ishiki_id, message_dict)



    def device_enumerated(self, client_id, info):

        print("client_id: %s" % client_id)
        print("message: %s" % json.dumps(info, indent=4))

        wrapper = BrickWrapper(self, client_id, info)

        # if info["device_identifier"] == device_factory.BrickletTemperature.DEVICE_IDENTIFIER:
        #
        #     wrapper.brick.register_callback(callback_id, function)

