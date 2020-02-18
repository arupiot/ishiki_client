from tinkerforge.bricklet_e_paper_296x128 import BrickletEPaper296x128
from ishiki_client.display_controller.controller import DisplayController
import ishiki_client.display_controller.config as config

class ArupDisplayController(DisplayController):


    def __init__(self, host, port):

        self.temperature = None
        self.pressure = None
        self.humidity = None
        self.decibels = None
        self.motion = None

        super().__init__(host, port)


    def write_data(self):

        if self.e_paper_296x128 is not None:

            if self.air_quality is not None:
                new_temperature = self.air_quality.get_temperature()/100.0
                self.update(new_temperature, "temperature", 0.1, "%.1f   C", 0)

                new_humidity = self.air_quality.get_humidity() / 100.0
                self.update(new_humidity, "humidity", 0.1, "%.1f   %%RH", 1)

            if self.sound_pressure_level is not None:
                new_decibels = self.sound_pressure_level.get_decibel()/10.0
                self.update(new_decibels, "decibels", 3, "%.1f   dB", 3)

            if self.motion_detector_v2 is not None:
                new_motion = self.motion_detector_v2.get_motion_detected()
                self.update(new_motion, "motion", 0.5, "%s   motion", 2)

            else:
                if self.air_quality is not None:

                    new_pressure = self.air_quality.get_air_pressure() / 100.0
                    self.update(new_pressure, "pressure", 0.1, "%.1f hPa", 2)



    def update(self, value, name, threshhold, format, line_number):

        current = getattr(self, name)
        if current is not None:
            if abs(value - current) >= threshhold:
                setattr(self, name, value)
                self.write_a_line(format % value, line_number)
        else:
            setattr(self, name, value)
            self.write_a_line(format % value, line_number)



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