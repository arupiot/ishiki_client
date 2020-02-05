import json
import zmq
import paho.mqtt.client as mqtt
import ishiki_tinker.config as config

class PluggableClient(mqtt.Client):

    def __init__(self, *args, **kwargs):
        self.zmq_socket = None
        self.zmq_context = None
        print("plugged")
        super().__init__(*args, **kwargs)
        if config.zmq_port is not None:
            self.connect_zmq()

    def publish(self, topic, payload=None, qos=0, retain=False, properties=None):
        print(topic)
        print(payload)
        super().publish(topic, payload=payload, qos=qos, retain=retain, properties=properties)
        if self.zmq_socket is not None:
            self.publish_to_zmq(topic, payload=payload)

    def publish_to_zmq(self, topic, payload=None):

        btopic = topic.encode("utf-8")
        bpayload = payload.encode("utf-8")

        try:
            self.zmq_socket.send_multipart([btopic, bpayload])
            print("published to ZMQ")
        except Exception as e:
            print("Error publishing to ZMQ:")
            print(e)

    def disconnect(self):
        super().disconnect()
        if self.zmq_context is not None:
            self.zmq_socket.close()
            self.zmq_context.term()

    def connect_zmq(self):
        self.zmq_context = zmq.Context()
        self.zmq_socket = self.zmq_context.socket(zmq.PUB)
        self.zmq_socket.bind("tcp://*:%s" % config.zmq_port)

mqtt.Client = PluggableClient