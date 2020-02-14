
try:
    import ishiki_client.mqtt_gateway.config_local as local_config
except ModuleNotFoundError as e:
    local_config = None

from ishiki_client.shared.config_helper import ConfigHelper

helper = ConfigHelper(local_config)

IPCON_HOST = helper.string("IPCON_HOST", default="localhost")
IPCON_PORT = helper.int("IPCON_PORT", default=4223)
IPCON_AUTH_SECRET = helper.string("IPCON_AUTH_SECRET", default="")
IPCON_TIMEOUT = helper.int("IPCON_TIMEOUT", default=4223)

BROKER_HOST = helper.string("BROKER_HOST", default="localhost")
BROKER_PORT = helper.int("BROKER_PORT", default=1883)
BROKER_AUTH = helper.string("BROKER_AUTH")
BROKER_USERNAME = helper.string("BROKER_USERNAME")
BROKER_PASSWORD = helper.string("BROKER_PASSWORD")
BROKER_CERTIFICATE = helper.string("BROKER_CERTIFICATE")
BROKER_TLS_INSECURE = helper.bool("BROKER_TLS_INSECURE")

CREDENTIALS_PATH = helper.string("CREDENTIALS_PATH")
GLOBAL_TOPIC_PREFIX = helper.string("GLOBAL_TOPIC_PREFIX", default="tinkerforge")
DEBUG = helper.bool("DEBUG")
NO_SYMBOLIC_RESPONSE = helper.bool("NO_SYMBOLIC_RESPONSE")
SHOW_PAYLOAD = helper.bool("SHOW_PAYLOAD")
INIT_FILE = helper.string("INIT_FILE")

zmq_port = helper.string("ZMQ_PORT")

if len(GLOBAL_TOPIC_PREFIX) > 0 and not GLOBAL_TOPIC_PREFIX.endswith('/'):
    GLOBAL_TOPIC_PREFIX += '/'