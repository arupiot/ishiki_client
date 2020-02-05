import ishiki_client.listener.config_local as local_config
from ishiki_client.shared.config_helper import ConfigHelper

helper = ConfigHelper(local_config)

USERNAME = helper.string("USERNAME")
PASSWORD = helper.string("PASSWORD")
TLS_CERTIFICATE = helper.string("TLS_CERTIFICATE")
TLS_INSECURE = helper.bool("TLS_INSECURE")
