import os
import json
import paho.mqtt.client as mqtt


from ishiki_client.listener.bricks.base_brick import BaseBrick

IP_CONNECTION = "ip_connection"
OPERATION_CALLBACK = "callback"
FUNCTION_ENUMERATE = "enumerate"

import ishiki_client.listener.config as config

# The callback for when the client receives a CONNACK response from the server.
def on_connect(client, userdata, flags, rc):
    print("Connected with result code " + str(rc))
    # Subscribing in on_connect() means that if we lose the connection and
    # reconnect then subscriptions will be renewed.
    client.subscribe("ishiki/#")


def on_message(client, userdata, msg):

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
        device_enumerated(ishiki_id, message_dict)


def device_enumerated(client_id, info):

    print("client_idclient_id: %s" % client_id)
    print("message: %s" % json.dumps(info, indent=4))

    brick = BaseBrick(client_id, info)


def start():

    username = config.USERNAME
    password = config.PASSWORD
    tls_certificate = config.TLS_CERTIFICATE
    tls_insecure = config.TLS_INSECURE

    client = mqtt.Client()
    client.username_pw_set(username, password)

    if tls_certificate is not None:
        client.tls_set(tls_certificate)

    if tls_insecure:
        client.tls_insecure_set(True)

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect("localhost", 8883, 60)
    client.loop_forever()
