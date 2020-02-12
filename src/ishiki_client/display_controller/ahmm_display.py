from ishiki_client.display_controller.controller import DisplayController

class ArupDisplayController(DisplayController):

    def write_data(self):
        pass

        # if self.temperature_sensor is not None:
        #     new_temperature = self.temperature_sensor.get_temperature() / 100.0
        #     if self.temperature is not None:
        #         if abs(new_temperature - self.temperature) >= 0.1:
        #             self.temperature = new_temperature
        #             self.write_temperature()
        #     else:
        #         self.temperature = new_temperature
        #         self.write_temperature()

    # def write_temperature(self):
    #
    #     self.wait_for_idle()
    #     self.epaper.set_update_mode(BrickletEPaper296x128.UPDATE_MODE_DELTA)
    #     self.epaper.draw_box(150, 9, 295, 30, True, BrickletEPaper296x128.COLOR_WHITE)
    #
    #     self.epaper.draw_text(210,
    #                           10,
    #                           BrickletEPaper296x128.FONT_12X16,
    #                           BrickletEPaper296x128.COLOR_BLACK,
    #                           BrickletEPaper296x128.ORIENTATION_HORIZONTAL,
    #                           "%.1f C" % self.temperature)
    #     self.epaper.draw()
    #     print("temperature: %.1f C" % self.temperature)