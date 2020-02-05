from ishiki_client.shared.tinkerforge_controller import TinkerforgeController
from tinkerforge.bricklet_e_paper_296x128 import BrickletEPaper296x128
from PIL import Image

import ishiki_client.display.config as config


class DisplayController(TinkerforgeController):

    def __init__(self, host, port):

        self.counter = 0
        self.width = 296  # Columns
        self.height = 128  # Rows

        super().__init__(host, port)


    def next(self):
        if self.counter == 0:
            self.draw()

        if self.epaper is not None:
            self.counter += 1

        if self.counter == 300:
            self.counter = 0

        print("tick")


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

    def draw(self):

        if self.epaper is not None:

            location = config.IMAGE_URL

            if location.startswith("http"):
                image = None
            else:
                image = Image.open(location)

            if image is not None:

                # Get black/white pixels from image and write them to the Bricklet buffer
                pixels_bw = self.bool_list_from_pil_image(image, self.width, self.height, (0xFF, 0xFF, 0xFF))
                self.epaper.write_black_white(0, 0, self.width - 1, self.height - 1, pixels_bw)

                # Get red pixels from image and write them to the Bricklet buffer
                pixels_red = self.bool_list_from_pil_image(image, self.width, self.height, (0xFF, 0, 0))
                self.epaper.write_color(0, 0, self.width - 1, self.height - 1, pixels_red)

                # Draw buffered values to the display
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


def start():

    controller = DisplayController(config.HOST, config.PORT)
    controller.run()

if __name__ == '__main__':
    start()