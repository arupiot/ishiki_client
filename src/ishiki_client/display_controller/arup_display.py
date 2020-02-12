from tinkerforge.bricklet_e_paper_296x128 import BrickletEPaper296x128
from ishiki_client.display_controller.controller import DisplayController
import ishiki_client.display_controller.config as config

class ArupDisplayController(DisplayController):


    def __init__(self, host, port):

        self.temperature = None
        self.pressure = None
        self.humidity = None
        self.decibels = None

        super().__init__(host, port)


    def write_data(self):

        if self.e_paper_296x128 is not None:

            if self.air_quality is not None:
                new_temperature = self.air_quality.get_temperature()/100.0
                if self.temperature is not None:
                    if abs(new_temperature - self.temperature) >= 0.1:
                        self.temperature = new_temperature
                        self.write_a_line("%.1f   C" % self.temperature, 0)
                else:
                    self.temperature = new_temperature
                    self.write_a_line("%.1f   C" % self.temperature, 0)

                new_humidity = self.air_quality.get_humidity() / 100.0
                if self.humidity is not None:
                    if abs(new_humidity - self.humidity) >= 0.1:
                        self.humidity = new_humidity
                        self.write_a_line("%.1f   %sRH" % (self.humidity, "%"), 1)
                else:
                    self.humidity = new_humidity
                    self.write_a_line("%.1f   %sRH" % (self.humidity, "%"), 1)

                new_pressure = self.air_quality.get_air_pressure() / 100.0
                if self.pressure is not None:
                    if abs(new_pressure - self.pressure) >= 0.1:
                        self.pressure = new_pressure
                        self.write_a_line("%.1f hPa" % self.pressure, 2)
                else:
                    self.pressure = new_pressure
                    self.write_a_line("%.1f hPa" % self.pressure, 2)

            if self.sound_pressure_level is not None:
                new_decibels = self.sound_pressure_level.get_decibel()/10.0
                if self.decibels is not None:
                    if abs(new_decibels - self.decibels) >= 3:
                        self.decibels = new_decibels
                        self.write_a_line("%.1f   dB" % self.decibels, 3)
                else:
                    self.decibels = new_decibels
                    self.write_a_line("%.1f   dB" % self.decibels, 3)


    def write_a_line(self, msg, line):

        top = 15
        gap = line * 25
        y = top + gap

        self.wait_for_idle()
        self.e_paper_296x128.set_update_mode(BrickletEPaper296x128.UPDATE_MODE_DELTA)
        self.e_paper_296x128.draw_box(150, y, 295, y + 16, True, BrickletEPaper296x128.COLOR_WHITE)

        self.e_paper_296x128.draw_text(160,
                              y + 1,
                              BrickletEPaper296x128.FONT_12X16,
                              BrickletEPaper296x128.COLOR_BLACK,
                              BrickletEPaper296x128.ORIENTATION_HORIZONTAL,
                              msg)

        self.e_paper_296x128.draw()
        print(msg)



def start():
    controller = ArupDisplayController(config.HOST, config.PORT)
    controller.run()


if __name__ == '__main__':
    start()