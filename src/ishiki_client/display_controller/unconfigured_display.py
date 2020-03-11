from tinkerforge.bricklet_e_paper_296x128 import BrickletEPaper296x128
from ishiki_client.display_controller.controller import DisplayController
import ishiki_client.display_controller.config as config

class UnconfiguredDisplayController(DisplayController):


    def __init__(self, host, port):

        self.temperature = None
        self.pressure = None
        self.humidity = None
        self.decibels = None
        self.motion = None

        super().__init__(host, port)










def start():
    controller = UnconfiguredDisplayController(config.HOST, config.PORT)
    controller.run()


if __name__ == '__main__':
    start()