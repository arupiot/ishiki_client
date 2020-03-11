import sys
import time
import jwt
import os
import json
import signal
from collections import OrderedDict


from ishiki_client.shared import tinkerforge_mqtt as tf

from .init_controller import InitController
import ishiki_client.mqtt_gateway.config as config



def create_jwt_token(username, credentials_path):

    with open(credentials_path, "r") as f:
        creds = json.loads(f.read())

    now = int(time.time())

    payload = {"iss": username,
               "sub": username,
               "iat": now,
               "exp": now + 60
               }

    return jwt.encode(payload, creds["private_key"], algorithm='RS256').decode("utf-8")

def start():

    signal.signal(signal.SIGINT, tf.terminate)
    signal.signal(signal.SIGTERM, tf.terminate)
    signal.signal(signal.SIGQUIT, tf.terminate)

    ## this replaces the username with a jwt token signed with the credentails
    if config.BROKER_AUTH == "jwt":
        if config.CREDENTIALS_PATH is None:
            raise Exception("You have to provide CREDENTIALS_PATH to do jwt auth")
        broker_username = create_jwt_token(config.BROKER_USERNAME, config.CREDENTIALS_PATH)
        broker_password = "not_a_password"
    else:
        broker_username = config.BROKER_USERNAME
        broker_password = config.BROKER_PASSWORD

    if config.INIT_FILE is not None:
        try:
            with open(config.INIT_FILE) as f:
                initial_config = json.load(f, object_pairs_hook=OrderedDict)
        except Exception as e:
            print("Could not read init file: {}".format(str(e)))
            sys.exit(tf.ERROR_COULD_NOT_READ_INIT_FILE)
    else:
        controller = InitController(config.IPCON_HOST, config.IPCON_PORT, config.GLOBAL_TOPIC_PREFIX)
        initial_config = controller.get_init_json()

    bindings = tf.MQTTBindings(config.DEBUG,
                               config.NO_SYMBOLIC_RESPONSE,
                               config.SHOW_PAYLOAD,
                               config.GLOBAL_TOPIC_PREFIX,
                               float(config.IPCON_TIMEOUT)/1000,
                               broker_username,
                               broker_password,
                               config.BROKER_CERTIFICATE,
                               config.BROKER_TLS_INSECURE)
    tf.bindings = bindings

    bindings.connect_to_broker(config.BROKER_HOST, config.BROKER_PORT)
    if 'pre_connect' in initial_config:
        print("running pre_connect %s" % initial_config['pre_connect'])
        bindings.run_config(initial_config['pre_connect'])
    bindings.connect_to_brickd(config.IPCON_HOST, config.IPCON_PORT, config.IPCON_AUTH_SECRET)
    if 'post_connect' in initial_config:
        print("running post_connect: %s" % initial_config['post_connect'])
        bindings.run_config(initial_config['post_connect'])
    else:
        bindings.run_config(initial_config)
    bindings.run()

if __name__ == '__main__':
    start()
