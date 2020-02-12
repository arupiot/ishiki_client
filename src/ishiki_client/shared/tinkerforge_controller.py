import time
from tinkerforge.ip_connection import IPConnection
from tinkerforge import device_factory


# oo wrapper for callback using curried callable
class EnumerateCallback:

    def __init__(self, controller):
        self.controller = controller

    def __call__(self, *args, **kwargs):
        self.controller.cb_enumerate(*args, **kwargs)


class TinkerforgeController:

    def __init__(self, host, port):
        print("hello")
        # Create connection and connect to brickd
        self.ipcon = IPConnection()
        self.ipcon.connect(host, port)
        print("connected")
        self.devices = {}


        # Register Enumerate Callback
        self.ipcon.register_callback(IPConnection.CALLBACK_ENUMERATE, EnumerateCallback(self))

        # Trigger Enumerate
        self.ipcon.enumerate()

    def run(self):

        while True:
            try:
                time.sleep(1)
                self.next()
            except KeyboardInterrupt:
                self.stop()
                print("goodbye")
                break

    def next(self):
        print("tick")


    def __getattr__(self, name):
        if name in self.devices:
            return self.devices[name]
        else:
            raise AttributeError("Not found %s" % name)


    def cb_enumerate(self,
                     uid,
                     connected_uid,
                     position,
                     hardware_version,
                     firmware_version,
                     device_identifier,
                     enumeration_type):


        device_class = device_factory.get_device_class(device_identifier)
        device = device_class(uid, self.ipcon)
        device_name = device_class.DEVICE_URL_PART

        counter = 2
        while device_name in self.devices:
            if device.uid == self.devices[device_name].uid:
                return
            device_name = "%s_%s" % (device_name, counter)
            counter += 1

        print("found %s" % device_name)
        self.devices[device_name] = device


        # print("UID:               " + uid)
        # print("Enumeration Type:  " + str(enumeration_type))
        #
        # if enumeration_type == IPConnection.ENUMERATION_TYPE_DISCONNECTED:
        #     print("")
        #     return
        #
        # print("Connected UID:     " + connected_uid)
        # print("Position:          " + position)
        # print("Hardware Version:  " + str(hardware_version))
        # print("Firmware Version:  " + str(firmware_version))
        # print("Device Identifier: " + str(device_identifier))
        # print("")


    def stop(self):

        self.ipcon.disconnect()
        print("\ndisconnected")

