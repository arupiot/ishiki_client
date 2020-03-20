import socket
import os
import qrcode
import ishiki_client
from tinkerforge.bricklet_e_paper_296x128 import BrickletEPaper296x128
from ishiki_client.display_controller.controller import DisplayController
import ishiki_client.display_controller.config as config

THIS_DIR = os.path.dirname(ishiki_client.display_controller.__file__)

class UnconfiguredDisplayController(DisplayController):


    def __init__(self, host, port):

        self.temperature = None
        self.pressure = None
        self.humidity = None
        self.decibels = None
        self.motion = None

        super().__init__(host, port)

    def get_address(self):
        try:
            host_name = socket.gethostname()
            host_ip = socket.gethostbyname(host_name)
            print("Hostname :  ", host_name)
            print("IP : ", host_ip)
            return host_ip
        except:
            print("Unable to get Hostname and IP")

    def get_ip(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # doesn't even have to be reachable
            s.connect(('10.255.255.255', 1))
            IP = s.getsockname()[0]
        except:
            IP = '127.0.0.1'
        finally:
            s.close()
        return IP

    def getMAC(interface='en0'):
        try:
            str = open('/sys/class/net/%s/address' % interface).read()
        except:
            str = "00:00:00:00:00:00"
        return str[0:17]


    def write_device(self):

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=3,
            border=0,
        )
        qr.add_data(config.QRCODE_DATA)
        qr.make(fit=True)

        image = qr.make_image(fill_color="black", back_color="white")
        side = image.height
        image_data = image.load()
        pixels = []

        for row in range(side):
            for column in range(side):
                pixel = image_data[column, row]
                value = pixel == 255
                pixels.append(value)


        self.wait_for_idle()
        self.e_paper_296x128.set_update_mode(BrickletEPaper296x128.UPDATE_MODE_DEFAULT)

        self.e_paper_296x128.write_black_white(175, 15, 175 + side - 1, 15 + side - 1, pixels)
        self.e_paper_296x128.draw()

        self.wait_for_idle()
        self.e_paper_296x128.set_update_mode(BrickletEPaper296x128.UPDATE_MODE_DELTA)
        self.e_paper_296x128.draw_box(0, 96, 150, 127, True, BrickletEPaper296x128.COLOR_WHITE)

        self.e_paper_296x128.draw_text(10,
                              98,
                              BrickletEPaper296x128.FONT_6X8,
                              BrickletEPaper296x128.COLOR_BLACK,
                              BrickletEPaper296x128.ORIENTATION_HORIZONTAL,
                              "MAC: %s" % self.getMAC())

        self.e_paper_296x128.draw_text(10,
                              110,
                              BrickletEPaper296x128.FONT_6X8,
                              BrickletEPaper296x128.COLOR_BLACK,
                              BrickletEPaper296x128.ORIENTATION_HORIZONTAL,
                              "IP:  %s" % self.get_ip())

        self.e_paper_296x128.draw()


def start():
    controller = UnconfiguredDisplayController(config.HOST, config.PORT)
    controller.run()





if __name__ == '__main__':
    start()