

from ishiki_client.listener.mqtt_connection import MqttConnection
import ishiki_client.listener.config as config



def start():

    connection = MqttConnection(config.USERNAME,
                                config.PASSWORD,
                                config.TLS_CERTIFICATE,
                                config.TLS_INSECURE)

    connection.start()




