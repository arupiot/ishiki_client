from io import BytesIO
import time
import requests

from ishiki_client.shared.tinkerforge_controller import TinkerforgeController
from tinkerforge.bricklet_e_paper_296x128 import BrickletEPaper296x128
from tinkerforge.bricklet_temperature import BrickletTemperature
from tinkerforge.bricklet_air_quality import BrickletAirQuality
from tinkerforge.bricklet_sound_pressure_level import BrickletSoundPressureLevel
from tinkerforge.bricklet_rgb_led_button import BrickletRGBLEDButton
from tinkerforge.ip_connection import IPConnection



from PIL import Image

import ishiki_client.display_controller.config as config

REFRESH_TIMEOUT = 60 * 60 * 2


class DisplayController(TinkerforgeController):

    def __init__(self, host, port):

        self.counter = 0
        self.width = 296  # Columns
        self.height = 128  # Rows
        self.image = None
        # self.e_paper_296x128 = None

        super().__init__(host, port)

    def next(self):
        if self.counter == 0:
            self.draw()

        self.write_data()

        if self.e_paper_296x128 is not None:
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
        # returns existing image if not None
        # else trys to get an image from a local file or remote url or returns None
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

        if self.e_paper_296x128 is not None:

            image = self.get_image()

            if image is not None:
                self.wait_for_idle()
                self.e_paper_296x128.set_update_mode(BrickletEPaper296x128.UPDATE_MODE_DEFAULT)
                # Get black/white pixels from image and write them to the Bricklet buffer
                pixels_bw = self.bool_list_from_pil_image(image, self.width, self.height, (0xFF, 0xFF, 0xFF))
                self.e_paper_296x128.write_black_white(0, 0, self.width - 1, self.height - 1, pixels_bw)

                # Get red pixels from image and write them to the Bricklet buffer
                pixels_red = self.bool_list_from_pil_image(image, self.width, self.height, (0xFF, 0, 0))
                self.e_paper_296x128.write_color(0, 0, self.width - 1, self.height - 1, pixels_red)

                # Draw buffered values to the display
                self.e_paper_296x128.draw()

            self.write_device()

    def write_data(self):
        ## override this in the sub class
        pass


    def write_device(self):

        self.wait_for_idle()
        self.e_paper_296x128.set_update_mode(BrickletEPaper296x128.UPDATE_MODE_DELTA)
        self.e_paper_296x128.draw_box(0, 96, 150, 127, True, BrickletEPaper296x128.COLOR_WHITE)



        self.e_paper_296x128.draw_text(10,
                              98,
                              BrickletEPaper296x128.FONT_6X8,
                              BrickletEPaper296x128.COLOR_BLACK,
                              BrickletEPaper296x128.ORIENTATION_HORIZONTAL,
                              config.NAME)

        self.e_paper_296x128.draw_text(10,
                              110,
                              BrickletEPaper296x128.FONT_6X8,
                              BrickletEPaper296x128.COLOR_BLACK,
                              BrickletEPaper296x128.ORIENTATION_HORIZONTAL,
                              config.DEVICE[-6:])

        self.e_paper_296x128.draw()

    def wait_for_idle(self):

        if self.e_paper_296x128 is not None:

            status = self.e_paper_296x128.get_draw_status()
            while status != BrickletEPaper296x128.DRAW_STATUS_IDLE:
                status = self.e_paper_296x128.get_draw_status()
                time.sleep(1)




