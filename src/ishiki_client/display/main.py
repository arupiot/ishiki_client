from io import BytesIO
import time
import requests

from ishiki_client.shared.tinkerforge_controller import TinkerforgeController
from tinkerforge.bricklet_e_paper_296x128 import BrickletEPaper296x128
from tinkerforge.bricklet_temperature import BrickletTemperature

from PIL import Image

import ishiki_client.display.config as config

REFRESH_TIMEOUT = 60 * 60 * 2


class DisplayController(TinkerforgeController):

    def __init__(self, host, port):

        self.counter = 0
        self.width = 296  # Columns
        self.height = 128  # Rows
        self.image = None
        self.epaper = None
        self.temperature_sensor = None
        self.temperature = None

        super().__init__(host, port)


    def next(self):
        if self.counter == 0:
            self.draw()

        self.write_data()

        if self.epaper is not None:
            self.counter += 1

        if self.counter == REFRESH_TIMEOUT:
            self.counter = 0


    # Convert PIL image to matching color bool list
    def bool_list_from_pil_image(self, image, width=296, height=128, color=(0, 0, 0)):
        image_data = image.load()
        pixels = []

        for row in range(height):
            for column in range(width):
                pixel = image_data[column, row]
                value = (pixel[0] == color[0]) and (pixel[1] == color[1]) and (pixel[2] == color[2])
                pixels.append(value)

        return pixels

    def get_image(self):
        ## returns existing image if not None
        ## else trys to get an image from a local file or remote url or returns None
        if self.image is not None:
            return self.image
        location = config.IMAGE_URL
        if location.startswith("http"):
            r = requests.get(location)
            if r.status_code == 200:
                self.image = Image.open(BytesIO(r.content))
                print("downloaded image")
            else:
                print("failed to download image")
        else:
            self.image = Image.open(location)
        return self.image


    def draw(self):

        if self.epaper is not None:

            image = self.get_image()

            if image is not None:
                self.wait_for_idle()
                self.epaper.set_update_mode(BrickletEPaper296x128.UPDATE_MODE_DEFAULT)
                # Get black/white pixels from image and write them to the Bricklet buffer
                pixels_bw = self.bool_list_from_pil_image(image, self.width, self.height, (0xFF, 0xFF, 0xFF))
                self.epaper.write_black_white(0, 0, self.width - 1, self.height - 1, pixels_bw)

                # Get red pixels from image and write them to the Bricklet buffer
                pixels_red = self.bool_list_from_pil_image(image, self.width, self.height, (0xFF, 0, 0))
                self.epaper.write_color(0, 0, self.width - 1, self.height - 1, pixels_red)

                # Draw buffered values to the display
                self.epaper.draw()


    def write_data(self):

        if self.temperature_sensor is not None:
            new_temperature = self.temperature_sensor.get_temperature()/100.0
            if self.temperature is not None:
                if abs(new_temperature - self.temperature) >= 0.1:
                    self.temperature = new_temperature
                    self.write_temperature()
            else:
                self.temperature = new_temperature
                self.write_temperature()

    def wait_for_idle(self):

        status = self.epaper.get_draw_status()
        while status != BrickletEPaper296x128.DRAW_STATUS_IDLE:
            status = self.epaper.get_draw_status()
            time.sleep(1)

    def write_temperature(self):

        self.wait_for_idle()
        self.epaper.set_update_mode(BrickletEPaper296x128.UPDATE_MODE_DELTA)
        self.epaper.draw_box(150, 9, 295, 30, True, BrickletEPaper296x128.COLOR_WHITE)

        self.epaper.draw_text(210,
                              10,
                              BrickletEPaper296x128.FONT_12X16,
                              BrickletEPaper296x128.COLOR_BLACK,
                              BrickletEPaper296x128.ORIENTATION_HORIZONTAL,
                              "%.1f C" % self.temperature)
        self.epaper.draw()


    def cb_enumerate(self,
                     uid,
                     connected_uid,
                     position,
                     hardware_version,
                     firmware_version,
                     device_identifier,
                     enumeration_type):

        if device_identifier == BrickletEPaper296x128.DEVICE_IDENTIFIER:
            self.epaper = BrickletEPaper296x128(uid, self.ipcon)
        if device_identifier == BrickletTemperature.DEVICE_IDENTIFIER:
            self.temperature_sensor = BrickletTemperature(uid, self.ipcon)

def start():

    controller = DisplayController(config.HOST, config.PORT)
    controller.run()

if __name__ == '__main__':
    start()