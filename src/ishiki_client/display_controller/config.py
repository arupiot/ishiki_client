
try:
    import ishiki_client.display_controller.config_local as local_config
except ModuleNotFoundError as e:
    local_config = None

from ishiki_client.shared.config_helper import ConfigHelper

helper = ConfigHelper(local_config)

HOST = helper.string("HOST", default="localhost")
PORT = helper.int("PORT", 4223)
IMAGE_URL = helper.string("IMAGE_URL", "ishiki_eink/eink.png")