#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (C) 2019 Erik Fleckstein <erik@tinkerforge.com>
#
# Version 2.0.8
#
# Redistribution and use in source and binary forms of this file,
# with or without modification, are permitted. See the Creative
# Commons Zero (CC0 1.0) License for more details.

import sys
import os
import signal
import time
import shlex
import socket
import select
import threading
import subprocess
import textwrap
from collections import namedtuple, OrderedDict
if sys.version_info < (3,3):
    from collections import Hashable
else:
    from collections.abc import Hashable
import json
import logging
import traceback
import argparse

# error codes are also used as exit codes, valid values are [1..255]
ERROR_INTERRUPTED = 1
ERROR_SYNTAX_ERROR = 2
ERROR_PYTHON_VERSION = 21
ERROR_ARGPARSE_MISSING = 22
ERROR_SOCKET_ERROR = 23
ERROR_OTHER_EXCEPTION = 24
ERROR_INVALID_PLACEHOLDER = 25
ERROR_AUTHENTICATION_ERROR = 26
ERROR_OUTPUT_NOT_ESCAPABLE_ERROR = 27
ERROR_PAHO_MISSING = 28
ERROR_PAHO_VERSION = 29
ERROR_NO_CONNECTION_TO_BROKER = 30
ERROR_COULD_NOT_READ_INIT_FILE = 31
IPCONNECTION_ERROR_OFFSET = 200

def fatal_error(message, exit_code):
    logging.critical(message)
    sys.exit(exit_code)

try:
    import paho.mqtt
except ImportError:
    fatal_error("requiring paho 1.3.1 or newer.", ERROR_PAHO_MISSING)

from distutils.version import LooseVersion, StrictVersion
if paho.mqtt.__version__ < StrictVersion("1.3.1"):
    fatal_error("Paho version has to be at lease 1.3.1, but was " + str(paho.mqtt.__version__), ERROR_PAHO_VERSION)

import paho.mqtt.client as mqtt


if sys.hexversion < 0x02070900:
    fatal_error('requiring python 2.7.9 or 3.4 or newer', ERROR_PYTHON_VERSION)

if sys.hexversion > 0x03000000 and sys.hexversion < 0x03040000:
    fatal_error('requiring python 2.7.9 or 3.4 or newer', ERROR_PYTHON_VERSION)

try:
    import argparse
except ImportError:
    fatal_error('requiring python argparse module', ERROR_ARGPARSE_MISSING)

FunctionInfo = namedtuple('FunctionInfo', ['id', 'arg_names', 'arg_types', 'arg_symbols', 'payload_fmt', 'result_names', 'result_symbols', 'response_fmt'])
HighLevelFunctionInfo = namedtuple('HighLevelFunctionInfo',
    ['low_level_id', 'direction',
     'high_level_roles_in', 'high_level_roles_out', 'low_level_roles_in', 'low_level_roles_out',
     'arg_names', 'arg_types', 'arg_symbols', 'format_in', 'result_names', 'result_symbols', 'format_out',
     'chunk_padding', 'chunk_cardinality', 'chunk_max_offset',
     'short_write', 'single_read', 'fixed_length'])
CallbackInfo = namedtuple('CallbackInfo', ['id', 'names', 'symbols', 'fmt', 'high_level_info'])



# -*- coding: utf-8 -*-
# Copyright (C) 2012-2015, 2017, 2019 Matthias Bolte <matthias@tinkerforge.com>
# Copyright (C) 2011-2012 Olaf Lüke <olaf@tinkerforge.com>
#
# Redistribution and use in source and binary forms of this file,
# with or without modification, are permitted. See the Creative
# Commons Zero (CC0 1.0) License for more details.

import struct
import socket
import sys
import time
import os
import math
import hmac
import hashlib
import errno
import threading

try:
    import queue # Python 3
except ImportError:
    import Queue as queue # Python 2

def get_uid_from_data(data):
    return struct.unpack('<I', data[0:4])[0]

def get_length_from_data(data):
    return struct.unpack('<B', data[4:5])[0]

def get_function_id_from_data(data):
    return struct.unpack('<B', data[5:6])[0]

def get_sequence_number_from_data(data):
    return (struct.unpack('<B', data[6:7])[0] >> 4) & 0x0F

def get_error_code_from_data(data):
    return (struct.unpack('<B', data[7:8])[0] >> 6) & 0x03

BASE58 = '123456789abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ'

def base58encode(value):
    encoded = ''

    while value >= 58:
        div, mod = divmod(value, 58)
        encoded = BASE58[mod] + encoded
        value = div

    return BASE58[value] + encoded

def base58decode(encoded):
    value = 0
    column_multiplier = 1

    for c in encoded[::-1]:
        try:
            column = BASE58.index(c)
        except ValueError:
            raise Error(Error.INVALID_UID, 'UID "{0}" contains invalid character'.format(encoded), suppress_context=True)

        value += column * column_multiplier
        column_multiplier *= 58

    return value

def uid64_to_uid32(uid64):
    value1 = uid64 & 0xFFFFFFFF
    value2 = (uid64 >> 32) & 0xFFFFFFFF

    uid32  = (value1 & 0x00000FFF)
    uid32 |= (value1 & 0x0F000000) >> 12
    uid32 |= (value2 & 0x0000003F) << 16
    uid32 |= (value2 & 0x000F0000) << 6
    uid32 |= (value2 & 0x3F000000) << 2

    return uid32

def create_chunk_data(data, chunk_offset, chunk_length, chunk_padding):
    chunk_data = data[chunk_offset:chunk_offset + chunk_length]

    if len(chunk_data) < chunk_length:
        chunk_data += [chunk_padding] * (chunk_length - len(chunk_data))

    return chunk_data

if sys.hexversion < 0x03000000:
    def create_char(value): # return str with len() == 1 and ord() <= 255
        if isinstance(value, str) and len(value) == 1: # Python2 str satisfies ord() <= 255 by default
            return value
        elif isinstance(value, unicode) and len(value) == 1:
            code_point = ord(value)

            if code_point <= 255:
                return chr(code_point)
            else:
                raise ValueError('Invalid char value: ' + repr(value))
        elif isinstance(value, bytearray) and len(value) == 1: # Python2 bytearray satisfies item <= 255 by default
            return chr(value[0])
        elif isinstance(value, int) and value >= 0 and value <= 255:
            return chr(value)
        else:
            raise ValueError('Invalid char value: ' + repr(value))
else:
    def create_char(value): # return str with len() == 1 and ord() <= 255
        if isinstance(value, str) and len(value) == 1 and ord(value) <= 255:
            return value
        elif isinstance(value, (bytes, bytearray)) and len(value) == 1: # Python3 bytes/bytearray satisfies item <= 255 by default
            return chr(value[0])
        elif isinstance(value, int) and value >= 0 and value <= 255:
            return chr(value)
        else:
            raise ValueError('Invalid char value: ' + repr(value))

if sys.hexversion < 0x03000000:
    def create_char_list(value, expected_type='char list'): # return list of str with len() == 1 and ord() <= 255 for all items
        if isinstance(value, list):
            return map(create_char, value)
        elif isinstance(value, str): # Python2 str satisfies ord() <= 255 by default
            return list(value)
        elif isinstance(value, unicode):
            chars = []

            for char in value:
                code_point = ord(char)

                if code_point <= 255:
                    chars.append(chr(code_point))
                else:
                    raise ValueError('Invalid {0} value: {1}'.format(expected_type, repr(value)))

            return chars
        elif isinstance(value, bytearray): # Python2 bytearray satisfies item <= 255 by default
            return map(chr, value)
        else:
            raise ValueError('Invalid {0} value: {1}'.format(expected_type, repr(value)))
else:
    def create_char_list(value, expected_type='char list'): # return list of str with len() == 1 and ord() <= 255 for all items
        if isinstance(value, list):
            return list(map(create_char, value))
        elif isinstance(value, str):
            chars = list(value)

            for char in chars:
                if ord(char) > 255:
                    raise ValueError('Invalid {0} value: {1}'.format(expected_type, repr(value)))

            return chars
        elif isinstance(value, (bytes, bytearray)): # Python3 bytes/bytearray satisfies item <= 255 by default
            return list(map(chr, value))
        else:
            raise ValueError('Invalid {0} value: {1}'.format(expected_type, repr(value)))

if sys.hexversion < 0x03000000:
    def create_string(value): # return str with ord() <= 255 for all chars
        if isinstance(value, str): # Python2 str satisfies ord() <= 255 by default
            return value
        elif isinstance(value, unicode):
            chars = []

            for char in value:
                code_point = ord(char)

                if code_point <= 255:
                    chars.append(chr(code_point))
                else:
                    raise ValueError('Invalid string value: {0}'.format(repr(value)))

            return ''.join(chars)
        elif isinstance(value, bytearray): # Python2 bytearray satisfies item <= 255 by default
            chars = []

            for byte in value:
                chars.append(chr(byte))

            return ''.join(chars)
        else:
            return ''.join(create_char_list(value, expected_type='string'))
else:
    def create_string(value): # return str with ord() <= 255 for all chars
        if isinstance(value, str):
            for char in value:
                if ord(char) > 255:
                    raise ValueError('Invalid string value: {0}'.format(repr(value)))

            return value
        elif isinstance(value, (bytes, bytearray)): # Python3 bytes/bytearray satisfies item <= 255 by default
            chars = []

            for byte in value:
                chars.append(chr(byte))

            return ''.join(chars)
        else:
            return ''.join(create_char_list(value, expected_type='string'))

def pack_payload(data, form):
    if sys.hexversion < 0x03000000:
        packed = ''
    else:
        packed = b''

    for f, d in zip(form.split(' '), data):
        if '!' in f:
            if len(f) > 1:
                if int(f.replace('!', '')) != len(d):
                    raise ValueError('Incorrect bool list length')

                p = [0] * int(math.ceil(len(d) / 8.0))

                for i, b in enumerate(d):
                    if b:
                        p[i // 8] |= 1 << (i % 8)

                packed += struct.pack('<{0}B'.format(len(p)), *p)
            else:
                packed += struct.pack('<?', d)
        elif 'c' in f:
            if sys.hexversion < 0x03000000:
                if len(f) > 1:
                    packed += struct.pack('<' + f, *d)
                else:
                    packed += struct.pack('<' + f, d)
            else:
                if len(f) > 1:
                    packed += struct.pack('<' + f, *list(map(lambda char: bytes([ord(char)]), d)))
                else:
                    packed += struct.pack('<' + f, bytes([ord(d)]))
        elif 's' in f:
            if sys.hexversion < 0x03000000:
                packed += struct.pack('<' + f, d)
            else:
                packed += struct.pack('<' + f, bytes(map(ord, d)))
        elif len(f) > 1:
            packed += struct.pack('<' + f, *d)
        else:
            packed += struct.pack('<' + f, d)

    return packed

def unpack_payload(data, form):
    ret = []

    for f in form.split(' '):
        o = f

        if '!' in f:
            if len(f) > 1:
                f = '{0}B'.format(int(math.ceil(int(f.replace('!', '')) / 8.0)))
            else:
                f = 'B'

        f = '<' + f
        length = struct.calcsize(f)
        x = struct.unpack(f, data[:length])

        if '!' in o:
            y = []

            if len(o) > 1:
                for i in range(int(o.replace('!', ''))):
                    y.append(x[i // 8] & (1 << (i % 8)) != 0)
            else:
                y.append(x[0] != 0)

            x = tuple(y)

        if 'c' in f:
            if sys.hexversion < 0x03000000:
                if len(x) > 1:
                    ret.append(x)
                else:
                    ret.append(x[0])
            else:
                if len(x) > 1:
                    ret.append(tuple(map(lambda item: chr(ord(item)), x)))
                else:
                    ret.append(chr(ord(x[0])))
        elif 's' in f:
            if sys.hexversion < 0x03000000:
                s = x[0]
            else:
                s = ''.join(map(chr, x[0]))

            i = s.find('\x00')

            if i >= 0:
                s = s[:i]

            ret.append(s)
        elif len(x) > 1:
            ret.append(x)
        else:
            ret.append(x[0])

        data = data[length:]

    if len(ret) == 1:
        return ret[0]
    else:
        return ret

class Error(Exception):
    TIMEOUT = -1
    NOT_ADDED = -6 # obsolete since v2.0
    ALREADY_CONNECTED = -7
    NOT_CONNECTED = -8
    INVALID_PARAMETER = -9
    NOT_SUPPORTED = -10
    UNKNOWN_ERROR_CODE = -11
    STREAM_OUT_OF_SYNC = -12
    INVALID_UID = -13
    NON_ASCII_CHAR_IN_SECRET = -14

    def __init__(self, value, description, suppress_context=False):
        Exception.__init__(self, '{0} ({1})'.format(description, value))

        self.value = value
        self.description = description

        if sys.hexversion >= 0x03000000 and suppress_context:
            # this is a Python 2 syntax compatible form of the "raise ... from None"
            # syntax in Python 3. especially the timeout error shows in Python 3
            # the queue.Empty exception as its context. this is confusing and doesn't
            # help much. the "raise ... from None" syntax in Python 3 stops the
            # default traceback printer from outputting the context of the exception
            # while keeping the queue.Empty exception in the __context__ field for
            # debugging purposes.
            self.__cause__ = None
            self.__suppress_context__ = True

class Device(object):
    RESPONSE_EXPECTED_INVALID_FUNCTION_ID = 0
    RESPONSE_EXPECTED_ALWAYS_TRUE = 1 # getter
    RESPONSE_EXPECTED_TRUE = 2 # setter
    RESPONSE_EXPECTED_FALSE = 3 # setter, default

    def __init__(self, uid, ipcon):
        """
        Creates the device object with the unique device ID *uid* and adds
        it to the IPConnection *ipcon*.
        """

        uid_ = base58decode(uid)

        if uid_ > (1 << 64) - 1:
            raise Error(Error.INVALID_UID, 'UID "{0}" is too big'.format(uid))

        if uid_ > (1 << 32) - 1:
            uid_ = uid64_to_uid32(uid_)

        if uid_ == 0:
            raise Error(Error.INVALID_UID, 'UID "{0}" is empty or maps to zero'.format(uid))

        self.uid = uid_
        self.ipcon = ipcon
        self.api_version = (0, 0, 0)
        self.registered_callbacks = {}
        self.callback_formats = {}
        self.high_level_callbacks = {}
        self.expected_response_function_id = None # protected by request_lock
        self.expected_response_sequence_number = None # protected by request_lock
        self.response_queue = queue.Queue()
        self.request_lock = threading.Lock()
        self.stream_lock = threading.Lock()

        self.response_expected = [Device.RESPONSE_EXPECTED_INVALID_FUNCTION_ID] * 256
        self.response_expected[IPConnection.FUNCTION_ADC_CALIBRATE] = Device.RESPONSE_EXPECTED_ALWAYS_TRUE
        self.response_expected[IPConnection.FUNCTION_GET_ADC_CALIBRATION] = Device.RESPONSE_EXPECTED_ALWAYS_TRUE
        self.response_expected[IPConnection.FUNCTION_READ_BRICKLET_UID] = Device.RESPONSE_EXPECTED_ALWAYS_TRUE
        self.response_expected[IPConnection.FUNCTION_WRITE_BRICKLET_UID] = Device.RESPONSE_EXPECTED_ALWAYS_TRUE
        self.response_expected[IPConnection.FUNCTION_READ_BRICKLET_PLUGIN] = Device.RESPONSE_EXPECTED_ALWAYS_TRUE
        self.response_expected[IPConnection.FUNCTION_WRITE_BRICKLET_PLUGIN] = Device.RESPONSE_EXPECTED_ALWAYS_TRUE

        ipcon.devices[self.uid] = self # FIXME: maybe use a weakref here

    def get_api_version(self):
        """
        Returns the API version (major, minor, revision) of the bindings for
        this device.
        """

        return self.api_version

    def get_response_expected(self, function_id):
        """
        Returns the response expected flag for the function specified by the
        *function_id* parameter. It is *true* if the function is expected to
        send a response, *false* otherwise.

        For getter functions this is enabled by default and cannot be disabled,
        because those functions will always send a response. For callback
        configuration functions it is enabled by default too, but can be
        disabled via the set_response_expected function. For setter functions
        it is disabled by default and can be enabled.

        Enabling the response expected flag for a setter function allows to
        detect timeouts and other error conditions calls of this setter as
        well. The device will then send a response for this purpose. If this
        flag is disabled for a setter function then no response is send and
        errors are silently ignored, because they cannot be detected.
        """

        if function_id < 0 or function_id >= len(self.response_expected):
            raise ValueError('Function ID {0} out of range'.format(function_id))

        flag = self.response_expected[function_id]

        if flag == Device.RESPONSE_EXPECTED_INVALID_FUNCTION_ID:
            raise ValueError('Invalid function ID {0}'.format(function_id))

        return flag in [Device.RESPONSE_EXPECTED_ALWAYS_TRUE, Device.RESPONSE_EXPECTED_TRUE]

    def set_response_expected(self, function_id, response_expected):
        """
        Changes the response expected flag of the function specified by the
        *function_id* parameter. This flag can only be changed for setter
        (default value: *false*) and callback configuration functions
        (default value: *true*). For getter functions it is always enabled.

        Enabling the response expected flag for a setter function allows to
        detect timeouts and other error conditions calls of this setter as
        well. The device will then send a response for this purpose. If this
        flag is disabled for a setter function then no response is send and
        errors are silently ignored, because they cannot be detected.
        """

        if function_id < 0 or function_id >= len(self.response_expected):
            raise ValueError('Function ID {0} out of range'.format(function_id))

        flag = self.response_expected[function_id]

        if flag == Device.RESPONSE_EXPECTED_INVALID_FUNCTION_ID:
            raise ValueError('Invalid function ID {0}'.format(function_id))

        if flag == Device.RESPONSE_EXPECTED_ALWAYS_TRUE:
            raise ValueError('Response Expected flag cannot be changed for function ID {0}'.format(function_id))

        if bool(response_expected):
            self.response_expected[function_id] = Device.RESPONSE_EXPECTED_TRUE
        else:
            self.response_expected[function_id] = Device.RESPONSE_EXPECTED_FALSE

    def set_response_expected_all(self, response_expected):
        """
        Changes the response expected flag for all setter and callback
        configuration functions of this device at once.
        """

        if bool(response_expected):
            flag = Device.RESPONSE_EXPECTED_TRUE
        else:
            flag = Device.RESPONSE_EXPECTED_FALSE

        for i in range(len(self.response_expected)):
            if self.response_expected[i] in [Device.RESPONSE_EXPECTED_TRUE, Device.RESPONSE_EXPECTED_FALSE]:
                self.response_expected[i] = flag

class BrickDaemon(Device):
    FUNCTION_GET_AUTHENTICATION_NONCE = 1
    FUNCTION_AUTHENTICATE = 2

    def __init__(self, uid, ipcon):
        Device.__init__(self, uid, ipcon)

        self.api_version = (2, 0, 0)

        self.response_expected[BrickDaemon.FUNCTION_GET_AUTHENTICATION_NONCE] = BrickDaemon.RESPONSE_EXPECTED_ALWAYS_TRUE
        self.response_expected[BrickDaemon.FUNCTION_AUTHENTICATE] = BrickDaemon.RESPONSE_EXPECTED_TRUE

    def get_authentication_nonce(self):
        return self.ipcon.send_request(self, BrickDaemon.FUNCTION_GET_AUTHENTICATION_NONCE, (), '', '4B')

    def authenticate(self, client_nonce, digest):
        self.ipcon.send_request(self, BrickDaemon.FUNCTION_AUTHENTICATE, (client_nonce, digest), '4B 20B', '')

class IPConnection(object):
    FUNCTION_ENUMERATE = 254
    FUNCTION_ADC_CALIBRATE = 251
    FUNCTION_GET_ADC_CALIBRATION = 250
    FUNCTION_READ_BRICKLET_UID = 249
    FUNCTION_WRITE_BRICKLET_UID = 248
    FUNCTION_READ_BRICKLET_PLUGIN = 247
    FUNCTION_WRITE_BRICKLET_PLUGIN = 246
    FUNCTION_DISCONNECT_PROBE = 128

    CALLBACK_ENUMERATE = 253
    CALLBACK_CONNECTED = 0
    CALLBACK_DISCONNECTED = 1

    BROADCAST_UID = 0

    PLUGIN_CHUNK_SIZE = 32

    # enumeration_type parameter to the enumerate callback
    ENUMERATION_TYPE_AVAILABLE = 0
    ENUMERATION_TYPE_CONNECTED = 1
    ENUMERATION_TYPE_DISCONNECTED = 2

    # connect_reason parameter to the connected callback
    CONNECT_REASON_REQUEST = 0
    CONNECT_REASON_AUTO_RECONNECT = 1

    # disconnect_reason parameter to the disconnected callback
    DISCONNECT_REASON_REQUEST = 0
    DISCONNECT_REASON_ERROR = 1
    DISCONNECT_REASON_SHUTDOWN = 2

    # returned by get_connection_state
    CONNECTION_STATE_DISCONNECTED = 0
    CONNECTION_STATE_CONNECTED = 1
    CONNECTION_STATE_PENDING = 2 # auto-reconnect in process

    QUEUE_EXIT = 0
    QUEUE_META = 1
    QUEUE_PACKET = 2

    DISCONNECT_PROBE_INTERVAL = 5

    class CallbackContext(object):
        def __init__(self):
            self.queue = None
            self.thread = None
            self.packet_dispatch_allowed = False
            self.lock = None

    def __init__(self):
        """
        Creates an IP Connection object that can be used to enumerate the available
        devices. It is also required for the constructor of Bricks and Bricklets.
        """

        self.host = None
        self.port = None
        self.timeout = 2.5
        self.auto_reconnect = True
        self.auto_reconnect_allowed = False
        self.auto_reconnect_pending = False
        self.auto_reconnect_internal = False
        self.connect_failure_callback = None
        self.sequence_number_lock = threading.Lock()
        self.next_sequence_number = 0 # protected by sequence_number_lock
        self.authentication_lock = threading.Lock() # protects authentication handshake
        self.next_authentication_nonce = 0 # protected by authentication_lock
        self.devices = {}
        self.registered_callbacks = {}
        self.socket = None # protected by socket_lock
        self.socket_id = 0 # protected by socket_lock
        self.socket_lock = threading.Lock()
        self.socket_send_lock = threading.Lock()
        self.receive_flag = False
        self.receive_thread = None
        self.callback = None
        self.disconnect_probe_flag = False
        self.disconnect_probe_queue = None
        self.disconnect_probe_thread = None
        self.waiter = threading.Semaphore()
        self.brickd = BrickDaemon('2', self)

    def connect(self, host, port):
        """
        Creates a TCP/IP connection to the given *host* and *port*. The host
        and port can point to a Brick Daemon or to a WIFI/Ethernet Extension.

        Devices can only be controlled when the connection was established
        successfully.

        Blocks until the connection is established and throws an exception if
        there is no Brick Daemon or WIFI/Ethernet Extension listening at the
        given host and port.
        """

        with self.socket_lock:
            if self.socket is not None:
                raise Error(Error.ALREADY_CONNECTED,
                            'Already connected to {0}:{1}'.format(self.host, self.port))

            self.host = host
            self.port = port

            self.connect_unlocked(False)

    def disconnect(self):
        """
        Disconnects the TCP/IP connection from the Brick Daemon or the
        WIFI/Ethernet Extension.
        """

        with self.socket_lock:
            self.auto_reconnect_allowed = False

            if self.auto_reconnect_pending:
                # abort potentially pending auto reconnect
                self.auto_reconnect_pending = False
            else:
                if self.socket is None:
                    raise Error(Error.NOT_CONNECTED, 'Not connected')

                self.disconnect_unlocked()

            # end callback thread
            callback = self.callback
            self.callback = None

        # do this outside of socket_lock to allow calling (dis-)connect from
        # the callbacks while blocking on the join call here
        callback.queue.put((IPConnection.QUEUE_META,
                            (IPConnection.CALLBACK_DISCONNECTED,
                             IPConnection.DISCONNECT_REASON_REQUEST, None)))
        callback.queue.put((IPConnection.QUEUE_EXIT, None))

        if threading.current_thread() is not callback.thread:
            callback.thread.join()

    def authenticate(self, secret):
        """
        Performs an authentication handshake with the connected Brick Daemon or
        WIFI/Ethernet Extension. If the handshake succeeds the connection switches
        from non-authenticated to authenticated state and communication can
        continue as normal. If the handshake fails then the connection gets closed.
        Authentication can fail if the wrong secret was used or if authentication
        is not enabled at all on the Brick Daemon or the WIFI/Ethernet Extension.

        For more information about authentication see
        https://www.tinkerforge.com/en/doc/Tutorials/Tutorial_Authentication/Tutorial.html
        """

        try:
            secret_bytes = secret.encode('ascii')
        except UnicodeEncodeError:
            raise Error(Error.NON_ASCII_CHAR_IN_SECRET, 'Authentication secret contains non-ASCII characters')

        with self.authentication_lock:
            if self.next_authentication_nonce == 0:
                try:
                    self.next_authentication_nonce = struct.unpack('<I', os.urandom(4))[0]
                except NotImplementedError:
                    subseconds, seconds = math.modf(time.time())
                    seconds = int(seconds)
                    subseconds = int(subseconds * 1000000)
                    self.next_authentication_nonce = ((seconds << 26 | seconds >> 6) & 0xFFFFFFFF) + subseconds + os.getpid()

            server_nonce = self.brickd.get_authentication_nonce()
            client_nonce = struct.unpack('<4B', struct.pack('<I', self.next_authentication_nonce))
            self.next_authentication_nonce = (self.next_authentication_nonce + 1) % (1 << 32)

            h = hmac.new(secret_bytes, digestmod=hashlib.sha1)

            h.update(struct.pack('<4B', *server_nonce))
            h.update(struct.pack('<4B', *client_nonce))

            digest = struct.unpack('<20B', h.digest())
            h = None

            self.brickd.authenticate(client_nonce, digest)

    def get_connection_state(self):
        """
        Can return the following states:

        - CONNECTION_STATE_DISCONNECTED: No connection is established.
        - CONNECTION_STATE_CONNECTED: A connection to the Brick Daemon or
          the WIFI/Ethernet Extension is established.
        - CONNECTION_STATE_PENDING: IP Connection is currently trying to
          connect.
        """

        if self.socket is not None:
            return IPConnection.CONNECTION_STATE_CONNECTED
        elif self.auto_reconnect_pending:
            return IPConnection.CONNECTION_STATE_PENDING
        else:
            return IPConnection.CONNECTION_STATE_DISCONNECTED

    def set_auto_reconnect(self, auto_reconnect):
        """
        Enables or disables auto-reconnect. If auto-reconnect is enabled,
        the IP Connection will try to reconnect to the previously given
        host and port, if the connection is lost.

        Default value is *True*.
        """

        self.auto_reconnect = bool(auto_reconnect)

        if not self.auto_reconnect:
            # abort potentially pending auto reconnect
            self.auto_reconnect_allowed = False

    def get_auto_reconnect(self):
        """
        Returns *true* if auto-reconnect is enabled, *false* otherwise.
        """

        return self.auto_reconnect

    def set_timeout(self, timeout):
        """
        Sets the timeout in seconds for getters and for setters for which the
        response expected flag is activated.

        Default timeout is 2.5.
        """

        timeout = float(timeout)

        if timeout < 0:
            raise ValueError('Timeout cannot be negative')

        self.timeout = timeout

    def get_timeout(self):
        """
        Returns the timeout as set by set_timeout.
        """

        return self.timeout

    def enumerate(self):

        print("enumerate")

        """
        Broadcasts an enumerate request. All devices will respond with an
        enumerate callback.
        """

        request, _, _ = self.create_packet_header(None, 8, IPConnection.FUNCTION_ENUMERATE)

        self.send(request)

    def wait(self):
        """
        Stops the current thread until unwait is called.

        This is useful if you rely solely on callbacks for events, if you want
        to wait for a specific callback or if the IP Connection was created in
        a thread.

        Wait and unwait act in the same way as "acquire" and "release" of a
        semaphore.
        """
        self.waiter.acquire()

    def unwait(self):
        """
        Unwaits the thread previously stopped by wait.

        Wait and unwait act in the same way as "acquire" and "release" of
        a semaphore.
        """
        self.waiter.release()

    def register_callback(self, callback_id, function):
        """
        Registers the given *function* with the given *callback_id*.
        """
        if function is None:
            self.registered_callbacks.pop(callback_id, None)
        else:
            self.registered_callbacks[callback_id] = function

    def connect_unlocked(self, is_auto_reconnect):
        # NOTE: assumes that socket is None and socket_lock is locked

        # create callback thread and queue
        if self.callback is None:
            try:
                self.callback = IPConnection.CallbackContext()
                self.callback.queue = queue.Queue()
                self.callback.packet_dispatch_allowed = False
                self.callback.lock = threading.Lock()
                self.callback.thread = threading.Thread(name='Callback-Processor',
                                                        target=self.callback_loop,
                                                        args=(self.callback,))
                self.callback.thread.daemon = True
                self.callback.thread.start()
            except:
                self.callback = None
                raise

        # create and connect socket
        try:
            tmp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            tmp.settimeout(5)
            tmp.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            tmp.connect((self.host, self.port))

            if sys.platform == 'win32':
                # for some unknown reason the socket recv() call does not
                # immediate return on Windows if the socket gets shut down on
                # disconnect. the socket recv() call will still block for
                # several seconds before it returns. this in turn blocks the
                # disconnect. to workaround this use a 100ms timeout for
                # blocking socket operations.
                tmp.settimeout(0.1)
            else:
                tmp.settimeout(None)
        except Exception as e:
            def cleanup1():
                if self.auto_reconnect_internal:
                    if is_auto_reconnect:
                        return

                    if self.connect_failure_callback is not None:
                        self.connect_failure_callback(e)

                    self.auto_reconnect_allowed = True

                    # FIXME: don't misuse disconnected-callback here to trigger an auto-reconnect
                    #        because not actual connection has been established yet
                    self.callback.queue.put((IPConnection.QUEUE_META,
                                             (IPConnection.CALLBACK_DISCONNECTED,
                                              IPConnection.DISCONNECT_REASON_ERROR, None)))
                else:
                    # end callback thread
                    if not is_auto_reconnect:
                        self.callback.queue.put((IPConnection.QUEUE_EXIT, None))

                        if threading.current_thread() is not self.callback.thread:
                            self.callback.thread.join()

                        self.callback = None

            cleanup1()
            raise

        self.socket = tmp
        self.socket_id += 1

        # create disconnect probe thread
        try:
            self.disconnect_probe_flag = True
            self.disconnect_probe_queue = queue.Queue()
            self.disconnect_probe_thread = threading.Thread(name='Disconnect-Prober',
                                                            target=self.disconnect_probe_loop,
                                                            args=(self.disconnect_probe_queue,))
            self.disconnect_probe_thread.daemon = True
            self.disconnect_probe_thread.start()
        except:
            def cleanup2():
                self.disconnect_probe_thread = None

                # close socket
                self.socket.close()
                self.socket = None

                # end callback thread
                if not is_auto_reconnect:
                    self.callback.queue.put((IPConnection.QUEUE_EXIT, None))

                    if threading.current_thread() is not self.callback.thread:
                        self.callback.thread.join()

                    self.callback = None

            cleanup2()
            raise

        # create receive thread
        self.callback.packet_dispatch_allowed = True

        try:
            self.receive_flag = True
            self.receive_thread = threading.Thread(name='Brickd-Receiver',
                                                   target=self.receive_loop,
                                                   args=(self.socket_id,))
            self.receive_thread.daemon = True
            self.receive_thread.start()
        except:
            def cleanup3():
                self.receive_thread = None

                # close socket
                self.disconnect_unlocked()

                # end callback thread
                if not is_auto_reconnect:
                    self.callback.queue.put((IPConnection.QUEUE_EXIT, None))

                    if threading.current_thread() is not self.callback.thread:
                        self.callback.thread.join()

                    self.callback = None

            cleanup3()
            raise

        self.auto_reconnect_allowed = False
        self.auto_reconnect_pending = False

        if is_auto_reconnect:
            connect_reason = IPConnection.CONNECT_REASON_AUTO_RECONNECT
        else:
            connect_reason = IPConnection.CONNECT_REASON_REQUEST

        self.callback.queue.put((IPConnection.QUEUE_META,
                                 (IPConnection.CALLBACK_CONNECTED,
                                  connect_reason, None)))

    def disconnect_unlocked(self):
        # NOTE: assumes that socket is not None and socket_lock is locked

        # end disconnect probe thread
        self.disconnect_probe_queue.put(True)
        self.disconnect_probe_thread.join() # FIXME: use a timeout?
        self.disconnect_probe_thread = None

        # stop dispatching packet callbacks before ending the receive
        # thread to avoid timeout exceptions due to callback functions
        # trying to call getters
        if threading.current_thread() is not self.callback.thread:
            # FIXME: cannot hold callback lock here because this can
            #        deadlock due to an ordering problem with the socket lock
            #with self.callback.lock:
            if True:
                self.callback.packet_dispatch_allowed = False
        else:
            self.callback.packet_dispatch_allowed = False

        # end receive thread
        self.receive_flag = False

        try:
            self.socket.shutdown(socket.SHUT_RDWR)
        except socket.error:
            pass

        if self.receive_thread is not None:
            self.receive_thread.join() # FIXME: use a timeout?
            self.receive_thread = None

        # close socket
        self.socket.close()
        self.socket = None

    def set_auto_reconnect_internal(self, auto_reconnect, connect_failure_callback):
        self.auto_reconnect_internal = auto_reconnect
        self.connect_failure_callback = connect_failure_callback

    def receive_loop(self, socket_id):
        if sys.hexversion < 0x03000000:
            pending_data = ''
        else:
            pending_data = bytes()

        while self.receive_flag:
            try:
                data = self.socket.recv(8192)
            except socket.timeout:
                continue
            except socket.error:
                if self.receive_flag:
                    e = sys.exc_info()[1]
                    if e.errno == errno.EINTR:
                        continue

                    self.handle_disconnect_by_peer(IPConnection.DISCONNECT_REASON_ERROR, socket_id, False)
                break

            if len(data) == 0:
                if self.receive_flag:
                    self.handle_disconnect_by_peer(IPConnection.DISCONNECT_REASON_SHUTDOWN, socket_id, False)
                break

            pending_data += data

            while self.receive_flag:
                if len(pending_data) < 8:
                    # Wait for complete header
                    break

                length = get_length_from_data(pending_data)

                if len(pending_data) < length:
                    # Wait for complete packet
                    break

                packet = pending_data[0:length]
                pending_data = pending_data[length:]

                self.handle_response(packet)

    def dispatch_meta(self, function_id, parameter, socket_id):
        if function_id == IPConnection.CALLBACK_CONNECTED:
            if IPConnection.CALLBACK_CONNECTED in self.registered_callbacks:
                self.registered_callbacks[IPConnection.CALLBACK_CONNECTED](parameter)
        elif function_id == IPConnection.CALLBACK_DISCONNECTED:
            if parameter != IPConnection.DISCONNECT_REASON_REQUEST:
                # need to do this here, the receive_loop is not allowed to
                # hold the socket_lock because this could cause a deadlock
                # with a concurrent call to the (dis-)connect function
                with self.socket_lock:
                    # don't close the socket if it got disconnected or
                    # reconnected in the meantime
                    if self.socket is not None and self.socket_id == socket_id:
                        # end disconnect probe thread
                        self.disconnect_probe_queue.put(True)
                        self.disconnect_probe_thread.join() # FIXME: use a timeout?
                        self.disconnect_probe_thread = None

                        # close socket
                        self.socket.close()
                        self.socket = None

            # FIXME: wait a moment here, otherwise the next connect
            # attempt will succeed, even if there is no open server
            # socket. the first receive will then fail directly
            time.sleep(0.1)

            if IPConnection.CALLBACK_DISCONNECTED in self.registered_callbacks:
                self.registered_callbacks[IPConnection.CALLBACK_DISCONNECTED](parameter)

            if parameter != IPConnection.DISCONNECT_REASON_REQUEST and \
               self.auto_reconnect and self.auto_reconnect_allowed:
                self.auto_reconnect_pending = True
                retry = True

                # block here until reconnect. this is okay, there is no
                # callback to deliver when there is no connection
                while retry:
                    retry = False

                    with self.socket_lock:
                        if self.auto_reconnect_allowed and self.socket is None:
                            try:
                                self.connect_unlocked(True)
                            except:
                                retry = True
                        else:
                            self.auto_reconnect_pending = False

                    if retry:
                        time.sleep(0.1)

    def dispatch_packet(self, packet):
        uid = get_uid_from_data(packet)
        length = get_length_from_data(packet)
        function_id = get_function_id_from_data(packet)
        payload = packet[8:]

        if function_id == IPConnection.CALLBACK_ENUMERATE and \
           IPConnection.CALLBACK_ENUMERATE in self.registered_callbacks:
            uid, connected_uid, position, hardware_version, \
                firmware_version, device_identifier, enumeration_type = \
                unpack_payload(payload, '8s 8s c 3B 3B H B')

            cb = self.registered_callbacks[IPConnection.CALLBACK_ENUMERATE]
            cb(uid, connected_uid, position, hardware_version,
               firmware_version, device_identifier, enumeration_type)
            return

        if uid not in self.devices:
            return

        device = self.devices[uid]

        if -function_id in device.high_level_callbacks:
            hlcb = device.high_level_callbacks[-function_id] # [roles, options, data]
            form = device.callback_formats[function_id] # FIXME: currently assuming that form is longer than 1
            llvalues = unpack_payload(payload, form)
            has_data = False
            data = None

            if hlcb[1]['fixed_length'] != None:
                length = hlcb[1]['fixed_length']
            else:
                length = llvalues[hlcb[0].index('stream_length')]

            if not hlcb[1]['single_chunk']:
                chunk_offset = llvalues[hlcb[0].index('stream_chunk_offset')]
            else:
                chunk_offset = 0

            chunk_data = llvalues[hlcb[0].index('stream_chunk_data')]

            if hlcb[2] == None: # no stream in-progress
                if chunk_offset == 0: # stream starts
                    hlcb[2] = chunk_data

                    if len(hlcb[2]) >= length: # stream complete
                        has_data = True
                        data = hlcb[2][:length]
                        hlcb[2] = None
                else: # ignore tail of current stream, wait for next stream start
                    pass
            else: # stream in-progress
                if chunk_offset != len(hlcb[2]): # stream out-of-sync
                    has_data = True
                    data = None
                    hlcb[2] = None
                else: # stream in-sync
                    hlcb[2] += chunk_data

                    if len(hlcb[2]) >= length: # stream complete
                        has_data = True
                        data = hlcb[2][:length]
                        hlcb[2] = None

            if has_data and -function_id in device.registered_callbacks:
                result = []

                for role, llvalue in zip(hlcb[0], llvalues):
                    if role == 'stream_chunk_data':
                        result.append(data)
                    elif role == None:
                        result.append(llvalue)

                device.registered_callbacks[-function_id](*tuple(result))

        if function_id in device.registered_callbacks:
            cb = device.registered_callbacks[function_id]
            form = device.callback_formats[function_id]

            if len(form) == 0:
                cb()
            elif len(form.split(' ')) == 1:
                cb(unpack_payload(payload, form))
            else:
                cb(*unpack_payload(payload, form))

    def callback_loop(self, callback):
        while True:
            kind, data = callback.queue.get()

            # FIXME: cannot hold callback lock here because this can
            #        deadlock due to an ordering problem with the socket lock
            #with callback.lock:
            if True:
                if kind == IPConnection.QUEUE_EXIT:
                    break
                elif kind == IPConnection.QUEUE_META:
                    self.dispatch_meta(*data)
                elif kind == IPConnection.QUEUE_PACKET:
                    # don't dispatch callbacks when the receive thread isn't running
                    if callback.packet_dispatch_allowed:
                        self.dispatch_packet(data)

    # NOTE: the disconnect probe thread is not allowed to hold the socket_lock at any
    #       time because it is created and joined while the socket_lock is locked
    def disconnect_probe_loop(self, disconnect_probe_queue):
        request, _, _ = self.create_packet_header(None, 8, IPConnection.FUNCTION_DISCONNECT_PROBE)

        while True:
            try:
                disconnect_probe_queue.get(True, IPConnection.DISCONNECT_PROBE_INTERVAL)
                break
            except queue.Empty:
                pass

            if self.disconnect_probe_flag:
                try:
                    with self.socket_send_lock:
                        while True:
                            try:
                                self.socket.send(request)
                                break
                            except socket.timeout:
                                continue
                except socket.error:
                    self.handle_disconnect_by_peer(IPConnection.DISCONNECT_REASON_ERROR,
                                                   self.socket_id, False)
                    break
            else:
                self.disconnect_probe_flag = True

    def send(self, packet):
        with self.socket_lock:
            if self.socket is None:
                raise Error(Error.NOT_CONNECTED, 'Not connected')

            try:
                with self.socket_send_lock:
                    while True:
                        try:
                            self.socket.send(packet)
                            break
                        except socket.timeout:
                            continue
            except socket.error:
                self.handle_disconnect_by_peer(IPConnection.DISCONNECT_REASON_ERROR, None, True)
                raise Error(Error.NOT_CONNECTED, 'Not connected', suppress_context=True)

            self.disconnect_probe_flag = False

    def send_request(self, device, function_id, data, form, form_ret):
        patched_from = []

        for f in form.split(' '):
            if '!' in f:
                if len(f) > 1:
                    patched_from.append('{0}B'.format(int(math.ceil(int(f.replace('!', '')) / 8.0))))
                else:
                    patched_from.append('?')
            else:
                patched_from.append(f)

        patched_from = '<' + ' '.join(patched_from)
        length = 8 + struct.calcsize(patched_from)
        request, response_expected, sequence_number = \
            self.create_packet_header(device, length, function_id)

        request += pack_payload(data, form)

        if response_expected:
            with device.request_lock:
                device.expected_response_function_id = function_id
                device.expected_response_sequence_number = sequence_number

                try:
                    self.send(request)

                    while True:
                        response = device.response_queue.get(True, self.timeout)

                        if function_id == get_function_id_from_data(response) and \
                           sequence_number == get_sequence_number_from_data(response):
                            # ignore old responses that arrived after the timeout expired, but before setting
                            # expected_response_function_id and expected_response_sequence_number back to None
                            break
                except queue.Empty:
                    msg = 'Did not receive response for function {0} in time'.format(function_id)
                    raise Error(Error.TIMEOUT, msg, suppress_context=True)
                finally:
                    device.expected_response_function_id = None
                    device.expected_response_sequence_number = None

            error_code = get_error_code_from_data(response)

            if error_code == 0:
                # no error
                pass
            elif error_code == 1:
                msg = 'Got invalid parameter for function {0}'.format(function_id)
                raise Error(Error.INVALID_PARAMETER, msg)
            elif error_code == 2:
                msg = 'Function {0} is not supported'.format(function_id)
                raise Error(Error.NOT_SUPPORTED, msg)
            else:
                msg = 'Function {0} returned an unknown error'.format(function_id)
                raise Error(Error.UNKNOWN_ERROR_CODE, msg)

            if len(form_ret) > 0:
                return unpack_payload(response[8:], form_ret)
        else:
            self.send(request)

    def get_next_sequence_number(self):
        with self.sequence_number_lock:
            sequence_number = self.next_sequence_number + 1
            self.next_sequence_number = sequence_number % 15
            return sequence_number

    def handle_response(self, packet):
        self.disconnect_probe_flag = False

        function_id = get_function_id_from_data(packet)
        sequence_number = get_sequence_number_from_data(packet)

        if sequence_number == 0 and function_id == IPConnection.CALLBACK_ENUMERATE:
            if IPConnection.CALLBACK_ENUMERATE in self.registered_callbacks:
                self.callback.queue.put((IPConnection.QUEUE_PACKET, packet))
            return

        uid = get_uid_from_data(packet)

        if not uid in self.devices:
            # Response from an unknown device, ignoring it
            return

        device = self.devices[uid]

        if sequence_number == 0:
            if function_id in device.registered_callbacks or \
               -function_id in device.high_level_callbacks:
                self.callback.queue.put((IPConnection.QUEUE_PACKET, packet))
            return

        if device.expected_response_function_id == function_id and \
           device.expected_response_sequence_number == sequence_number:
            device.response_queue.put(packet)
            return

        # Response seems to be OK, but can't be handled

    def handle_disconnect_by_peer(self, disconnect_reason, socket_id, disconnect_immediately):
        # NOTE: assumes that socket_lock is locked if disconnect_immediately is true

        self.auto_reconnect_allowed = True

        if disconnect_immediately:
            self.disconnect_unlocked()

        self.callback.queue.put((IPConnection.QUEUE_META,
                                 (IPConnection.CALLBACK_DISCONNECTED,
                                  disconnect_reason, socket_id)))

    def create_packet_header(self, device, length, function_id):
        uid = IPConnection.BROADCAST_UID
        sequence_number = self.get_next_sequence_number()
        r_bit = 0

        if device is not None:
            uid = device.uid

            if device.get_response_expected(function_id):
                r_bit = 1

        sequence_number_and_options = (sequence_number << 4) | (r_bit << 3)

        return (struct.pack('<IBBBB', uid, length, function_id,
                            sequence_number_and_options, 0),
                bool(r_bit),
                sequence_number)

    def write_bricklet_plugin(self, device, port, position, plugin_chunk):
        self.send_request(device,
                          IPConnection.FUNCTION_WRITE_BRICKLET_PLUGIN,
                          (port, position, plugin_chunk),
                          'c B 32B',
                          '')

    def read_bricklet_plugin(self, device, port, position):
        return self.send_request(device,
                                 IPConnection.FUNCTION_READ_BRICKLET_PLUGIN,
                                 (port, position),
                                 'c B',
                                 '32B')

    def get_adc_calibration(self, device):
        return self.send_request(device,
                                 IPConnection.FUNCTION_GET_ADC_CALIBRATION,
                                 (),
                                 '',
                                 'h h')

    def adc_calibrate(self, device, port):
        self.send_request(device,
                          IPConnection.FUNCTION_ADC_CALIBRATE,
                          (port,),
                          'c',
                          '')

    def write_bricklet_uid(self, device, port, uid):
        uid_int = base58decode(uid)

        self.send_request(device,
                          IPConnection.FUNCTION_WRITE_BRICKLET_UID,
                          (port, uid_int),
                          'c I',
                          '')

    def read_bricklet_uid(self, device, port):
        uid_int = self.send_request(device,
                                    IPConnection.FUNCTION_READ_BRICKLET_UID,
                                    (port,),
                                    'c',
                                    'I')

        return base58encode(uid_int)



class MQTTCallbackDevice(Device):
    def __init__(self, uid, ipcon, device_class, mqttc):
        Device.__init__(self, uid, ipcon)
        self.publish_paths = {}
        self.callback_names = {}
        self.callback_symbols = {}
        self.device_class = device_class
        self.mqttc = mqttc

    def add_callback(self, callback_id, callback_format, callback_names, callback_symbols, high_level_info):
        self.callback_formats[callback_id] = callback_format
        self.callback_names[callback_id] = callback_names
        self.callback_symbols[callback_id] = callback_symbols
        if high_level_info is not None:
            self.high_level_callbacks[-callback_id] = high_level_info


    def register_callback(self, bindings, callback_id, path):
        if -callback_id in self.high_level_callbacks:
            cid = -callback_id
        else:
            cid = callback_id

        if callback_id not in self.publish_paths:
            self.publish_paths[callback_id] = set()

        self.publish_paths[callback_id].add(path)
        self.registered_callbacks[cid] = lambda *args: bindings.callback_function(self, callback_id, *args)

    def deregister_callback(self, callback_id, path):
        if callback_id not in self.publish_paths:
            logging.debug("Got callback deregistration request, but no registration for topic {} was found. Ignoring the request.".format(path))
            return False
        self.publish_paths[callback_id].discard(path)
        if len(self.publish_paths[callback_id]) == 0:
            self.publish_paths.pop(callback_id)
            self.callback_names.pop(callback_id)
            self.callback_symbols.pop(callback_id)
            self.registered_callbacks.pop(callback_id, None)
        return True




class AccelerometerBricklet(MQTTCallbackDevice):
	functions = {
		'get_acceleration': FunctionInfo(1, [], [], [], '', ['x', 'y', 'z'], [{}, {}, {}], 'h h h'),
		'set_acceleration_callback_period': FunctionInfo(2, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_acceleration_callback_period': FunctionInfo(3, [], [], [], '', ['period'], [{}], 'I'),
		'set_acceleration_callback_threshold': FunctionInfo(4, ['option', 'min_x', 'max_x', 'min_y', 'max_y', 'min_z', 'max_z'], ['char', 'int', 'int', 'int', 'int', 'int', 'int'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}, {}, {}, {}, {}], 'c h h h h h h', [], [], ''),
		'get_acceleration_callback_threshold': FunctionInfo(5, [], [], [], '', ['option', 'min_x', 'max_x', 'min_y', 'max_y', 'min_z', 'max_z'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}, {}, {}, {}, {}], 'c h h h h h h'),
		'set_debounce_period': FunctionInfo(6, ['debounce'], ['int'], [{}], 'I', [], [], ''),
		'get_debounce_period': FunctionInfo(7, [], [], [], '', ['debounce'], [{}], 'I'),
		'get_temperature': FunctionInfo(8, [], [], [], '', ['temperature'], [{}], 'h'),
		'set_configuration': FunctionInfo(9, ['data_rate', 'full_scale', 'filter_bandwidth'], ['int', 'int', 'int'], [{0: 'off', 1: '3hz', 2: '6hz', 3: '12hz', 4: '25hz', 5: '50hz', 6: '100hz', 7: '400hz', 8: '800hz', 9: '1600hz'}, {0: '2g', 1: '4g', 2: '6g', 3: '8g', 4: '16g'}, {0: '800hz', 1: '400hz', 2: '200hz', 3: '50hz'}], 'B B B', [], [], ''),
		'get_configuration': FunctionInfo(10, [], [], [], '', ['data_rate', 'full_scale', 'filter_bandwidth'], [{0: 'off', 1: '3hz', 2: '6hz', 3: '12hz', 4: '25hz', 5: '50hz', 6: '100hz', 7: '400hz', 8: '800hz', 9: '1600hz'}, {0: '2g', 1: '4g', 2: '6g', 3: '8g', 4: '16g'}, {0: '800hz', 1: '400hz', 2: '200hz', 3: '50hz'}], 'B B B'),
		'led_on': FunctionInfo(11, [], [], [], '', [], [], ''),
		'led_off': FunctionInfo(12, [], [], [], '', [], [], ''),
		'is_led_on': FunctionInfo(13, [], [], [], '', ['on'], [{}], '!'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'acceleration': CallbackInfo(14, ['x', 'y', 'z'], [{}, {}, {}], 'h h h', None),
		'acceleration_reached': CallbackInfo(15, ['x', 'y', 'z'], [{}, {}, {}], 'h h h', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 2; re[3] = 1; re[4] = 2; re[5] = 1; re[6] = 2; re[7] = 1; re[8] = 1; re[9] = 3; re[10] = 1; re[11] = 3; re[12] = 3; re[13] = 1; re[255] = 1

class AccelerometerV2Bricklet(MQTTCallbackDevice):
	functions = {
		'get_acceleration': FunctionInfo(1, [], [], [], '', ['x', 'y', 'z'], [{}, {}, {}], 'i i i'),
		'set_configuration': FunctionInfo(2, ['data_rate', 'full_scale'], ['int', 'int'], [{0: '0_781hz', 1: '1_563hz', 2: '3_125hz', 3: '6_2512hz', 4: '12_5hz', 5: '25hz', 6: '50hz', 7: '100hz', 8: '200hz', 9: '400hz', 10: '800hz', 11: '1600hz', 12: '3200hz', 13: '6400hz', 14: '12800hz', 15: '25600hz'}, {0: '2g', 1: '4g', 2: '8g'}], 'B B', [], [], ''),
		'get_configuration': FunctionInfo(3, [], [], [], '', ['data_rate', 'full_scale'], [{0: '0_781hz', 1: '1_563hz', 2: '3_125hz', 3: '6_2512hz', 4: '12_5hz', 5: '25hz', 6: '50hz', 7: '100hz', 8: '200hz', 9: '400hz', 10: '800hz', 11: '1600hz', 12: '3200hz', 13: '6400hz', 14: '12800hz', 15: '25600hz'}, {0: '2g', 1: '4g', 2: '8g'}], 'B B'),
		'set_acceleration_callback_configuration': FunctionInfo(4, ['period', 'value_has_to_change'], ['int', 'bool'], [{}, {}], 'I !', [], [], ''),
		'get_acceleration_callback_configuration': FunctionInfo(5, [], [], [], '', ['period', 'value_has_to_change'], [{}, {}], 'I !'),
		'set_info_led_config': FunctionInfo(6, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat'}], 'B', [], [], ''),
		'get_info_led_config': FunctionInfo(7, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat'}], 'B'),
		'set_continuous_acceleration_configuration': FunctionInfo(9, ['enable_x', 'enable_y', 'enable_z', 'resolution'], ['bool', 'bool', 'bool', 'int'], [{}, {}, {}, {0: '8bit', 1: '16bit'}], '! ! ! B', [], [], ''),
		'get_continuous_acceleration_configuration': FunctionInfo(10, [], [], [], '', ['enable_x', 'enable_y', 'enable_z', 'resolution'], [{}, {}, {}, {0: '8bit', 1: '16bit'}], '! ! ! B'),
		'set_filter_configuration': FunctionInfo(13, ['iir_bypass', 'low_pass_filter'], ['int', 'int'], [{0: 'applied', 1: 'bypassed'}, {0: 'ninth', 1: 'half'}], 'B B', [], [], ''),
		'get_filter_configuration': FunctionInfo(14, [], [], [], '', ['iir_bypass', 'low_pass_filter'], [{0: 'applied', 1: 'bypassed'}, {0: 'ninth', 1: 'half'}], 'B B'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'acceleration': CallbackInfo(8, ['x', 'y', 'z'], [{}, {}, {}], 'i i i', None),
		'continuous_acceleration_16_bit': CallbackInfo(11, ['acceleration'], [{}], '30h', None),
		'continuous_acceleration_8_bit': CallbackInfo(12, ['acceleration'], [{}], '60b', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 3; re[3] = 1; re[4] = 2; re[5] = 1; re[6] = 3; re[7] = 1; re[9] = 3; re[10] = 1; re[13] = 3; re[14] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class AirQualityBricklet(MQTTCallbackDevice):
	functions = {
		'get_all_values': FunctionInfo(1, [], [], [], '', ['iaq_index', 'iaq_index_accuracy', 'temperature', 'humidity', 'air_pressure'], [{}, {0: 'unreliable', 1: 'low', 2: 'medium', 3: 'high'}, {}, {}, {}], 'i B i i i'),
		'set_temperature_offset': FunctionInfo(2, ['offset'], ['int'], [{}], 'i', [], [], ''),
		'get_temperature_offset': FunctionInfo(3, [], [], [], '', ['offset'], [{}], 'i'),
		'set_all_values_callback_configuration': FunctionInfo(4, ['period', 'value_has_to_change'], ['int', 'bool'], [{}, {}], 'I !', [], [], ''),
		'get_all_values_callback_configuration': FunctionInfo(5, [], [], [], '', ['period', 'value_has_to_change'], [{}, {}], 'I !'),
		'get_iaq_index': FunctionInfo(7, [], [], [], '', ['iaq_index', 'iaq_index_accuracy'], [{}, {0: 'unreliable', 1: 'low', 2: 'medium', 3: 'high'}], 'i B'),
		'set_iaq_index_callback_configuration': FunctionInfo(8, ['period', 'value_has_to_change'], ['int', 'bool'], [{}, {}], 'I !', [], [], ''),
		'get_iaq_index_callback_configuration': FunctionInfo(9, [], [], [], '', ['period', 'value_has_to_change'], [{}, {}], 'I !'),
		'get_temperature': FunctionInfo(11, [], [], [], '', ['temperature'], [{}], 'i'),
		'set_temperature_callback_configuration': FunctionInfo(12, ['period', 'value_has_to_change', 'option', 'min', 'max'], ['int', 'bool', 'char', 'int', 'int'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c i i', [], [], ''),
		'get_temperature_callback_configuration': FunctionInfo(13, [], [], [], '', ['period', 'value_has_to_change', 'option', 'min', 'max'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c i i'),
		'get_humidity': FunctionInfo(15, [], [], [], '', ['humidity'], [{}], 'i'),
		'set_humidity_callback_configuration': FunctionInfo(16, ['period', 'value_has_to_change', 'option', 'min', 'max'], ['int', 'bool', 'char', 'int', 'int'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c i i', [], [], ''),
		'get_humidity_callback_configuration': FunctionInfo(17, [], [], [], '', ['period', 'value_has_to_change', 'option', 'min', 'max'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c i i'),
		'get_air_pressure': FunctionInfo(19, [], [], [], '', ['air_pressure'], [{}], 'i'),
		'set_air_pressure_callback_configuration': FunctionInfo(20, ['period', 'value_has_to_change', 'option', 'min', 'max'], ['int', 'bool', 'char', 'int', 'int'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c i i', [], [], ''),
		'get_air_pressure_callback_configuration': FunctionInfo(21, [], [], [], '', ['period', 'value_has_to_change', 'option', 'min', 'max'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c i i'),
		'remove_calibration': FunctionInfo(23, [], [], [], '', [], [], ''),
		'set_background_calibration_duration': FunctionInfo(24, ['duration'], ['int'], [{0: '4_days', 1: '28_days'}], 'B', [], [], ''),
		'get_background_calibration_duration': FunctionInfo(25, [], [], [], '', ['duration'], [{0: '4_days', 1: '28_days'}], 'B'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'all_values': CallbackInfo(6, ['iaq_index', 'iaq_index_accuracy', 'temperature', 'humidity', 'air_pressure'], [{}, {0: 'unreliable', 1: 'low', 2: 'medium', 3: 'high'}, {}, {}, {}], 'i B i i i', None),
		'iaq_index': CallbackInfo(10, ['iaq_index', 'iaq_index_accuracy'], [{}, {0: 'unreliable', 1: 'low', 2: 'medium', 3: 'high'}], 'i B', None),
		'temperature': CallbackInfo(14, ['temperature'], [{}], 'i', None),
		'humidity': CallbackInfo(18, ['humidity'], [{}], 'i', None),
		'air_pressure': CallbackInfo(22, ['air_pressure'], [{}], 'i', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 3; re[3] = 1; re[4] = 2; re[5] = 1; re[7] = 1; re[8] = 2; re[9] = 1; re[11] = 1; re[12] = 2; re[13] = 1; re[15] = 1; re[16] = 2; re[17] = 1; re[19] = 1; re[20] = 2; re[21] = 1; re[23] = 3; re[24] = 3; re[25] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class AmbientLightBricklet(MQTTCallbackDevice):
	functions = {
		'get_illuminance': FunctionInfo(1, [], [], [], '', ['illuminance'], [{}], 'H'),
		'get_analog_value': FunctionInfo(2, [], [], [], '', ['value'], [{}], 'H'),
		'set_illuminance_callback_period': FunctionInfo(3, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_illuminance_callback_period': FunctionInfo(4, [], [], [], '', ['period'], [{}], 'I'),
		'set_analog_value_callback_period': FunctionInfo(5, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_analog_value_callback_period': FunctionInfo(6, [], [], [], '', ['period'], [{}], 'I'),
		'set_illuminance_callback_threshold': FunctionInfo(7, ['option', 'min', 'max'], ['char', 'int', 'int'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c H H', [], [], ''),
		'get_illuminance_callback_threshold': FunctionInfo(8, [], [], [], '', ['option', 'min', 'max'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c H H'),
		'set_analog_value_callback_threshold': FunctionInfo(9, ['option', 'min', 'max'], ['char', 'int', 'int'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c H H', [], [], ''),
		'get_analog_value_callback_threshold': FunctionInfo(10, [], [], [], '', ['option', 'min', 'max'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c H H'),
		'set_debounce_period': FunctionInfo(11, ['debounce'], ['int'], [{}], 'I', [], [], ''),
		'get_debounce_period': FunctionInfo(12, [], [], [], '', ['debounce'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'illuminance': CallbackInfo(13, ['illuminance'], [{}], 'H', None),
		'analog_value': CallbackInfo(14, ['value'], [{}], 'H', None),
		'illuminance_reached': CallbackInfo(15, ['illuminance'], [{}], 'H', None),
		'analog_value_reached': CallbackInfo(16, ['value'], [{}], 'H', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 1; re[3] = 2; re[4] = 1; re[5] = 2; re[6] = 1; re[7] = 2; re[8] = 1; re[9] = 2; re[10] = 1; re[11] = 2; re[12] = 1; re[255] = 1

class AmbientLightV2Bricklet(MQTTCallbackDevice):
	functions = {
		'get_illuminance': FunctionInfo(1, [], [], [], '', ['illuminance'], [{}], 'I'),
		'set_illuminance_callback_period': FunctionInfo(2, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_illuminance_callback_period': FunctionInfo(3, [], [], [], '', ['period'], [{}], 'I'),
		'set_illuminance_callback_threshold': FunctionInfo(4, ['option', 'min', 'max'], ['char', 'int', 'int'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c I I', [], [], ''),
		'get_illuminance_callback_threshold': FunctionInfo(5, [], [], [], '', ['option', 'min', 'max'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c I I'),
		'set_debounce_period': FunctionInfo(6, ['debounce'], ['int'], [{}], 'I', [], [], ''),
		'get_debounce_period': FunctionInfo(7, [], [], [], '', ['debounce'], [{}], 'I'),
		'set_configuration': FunctionInfo(8, ['illuminance_range', 'integration_time'], ['int', 'int'], [{6: 'unlimited', 0: '64000lux', 1: '32000lux', 2: '16000lux', 3: '8000lux', 4: '1300lux', 5: '600lux'}, {0: '50ms', 1: '100ms', 2: '150ms', 3: '200ms', 4: '250ms', 5: '300ms', 6: '350ms', 7: '400ms'}], 'B B', [], [], ''),
		'get_configuration': FunctionInfo(9, [], [], [], '', ['illuminance_range', 'integration_time'], [{6: 'unlimited', 0: '64000lux', 1: '32000lux', 2: '16000lux', 3: '8000lux', 4: '1300lux', 5: '600lux'}, {0: '50ms', 1: '100ms', 2: '150ms', 3: '200ms', 4: '250ms', 5: '300ms', 6: '350ms', 7: '400ms'}], 'B B'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'illuminance': CallbackInfo(10, ['illuminance'], [{}], 'I', None),
		'illuminance_reached': CallbackInfo(11, ['illuminance'], [{}], 'I', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 2; re[3] = 1; re[4] = 2; re[5] = 1; re[6] = 2; re[7] = 1; re[8] = 3; re[9] = 1; re[255] = 1

class AmbientLightV3Bricklet(MQTTCallbackDevice):
	functions = {
		'get_illuminance': FunctionInfo(1, [], [], [], '', ['illuminance'], [{}], 'I'),
		'set_illuminance_callback_configuration': FunctionInfo(2, ['period', 'value_has_to_change', 'option', 'min', 'max'], ['int', 'bool', 'char', 'int', 'int'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c I I', [], [], ''),
		'get_illuminance_callback_configuration': FunctionInfo(3, [], [], [], '', ['period', 'value_has_to_change', 'option', 'min', 'max'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c I I'),
		'set_configuration': FunctionInfo(5, ['illuminance_range', 'integration_time'], ['int', 'int'], [{6: 'unlimited', 0: '64000lux', 1: '32000lux', 2: '16000lux', 3: '8000lux', 4: '1300lux', 5: '600lux'}, {0: '50ms', 1: '100ms', 2: '150ms', 3: '200ms', 4: '250ms', 5: '300ms', 6: '350ms', 7: '400ms'}], 'B B', [], [], ''),
		'get_configuration': FunctionInfo(6, [], [], [], '', ['illuminance_range', 'integration_time'], [{6: 'unlimited', 0: '64000lux', 1: '32000lux', 2: '16000lux', 3: '8000lux', 4: '1300lux', 5: '600lux'}, {0: '50ms', 1: '100ms', 2: '150ms', 3: '200ms', 4: '250ms', 5: '300ms', 6: '350ms', 7: '400ms'}], 'B B'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'illuminance': CallbackInfo(4, ['illuminance'], [{}], 'I', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 2; re[3] = 1; re[5] = 3; re[6] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class AnalogInBricklet(MQTTCallbackDevice):
	functions = {
		'get_voltage': FunctionInfo(1, [], [], [], '', ['voltage'], [{}], 'H'),
		'get_analog_value': FunctionInfo(2, [], [], [], '', ['value'], [{}], 'H'),
		'set_voltage_callback_period': FunctionInfo(3, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_voltage_callback_period': FunctionInfo(4, [], [], [], '', ['period'], [{}], 'I'),
		'set_analog_value_callback_period': FunctionInfo(5, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_analog_value_callback_period': FunctionInfo(6, [], [], [], '', ['period'], [{}], 'I'),
		'set_voltage_callback_threshold': FunctionInfo(7, ['option', 'min', 'max'], ['char', 'int', 'int'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c H H', [], [], ''),
		'get_voltage_callback_threshold': FunctionInfo(8, [], [], [], '', ['option', 'min', 'max'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c H H'),
		'set_analog_value_callback_threshold': FunctionInfo(9, ['option', 'min', 'max'], ['char', 'int', 'int'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c H H', [], [], ''),
		'get_analog_value_callback_threshold': FunctionInfo(10, [], [], [], '', ['option', 'min', 'max'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c H H'),
		'set_debounce_period': FunctionInfo(11, ['debounce'], ['int'], [{}], 'I', [], [], ''),
		'get_debounce_period': FunctionInfo(12, [], [], [], '', ['debounce'], [{}], 'I'),
		'set_range': FunctionInfo(17, ['range'], ['int'], [{0: 'automatic', 1: 'up_to_6v', 2: 'up_to_10v', 3: 'up_to_36v', 4: 'up_to_45v', 5: 'up_to_3v'}], 'B', [], [], ''),
		'get_range': FunctionInfo(18, [], [], [], '', ['range'], [{0: 'automatic', 1: 'up_to_6v', 2: 'up_to_10v', 3: 'up_to_36v', 4: 'up_to_45v', 5: 'up_to_3v'}], 'B'),
		'set_averaging': FunctionInfo(19, ['average'], ['int'], [{}], 'B', [], [], ''),
		'get_averaging': FunctionInfo(20, [], [], [], '', ['average'], [{}], 'B'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'voltage': CallbackInfo(13, ['voltage'], [{}], 'H', None),
		'analog_value': CallbackInfo(14, ['value'], [{}], 'H', None),
		'voltage_reached': CallbackInfo(15, ['voltage'], [{}], 'H', None),
		'analog_value_reached': CallbackInfo(16, ['value'], [{}], 'H', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 1; re[3] = 2; re[4] = 1; re[5] = 2; re[6] = 1; re[7] = 2; re[8] = 1; re[9] = 2; re[10] = 1; re[11] = 2; re[12] = 1; re[17] = 3; re[18] = 1; re[19] = 3; re[20] = 1; re[255] = 1

class AnalogInV2Bricklet(MQTTCallbackDevice):
	functions = {
		'get_voltage': FunctionInfo(1, [], [], [], '', ['voltage'], [{}], 'H'),
		'get_analog_value': FunctionInfo(2, [], [], [], '', ['value'], [{}], 'H'),
		'set_voltage_callback_period': FunctionInfo(3, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_voltage_callback_period': FunctionInfo(4, [], [], [], '', ['period'], [{}], 'I'),
		'set_analog_value_callback_period': FunctionInfo(5, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_analog_value_callback_period': FunctionInfo(6, [], [], [], '', ['period'], [{}], 'I'),
		'set_voltage_callback_threshold': FunctionInfo(7, ['option', 'min', 'max'], ['char', 'int', 'int'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c H H', [], [], ''),
		'get_voltage_callback_threshold': FunctionInfo(8, [], [], [], '', ['option', 'min', 'max'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c H H'),
		'set_analog_value_callback_threshold': FunctionInfo(9, ['option', 'min', 'max'], ['char', 'int', 'int'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c H H', [], [], ''),
		'get_analog_value_callback_threshold': FunctionInfo(10, [], [], [], '', ['option', 'min', 'max'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c H H'),
		'set_debounce_period': FunctionInfo(11, ['debounce'], ['int'], [{}], 'I', [], [], ''),
		'get_debounce_period': FunctionInfo(12, [], [], [], '', ['debounce'], [{}], 'I'),
		'set_moving_average': FunctionInfo(13, ['average'], ['int'], [{}], 'B', [], [], ''),
		'get_moving_average': FunctionInfo(14, [], [], [], '', ['average'], [{}], 'B'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'voltage': CallbackInfo(15, ['voltage'], [{}], 'H', None),
		'analog_value': CallbackInfo(16, ['value'], [{}], 'H', None),
		'voltage_reached': CallbackInfo(17, ['voltage'], [{}], 'H', None),
		'analog_value_reached': CallbackInfo(18, ['value'], [{}], 'H', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 1; re[3] = 2; re[4] = 1; re[5] = 2; re[6] = 1; re[7] = 2; re[8] = 1; re[9] = 2; re[10] = 1; re[11] = 2; re[12] = 1; re[13] = 3; re[14] = 1; re[255] = 1

class AnalogInV3Bricklet(MQTTCallbackDevice):
	functions = {
		'get_voltage': FunctionInfo(1, [], [], [], '', ['voltage'], [{}], 'H'),
		'set_voltage_callback_configuration': FunctionInfo(2, ['period', 'value_has_to_change', 'option', 'min', 'max'], ['int', 'bool', 'char', 'int', 'int'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c H H', [], [], ''),
		'get_voltage_callback_configuration': FunctionInfo(3, [], [], [], '', ['period', 'value_has_to_change', 'option', 'min', 'max'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c H H'),
		'set_oversampling': FunctionInfo(5, ['oversampling'], ['int'], [{0: '32', 1: '64', 2: '128', 3: '256', 4: '512', 5: '1024', 6: '2048', 7: '4096', 8: '8192', 9: '16384'}], 'B', [], [], ''),
		'get_oversampling': FunctionInfo(6, [], [], [], '', ['oversampling'], [{0: '32', 1: '64', 2: '128', 3: '256', 4: '512', 5: '1024', 6: '2048', 7: '4096', 8: '8192', 9: '16384'}], 'B'),
		'set_calibration': FunctionInfo(7, ['offset', 'multiplier', 'divisor'], ['int', 'int', 'int'], [{}, {}, {}], 'h H H', [], [], ''),
		'get_calibration': FunctionInfo(8, [], [], [], '', ['offset', 'multiplier', 'divisor'], [{}, {}, {}], 'h H H'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'voltage': CallbackInfo(4, ['voltage'], [{}], 'H', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 2; re[3] = 1; re[5] = 3; re[6] = 1; re[7] = 3; re[8] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class AnalogOutBricklet(MQTTCallbackDevice):
	functions = {
		'set_voltage': FunctionInfo(1, ['voltage'], ['int'], [{}], 'H', [], [], ''),
		'get_voltage': FunctionInfo(2, [], [], [], '', ['voltage'], [{}], 'H'),
		'set_mode': FunctionInfo(3, ['mode'], ['int'], [{0: 'analog_value', 1: '1k_to_ground', 2: '100k_to_ground', 3: '500k_to_ground'}], 'B', [], [], ''),
		'get_mode': FunctionInfo(4, [], [], [], '', ['mode'], [{0: 'analog_value', 1: '1k_to_ground', 2: '100k_to_ground', 3: '500k_to_ground'}], 'B'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 3; re[2] = 1; re[3] = 3; re[4] = 1; re[255] = 1

class AnalogOutV2Bricklet(MQTTCallbackDevice):
	functions = {
		'set_output_voltage': FunctionInfo(1, ['voltage'], ['int'], [{}], 'H', [], [], ''),
		'get_output_voltage': FunctionInfo(2, [], [], [], '', ['voltage'], [{}], 'H'),
		'get_input_voltage': FunctionInfo(3, [], [], [], '', ['voltage'], [{}], 'H'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 3; re[2] = 1; re[3] = 1; re[255] = 1

class AnalogOutV3Bricklet(MQTTCallbackDevice):
	functions = {
		'set_output_voltage': FunctionInfo(1, ['voltage'], ['int'], [{}], 'H', [], [], ''),
		'get_output_voltage': FunctionInfo(2, [], [], [], '', ['voltage'], [{}], 'H'),
		'get_input_voltage': FunctionInfo(3, [], [], [], '', ['voltage'], [{}], 'H'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 3; re[2] = 1; re[3] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class BarometerBricklet(MQTTCallbackDevice):
	functions = {
		'get_air_pressure': FunctionInfo(1, [], [], [], '', ['air_pressure'], [{}], 'i'),
		'get_altitude': FunctionInfo(2, [], [], [], '', ['altitude'], [{}], 'i'),
		'set_air_pressure_callback_period': FunctionInfo(3, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_air_pressure_callback_period': FunctionInfo(4, [], [], [], '', ['period'], [{}], 'I'),
		'set_altitude_callback_period': FunctionInfo(5, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_altitude_callback_period': FunctionInfo(6, [], [], [], '', ['period'], [{}], 'I'),
		'set_air_pressure_callback_threshold': FunctionInfo(7, ['option', 'min', 'max'], ['char', 'int', 'int'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c i i', [], [], ''),
		'get_air_pressure_callback_threshold': FunctionInfo(8, [], [], [], '', ['option', 'min', 'max'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c i i'),
		'set_altitude_callback_threshold': FunctionInfo(9, ['option', 'min', 'max'], ['char', 'int', 'int'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c i i', [], [], ''),
		'get_altitude_callback_threshold': FunctionInfo(10, [], [], [], '', ['option', 'min', 'max'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c i i'),
		'set_debounce_period': FunctionInfo(11, ['debounce'], ['int'], [{}], 'I', [], [], ''),
		'get_debounce_period': FunctionInfo(12, [], [], [], '', ['debounce'], [{}], 'I'),
		'set_reference_air_pressure': FunctionInfo(13, ['air_pressure'], ['int'], [{}], 'i', [], [], ''),
		'get_chip_temperature': FunctionInfo(14, [], [], [], '', ['temperature'], [{}], 'h'),
		'get_reference_air_pressure': FunctionInfo(19, [], [], [], '', ['air_pressure'], [{}], 'i'),
		'set_averaging': FunctionInfo(20, ['moving_average_pressure', 'average_pressure', 'average_temperature'], ['int', 'int', 'int'], [{}, {}, {}], 'B B B', [], [], ''),
		'get_averaging': FunctionInfo(21, [], [], [], '', ['moving_average_pressure', 'average_pressure', 'average_temperature'], [{}, {}, {}], 'B B B'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'air_pressure': CallbackInfo(15, ['air_pressure'], [{}], 'i', None),
		'altitude': CallbackInfo(16, ['altitude'], [{}], 'i', None),
		'air_pressure_reached': CallbackInfo(17, ['air_pressure'], [{}], 'i', None),
		'altitude_reached': CallbackInfo(18, ['altitude'], [{}], 'i', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 1; re[3] = 2; re[4] = 1; re[5] = 2; re[6] = 1; re[7] = 2; re[8] = 1; re[9] = 2; re[10] = 1; re[11] = 2; re[12] = 1; re[13] = 3; re[14] = 1; re[19] = 1; re[20] = 3; re[21] = 1; re[255] = 1

class BarometerV2Bricklet(MQTTCallbackDevice):
	functions = {
		'get_air_pressure': FunctionInfo(1, [], [], [], '', ['air_pressure'], [{}], 'i'),
		'set_air_pressure_callback_configuration': FunctionInfo(2, ['period', 'value_has_to_change', 'option', 'min', 'max'], ['int', 'bool', 'char', 'int', 'int'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c i i', [], [], ''),
		'get_air_pressure_callback_configuration': FunctionInfo(3, [], [], [], '', ['period', 'value_has_to_change', 'option', 'min', 'max'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c i i'),
		'get_altitude': FunctionInfo(5, [], [], [], '', ['altitude'], [{}], 'i'),
		'set_altitude_callback_configuration': FunctionInfo(6, ['period', 'value_has_to_change', 'option', 'min', 'max'], ['int', 'bool', 'char', 'int', 'int'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c i i', [], [], ''),
		'get_altitude_callback_configuration': FunctionInfo(7, [], [], [], '', ['period', 'value_has_to_change', 'option', 'min', 'max'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c i i'),
		'get_temperature': FunctionInfo(9, [], [], [], '', ['temperature'], [{}], 'i'),
		'set_temperature_callback_configuration': FunctionInfo(10, ['period', 'value_has_to_change', 'option', 'min', 'max'], ['int', 'bool', 'char', 'int', 'int'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c i i', [], [], ''),
		'get_temperature_callback_configuration': FunctionInfo(11, [], [], [], '', ['period', 'value_has_to_change', 'option', 'min', 'max'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c i i'),
		'set_moving_average_configuration': FunctionInfo(13, ['moving_average_length_air_pressure', 'moving_average_length_temperature'], ['int', 'int'], [{}, {}], 'H H', [], [], ''),
		'get_moving_average_configuration': FunctionInfo(14, [], [], [], '', ['moving_average_length_air_pressure', 'moving_average_length_temperature'], [{}, {}], 'H H'),
		'set_reference_air_pressure': FunctionInfo(15, ['air_pressure'], ['int'], [{}], 'i', [], [], ''),
		'get_reference_air_pressure': FunctionInfo(16, [], [], [], '', ['air_pressure'], [{}], 'i'),
		'set_calibration': FunctionInfo(17, ['measured_air_pressure', 'actual_air_pressure'], ['int', 'int'], [{}, {}], 'i i', [], [], ''),
		'get_calibration': FunctionInfo(18, [], [], [], '', ['measured_air_pressure', 'actual_air_pressure'], [{}, {}], 'i i'),
		'set_sensor_configuration': FunctionInfo(19, ['data_rate', 'air_pressure_low_pass_filter'], ['int', 'int'], [{0: 'off', 1: '1hz', 2: '10hz', 3: '25hz', 4: '50hz', 5: '75hz'}, {0: 'off', 1: '1_9th', 2: '1_20th'}], 'B B', [], [], ''),
		'get_sensor_configuration': FunctionInfo(20, [], [], [], '', ['data_rate', 'air_pressure_low_pass_filter'], [{0: 'off', 1: '1hz', 2: '10hz', 3: '25hz', 4: '50hz', 5: '75hz'}, {0: 'off', 1: '1_9th', 2: '1_20th'}], 'B B'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'air_pressure': CallbackInfo(4, ['air_pressure'], [{}], 'i', None),
		'altitude': CallbackInfo(8, ['altitude'], [{}], 'i', None),
		'temperature': CallbackInfo(12, ['temperature'], [{}], 'i', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 2; re[3] = 1; re[5] = 1; re[6] = 2; re[7] = 1; re[9] = 1; re[10] = 2; re[11] = 1; re[13] = 3; re[14] = 1; re[15] = 3; re[16] = 1; re[17] = 3; re[18] = 1; re[19] = 3; re[20] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class CANBricklet(MQTTCallbackDevice):
	functions = {
		'write_frame': FunctionInfo(1, ['frame_type', 'identifier', 'data', 'length'], ['int', 'int', ('int', 8), 'int'], [{0: 'standard_data', 1: 'standard_remote', 2: 'extended_data', 3: 'extended_remote'}, {}, {}, {}], 'B I 8B B', ['success'], [{}], '!'),
		'read_frame': FunctionInfo(2, [], [], [], '', ['success', 'frame_type', 'identifier', 'data', 'length'], [{}, {0: 'standard_data', 1: 'standard_remote', 2: 'extended_data', 3: 'extended_remote'}, {}, {}, {}], '! B I 8B B'),
		'enable_frame_read_callback': FunctionInfo(3, [], [], [], '', [], [], ''),
		'disable_frame_read_callback': FunctionInfo(4, [], [], [], '', [], [], ''),
		'is_frame_read_callback_enabled': FunctionInfo(5, [], [], [], '', ['enabled'], [{}], '!'),
		'set_configuration': FunctionInfo(6, ['baud_rate', 'transceiver_mode', 'write_timeout'], ['int', 'int', 'int'], [{0: '10kbps', 1: '20kbps', 2: '50kbps', 3: '125kbps', 4: '250kbps', 5: '500kbps', 6: '800kbps', 7: '1000kbps'}, {0: 'normal', 1: 'loopback', 2: 'read_only'}, {}], 'B B i', [], [], ''),
		'get_configuration': FunctionInfo(7, [], [], [], '', ['baud_rate', 'transceiver_mode', 'write_timeout'], [{0: '10kbps', 1: '20kbps', 2: '50kbps', 3: '125kbps', 4: '250kbps', 5: '500kbps', 6: '800kbps', 7: '1000kbps'}, {0: 'normal', 1: 'loopback', 2: 'read_only'}, {}], 'B B i'),
		'set_read_filter': FunctionInfo(8, ['mode', 'mask', 'filter1', 'filter2'], ['int', 'int', 'int', 'int'], [{0: 'disabled', 1: 'accept_all', 2: 'match_standard', 3: 'match_standard_and_data', 4: 'match_extended'}, {}, {}, {}], 'B I I I', [], [], ''),
		'get_read_filter': FunctionInfo(9, [], [], [], '', ['mode', 'mask', 'filter1', 'filter2'], [{0: 'disabled', 1: 'accept_all', 2: 'match_standard', 3: 'match_standard_and_data', 4: 'match_extended'}, {}, {}, {}], 'B I I I'),
		'get_error_log': FunctionInfo(10, [], [], [], '', ['write_error_level', 'read_error_level', 'transceiver_disabled', 'write_timeout_count', 'read_register_overflow_count', 'read_buffer_overflow_count'], [{}, {}, {}, {}, {}, {}], 'B B ! I I I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'frame_read': CallbackInfo(11, ['frame_type', 'identifier', 'data', 'length'], [{0: 'standard_data', 1: 'standard_remote', 2: 'extended_data', 3: 'extended_remote'}, {}, {}, {}], 'B I 8B B', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 1; re[3] = 2; re[4] = 2; re[5] = 1; re[6] = 3; re[7] = 1; re[8] = 3; re[9] = 1; re[10] = 1; re[255] = 1

class CANV2Bricklet(MQTTCallbackDevice):
	functions = {
		'write_frame_low_level': FunctionInfo(1, ['frame_type', 'identifier', 'data_length', 'data_data'], ['int', 'int', 'int', ('int', 15)], [{0: 'standard_data', 1: 'standard_remote', 2: 'extended_data', 3: 'extended_remote'}, {}, {}, {}], 'B I B 15B', ['success'], [{}], '!'),
		'write_frame': HighLevelFunctionInfo(1, 'in', [None, None, 'stream_data'], [None], [None, None, 'stream_length', 'stream_chunk_data'], [None], ['frame_type', 'identifier', 'data'], ['int', 'int', ('int', -15)], [{0: 'standard_data', 1: 'standard_remote', 2: 'extended_data', 3: 'extended_remote'}, {}, {}], 'B I B 15B', ['success'], [{}], '!','0', 15, None,False, False, None),
		'read_frame_low_level': FunctionInfo(2, [], [], [], '', ['success', 'frame_type', 'identifier', 'data_length', 'data_data'], [{}, {0: 'standard_data', 1: 'standard_remote', 2: 'extended_data', 3: 'extended_remote'}, {}, {}, {}], '! B I B 15B'),
		'read_frame': HighLevelFunctionInfo(2, 'out', [], [None, None, None, 'stream_data'], [], [None, None, None, 'stream_length', 'stream_chunk_data'], [], [], [], '', ['success', 'frame-type', 'identifier', 'data'], [{}, {0: 'standard_data', 1: 'standard_remote', 2: 'extended_data', 3: 'extended_remote'}, {}, {}], '! B I B 15B',None, 15, None,False, True, None),
		'set_frame_read_callback_configuration': FunctionInfo(3, ['enabled'], ['bool'], [{}], '!', [], [], ''),
		'get_frame_read_callback_configuration': FunctionInfo(4, [], [], [], '', ['enabled'], [{}], '!'),
		'set_transceiver_configuration': FunctionInfo(5, ['baud_rate', 'sample_point', 'transceiver_mode'], ['int', 'int', 'int'], [{}, {}, {0: 'normal', 1: 'loopback', 2: 'read_only'}], 'I H B', [], [], ''),
		'get_transceiver_configuration': FunctionInfo(6, [], [], [], '', ['baud_rate', 'sample_point', 'transceiver_mode'], [{}, {}, {0: 'normal', 1: 'loopback', 2: 'read_only'}], 'I H B'),
		'set_queue_configuration_low_level': FunctionInfo(7, ['write_buffer_size', 'write_buffer_timeout', 'write_backlog_size', 'read_buffer_sizes_length', 'read_buffer_sizes_data', 'read_backlog_size'], ['int', 'int', 'int', 'int', ('int', 32), 'int'], [{}, {}, {}, {}, {}, {}], 'B i H B 32b H', [], [], ''),
		'set_queue_configuration': HighLevelFunctionInfo(7, 'in', [None, None, None, 'stream_data', None], [], [None, None, None, 'stream_length', 'stream_chunk_data', None], [], ['write_buffer_size', 'write_buffer_timeout', 'write_backlog_size', 'read_buffer_sizes', 'read_backlog_size'], ['int', 'int', 'int', ('int', -32), 'int'], [{}, {}, {}, {}, {}], 'B i H B 32b H', [], [], '','0', 32, None,False, False, None),
		'get_queue_configuration_low_level': FunctionInfo(8, [], [], [], '', ['write_buffer_size', 'write_buffer_timeout', 'write_backlog_size', 'read_buffer_sizes_length', 'read_buffer_sizes_data', 'read_backlog_size'], [{}, {}, {}, {}, {}, {}], 'B i H B 32b H'),
		'get_queue_configuration': HighLevelFunctionInfo(8, 'out', [], [None, None, None, 'stream_data', None], [], [None, None, None, 'stream_length', 'stream_chunk_data', None], [], [], [], '', ['write-buffer-size', 'write-buffer-timeout', 'write-backlog-size', 'read-buffer-sizes', 'read-backlog-size'], [{}, {}, {}, {}, {}], 'B i H B 32b H',None, 32, None,False, True, None),
		'set_read_filter_configuration': FunctionInfo(9, ['buffer_index', 'filter_mode', 'filter_mask', 'filter_identifier'], ['int', 'int', 'int', 'int'], [{}, {0: 'accept_all', 1: 'match_standard_only', 2: 'match_extended_only', 3: 'match_standard_and_extended'}, {}, {}], 'B B I I', [], [], ''),
		'get_read_filter_configuration': FunctionInfo(10, ['buffer_index'], ['int'], [{}], 'B', ['filter_mode', 'filter_mask', 'filter_identifier'], [{0: 'accept_all', 1: 'match_standard_only', 2: 'match_extended_only', 3: 'match_standard_and_extended'}, {}, {}], 'B I I'),
		'get_error_log_low_level': FunctionInfo(11, [], [], [], '', ['transceiver_state', 'transceiver_write_error_level', 'transceiver_read_error_level', 'transceiver_stuffing_error_count', 'transceiver_format_error_count', 'transceiver_ack_error_count', 'transceiver_bit1_error_count', 'transceiver_bit0_error_count', 'transceiver_crc_error_count', 'write_buffer_timeout_error_count', 'read_buffer_overflow_error_count', 'read_buffer_overflow_error_occurred_length', 'read_buffer_overflow_error_occurred_data', 'read_backlog_overflow_error_count'], [{0: 'active', 1: 'passive', 2: 'disabled'}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}], 'B B B I I I I I I I I B 32! I'),
		'get_error_log': HighLevelFunctionInfo(11, 'out', [], [None, None, None, None, None, None, None, None, None, None, None, 'stream_data', None], [], [None, None, None, None, None, None, None, None, None, None, None, 'stream_length', 'stream_chunk_data', None], [], [], [], '', ['transceiver-state', 'transceiver-write-error-level', 'transceiver-read-error-level', 'transceiver-stuffing-error-count', 'transceiver-format-error-count', 'transceiver-ack-error-count', 'transceiver-bit1-error-count', 'transceiver-bit0-error-count', 'transceiver-crc-error-count', 'write-buffer-timeout-error-count', 'read-buffer-overflow-error-count', 'read-buffer-overflow-error-occurred', 'read-backlog-overflow-error-count'], [{0: 'active', 1: 'passive', 2: 'disabled'}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}], 'B B B I I I I I I I I B 32! I',None, 32, None,False, True, None),
		'set_communication_led_config': FunctionInfo(12, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_communication'}], 'B', [], [], ''),
		'get_communication_led_config': FunctionInfo(13, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_communication'}], 'B'),
		'set_error_led_config': FunctionInfo(14, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_transceiver_state', 4: 'show_error'}], 'B', [], [], ''),
		'get_error_led_config': FunctionInfo(15, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_transceiver_state', 4: 'show_error'}], 'B'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'frame_read': CallbackInfo(16, ['frame_type', 'identifier', 'data'], [{0: 'standard_data', 1: 'standard_remote', 2: 'extended_data', 3: 'extended_remote'}, {}, {}], 'B I B 15B', [(None, None, 'stream_length', 'stream_chunk_data'), {'fixed_length': None, 'single_chunk': True}, None])
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 1; re[3] = 2; re[4] = 1; re[5] = 3; re[6] = 1; re[7] = 2; re[8] = 1; re[9] = 3; re[10] = 1; re[11] = 1; re[12] = 3; re[13] = 1; re[14] = 3; re[15] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class CO2Bricklet(MQTTCallbackDevice):
	functions = {
		'get_co2_concentration': FunctionInfo(1, [], [], [], '', ['co2_concentration'], [{}], 'H'),
		'set_co2_concentration_callback_period': FunctionInfo(2, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_co2_concentration_callback_period': FunctionInfo(3, [], [], [], '', ['period'], [{}], 'I'),
		'set_co2_concentration_callback_threshold': FunctionInfo(4, ['option', 'min', 'max'], ['char', 'int', 'int'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c H H', [], [], ''),
		'get_co2_concentration_callback_threshold': FunctionInfo(5, [], [], [], '', ['option', 'min', 'max'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c H H'),
		'set_debounce_period': FunctionInfo(6, ['debounce'], ['int'], [{}], 'I', [], [], ''),
		'get_debounce_period': FunctionInfo(7, [], [], [], '', ['debounce'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'co2_concentration': CallbackInfo(8, ['co2_concentration'], [{}], 'H', None),
		'co2_concentration_reached': CallbackInfo(9, ['co2_concentration'], [{}], 'H', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 2; re[3] = 1; re[4] = 2; re[5] = 1; re[6] = 2; re[7] = 1; re[255] = 1

class CO2V2Bricklet(MQTTCallbackDevice):
	functions = {
		'get_all_values': FunctionInfo(1, [], [], [], '', ['co2_concentration', 'temperature', 'humidity'], [{}, {}, {}], 'H h H'),
		'set_air_pressure': FunctionInfo(2, ['air_pressure'], ['int'], [{}], 'H', [], [], ''),
		'get_air_pressure': FunctionInfo(3, [], [], [], '', ['air_pressure'], [{}], 'H'),
		'set_temperature_offset': FunctionInfo(4, ['offset'], ['int'], [{}], 'H', [], [], ''),
		'get_temperature_offset': FunctionInfo(5, [], [], [], '', ['offset'], [{}], 'H'),
		'set_all_values_callback_configuration': FunctionInfo(6, ['period', 'value_has_to_change'], ['int', 'bool'], [{}, {}], 'I !', [], [], ''),
		'get_all_values_callback_configuration': FunctionInfo(7, [], [], [], '', ['period', 'value_has_to_change'], [{}, {}], 'I !'),
		'get_co2_concentration': FunctionInfo(9, [], [], [], '', ['co2_concentration'], [{}], 'H'),
		'set_co2_concentration_callback_configuration': FunctionInfo(10, ['period', 'value_has_to_change', 'option', 'min', 'max'], ['int', 'bool', 'char', 'int', 'int'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c H H', [], [], ''),
		'get_co2_concentration_callback_configuration': FunctionInfo(11, [], [], [], '', ['period', 'value_has_to_change', 'option', 'min', 'max'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c H H'),
		'get_temperature': FunctionInfo(13, [], [], [], '', ['temperature'], [{}], 'h'),
		'set_temperature_callback_configuration': FunctionInfo(14, ['period', 'value_has_to_change', 'option', 'min', 'max'], ['int', 'bool', 'char', 'int', 'int'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c h h', [], [], ''),
		'get_temperature_callback_configuration': FunctionInfo(15, [], [], [], '', ['period', 'value_has_to_change', 'option', 'min', 'max'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c h h'),
		'get_humidity': FunctionInfo(17, [], [], [], '', ['humidity'], [{}], 'H'),
		'set_humidity_callback_configuration': FunctionInfo(18, ['period', 'value_has_to_change', 'option', 'min', 'max'], ['int', 'bool', 'char', 'int', 'int'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c H H', [], [], ''),
		'get_humidity_callback_configuration': FunctionInfo(19, [], [], [], '', ['period', 'value_has_to_change', 'option', 'min', 'max'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c H H'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'all_values': CallbackInfo(8, ['co2_concentration', 'temperature', 'humidity'], [{}, {}, {}], 'H h H', None),
		'co2_concentration': CallbackInfo(12, ['co2_concentration'], [{}], 'H', None),
		'temperature': CallbackInfo(16, ['temperature'], [{}], 'h', None),
		'humidity': CallbackInfo(20, ['humidity'], [{}], 'H', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 3; re[3] = 1; re[4] = 3; re[5] = 1; re[6] = 2; re[7] = 1; re[9] = 1; re[10] = 2; re[11] = 1; re[13] = 1; re[14] = 2; re[15] = 1; re[17] = 1; re[18] = 2; re[19] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class ColorBricklet(MQTTCallbackDevice):
	functions = {
		'get_color': FunctionInfo(1, [], [], [], '', ['r', 'g', 'b', 'c'], [{}, {}, {}, {}], 'H H H H'),
		'set_color_callback_period': FunctionInfo(2, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_color_callback_period': FunctionInfo(3, [], [], [], '', ['period'], [{}], 'I'),
		'set_color_callback_threshold': FunctionInfo(4, ['option', 'min_r', 'max_r', 'min_g', 'max_g', 'min_b', 'max_b', 'min_c', 'max_c'], ['char', 'int', 'int', 'int', 'int', 'int', 'int', 'int', 'int'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}, {}, {}, {}, {}, {}, {}], 'c H H H H H H H H', [], [], ''),
		'get_color_callback_threshold': FunctionInfo(5, [], [], [], '', ['option', 'min_r', 'max_r', 'min_g', 'max_g', 'min_b', 'max_b', 'min_c', 'max_c'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}, {}, {}, {}, {}, {}, {}], 'c H H H H H H H H'),
		'set_debounce_period': FunctionInfo(6, ['debounce'], ['int'], [{}], 'I', [], [], ''),
		'get_debounce_period': FunctionInfo(7, [], [], [], '', ['debounce'], [{}], 'I'),
		'light_on': FunctionInfo(10, [], [], [], '', [], [], ''),
		'light_off': FunctionInfo(11, [], [], [], '', [], [], ''),
		'is_light_on': FunctionInfo(12, [], [], [], '', ['light'], [{0: 'on', 1: 'off'}], 'B'),
		'set_config': FunctionInfo(13, ['gain', 'integration_time'], ['int', 'int'], [{0: '1x', 1: '4x', 2: '16x', 3: '60x'}, {0: '2ms', 1: '24ms', 2: '101ms', 3: '154ms', 4: '700ms'}], 'B B', [], [], ''),
		'get_config': FunctionInfo(14, [], [], [], '', ['gain', 'integration_time'], [{0: '1x', 1: '4x', 2: '16x', 3: '60x'}, {0: '2ms', 1: '24ms', 2: '101ms', 3: '154ms', 4: '700ms'}], 'B B'),
		'get_illuminance': FunctionInfo(15, [], [], [], '', ['illuminance'], [{}], 'I'),
		'get_color_temperature': FunctionInfo(16, [], [], [], '', ['color_temperature'], [{}], 'H'),
		'set_illuminance_callback_period': FunctionInfo(17, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_illuminance_callback_period': FunctionInfo(18, [], [], [], '', ['period'], [{}], 'I'),
		'set_color_temperature_callback_period': FunctionInfo(19, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_color_temperature_callback_period': FunctionInfo(20, [], [], [], '', ['period'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'color': CallbackInfo(8, ['r', 'g', 'b', 'c'], [{}, {}, {}, {}], 'H H H H', None),
		'color_reached': CallbackInfo(9, ['r', 'g', 'b', 'c'], [{}, {}, {}, {}], 'H H H H', None),
		'illuminance': CallbackInfo(21, ['illuminance'], [{}], 'I', None),
		'color_temperature': CallbackInfo(22, ['color_temperature'], [{}], 'H', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 2; re[3] = 1; re[4] = 2; re[5] = 1; re[6] = 2; re[7] = 1; re[10] = 3; re[11] = 3; re[12] = 1; re[13] = 3; re[14] = 1; re[15] = 1; re[16] = 1; re[17] = 2; re[18] = 1; re[19] = 2; re[20] = 1; re[255] = 1

class ColorV2Bricklet(MQTTCallbackDevice):
	functions = {
		'get_color': FunctionInfo(1, [], [], [], '', ['r', 'g', 'b', 'c'], [{}, {}, {}, {}], 'H H H H'),
		'set_color_callback_configuration': FunctionInfo(2, ['period', 'value_has_to_change'], ['int', 'bool'], [{}, {}], 'I !', [], [], ''),
		'get_color_callback_configuration': FunctionInfo(3, [], [], [], '', ['period', 'value_has_to_change'], [{}, {}], 'I !'),
		'get_illuminance': FunctionInfo(5, [], [], [], '', ['illuminance'], [{}], 'I'),
		'set_illuminance_callback_configuration': FunctionInfo(6, ['period', 'value_has_to_change', 'option', 'min', 'max'], ['int', 'bool', 'char', 'int', 'int'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c I I', [], [], ''),
		'get_illuminance_callback_configuration': FunctionInfo(7, [], [], [], '', ['period', 'value_has_to_change', 'option', 'min', 'max'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c I I'),
		'get_color_temperature': FunctionInfo(9, [], [], [], '', ['color_temperature'], [{}], 'H'),
		'set_color_temperature_callback_configuration': FunctionInfo(10, ['period', 'value_has_to_change', 'option', 'min', 'max'], ['int', 'bool', 'char', 'int', 'int'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c H H', [], [], ''),
		'get_color_temperature_callback_configuration': FunctionInfo(11, [], [], [], '', ['period', 'value_has_to_change', 'option', 'min', 'max'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c H H'),
		'set_light': FunctionInfo(13, ['enable'], ['bool'], [{}], '!', [], [], ''),
		'get_light': FunctionInfo(14, [], [], [], '', ['enable'], [{}], '!'),
		'set_configuration': FunctionInfo(15, ['gain', 'integration_time'], ['int', 'int'], [{0: '1x', 1: '4x', 2: '16x', 3: '60x'}, {0: '2ms', 1: '24ms', 2: '101ms', 3: '154ms', 4: '700ms'}], 'B B', [], [], ''),
		'get_configuration': FunctionInfo(16, [], [], [], '', ['gain', 'integration_time'], [{0: '1x', 1: '4x', 2: '16x', 3: '60x'}, {0: '2ms', 1: '24ms', 2: '101ms', 3: '154ms', 4: '700ms'}], 'B B'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'color': CallbackInfo(4, ['r', 'g', 'b', 'c'], [{}, {}, {}, {}], 'H H H H', None),
		'illuminance': CallbackInfo(8, ['illuminance'], [{}], 'I', None),
		'color_temperature': CallbackInfo(12, ['color_temperature'], [{}], 'H', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 2; re[3] = 1; re[5] = 1; re[6] = 2; re[7] = 1; re[9] = 1; re[10] = 2; re[11] = 1; re[13] = 3; re[14] = 1; re[15] = 3; re[16] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class CompassBricklet(MQTTCallbackDevice):
	functions = {
		'get_heading': FunctionInfo(1, [], [], [], '', ['heading'], [{}], 'h'),
		'set_heading_callback_configuration': FunctionInfo(2, ['period', 'value_has_to_change', 'option', 'min', 'max'], ['int', 'bool', 'char', 'int', 'int'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c h h', [], [], ''),
		'get_heading_callback_configuration': FunctionInfo(3, [], [], [], '', ['period', 'value_has_to_change', 'option', 'min', 'max'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c h h'),
		'get_magnetic_flux_density': FunctionInfo(5, [], [], [], '', ['x', 'y', 'z'], [{}, {}, {}], 'i i i'),
		'set_magnetic_flux_density_callback_configuration': FunctionInfo(6, ['period', 'value_has_to_change'], ['int', 'bool'], [{}, {}], 'I !', [], [], ''),
		'get_magnetic_flux_density_callback_configuration': FunctionInfo(7, [], [], [], '', ['period', 'value_has_to_change'], [{}, {}], 'I !'),
		'set_configuration': FunctionInfo(9, ['data_rate', 'background_calibration'], ['int', 'bool'], [{0: '100hz', 1: '200hz', 2: '400hz', 3: '600hz'}, {}], 'B !', [], [], ''),
		'get_configuration': FunctionInfo(10, [], [], [], '', ['data_rate', 'background_calibration'], [{0: '100hz', 1: '200hz', 2: '400hz', 3: '600hz'}, {}], 'B !'),
		'set_calibration': FunctionInfo(11, ['offset', 'gain'], [('int', 3), ('int', 3)], [{}, {}], '3h 3h', [], [], ''),
		'get_calibration': FunctionInfo(12, [], [], [], '', ['offset', 'gain'], [{}, {}], '3h 3h'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'heading': CallbackInfo(4, ['heading'], [{}], 'h', None),
		'magnetic_flux_density': CallbackInfo(8, ['x', 'y', 'z'], [{}, {}, {}], 'i i i', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 2; re[3] = 1; re[5] = 1; re[6] = 2; re[7] = 1; re[9] = 3; re[10] = 1; re[11] = 3; re[12] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class Current12Bricklet(MQTTCallbackDevice):
	functions = {
		'get_current': FunctionInfo(1, [], [], [], '', ['current'], [{}], 'h'),
		'calibrate': FunctionInfo(2, [], [], [], '', [], [], ''),
		'is_over_current': FunctionInfo(3, [], [], [], '', ['over'], [{}], '!'),
		'get_analog_value': FunctionInfo(4, [], [], [], '', ['value'], [{}], 'H'),
		'set_current_callback_period': FunctionInfo(5, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_current_callback_period': FunctionInfo(6, [], [], [], '', ['period'], [{}], 'I'),
		'set_analog_value_callback_period': FunctionInfo(7, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_analog_value_callback_period': FunctionInfo(8, [], [], [], '', ['period'], [{}], 'I'),
		'set_current_callback_threshold': FunctionInfo(9, ['option', 'min', 'max'], ['char', 'int', 'int'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c h h', [], [], ''),
		'get_current_callback_threshold': FunctionInfo(10, [], [], [], '', ['option', 'min', 'max'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c h h'),
		'set_analog_value_callback_threshold': FunctionInfo(11, ['option', 'min', 'max'], ['char', 'int', 'int'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c H H', [], [], ''),
		'get_analog_value_callback_threshold': FunctionInfo(12, [], [], [], '', ['option', 'min', 'max'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c H H'),
		'set_debounce_period': FunctionInfo(13, ['debounce'], ['int'], [{}], 'I', [], [], ''),
		'get_debounce_period': FunctionInfo(14, [], [], [], '', ['debounce'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'current': CallbackInfo(15, ['current'], [{}], 'h', None),
		'analog_value': CallbackInfo(16, ['value'], [{}], 'H', None),
		'current_reached': CallbackInfo(17, ['current'], [{}], 'h', None),
		'analog_value_reached': CallbackInfo(18, ['value'], [{}], 'H', None),
		'over_current': CallbackInfo(19, [], [], '', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 3; re[3] = 1; re[4] = 1; re[5] = 2; re[6] = 1; re[7] = 2; re[8] = 1; re[9] = 2; re[10] = 1; re[11] = 2; re[12] = 1; re[13] = 2; re[14] = 1; re[255] = 1

class Current25Bricklet(MQTTCallbackDevice):
	functions = {
		'get_current': FunctionInfo(1, [], [], [], '', ['current'], [{}], 'h'),
		'calibrate': FunctionInfo(2, [], [], [], '', [], [], ''),
		'is_over_current': FunctionInfo(3, [], [], [], '', ['over'], [{}], '!'),
		'get_analog_value': FunctionInfo(4, [], [], [], '', ['value'], [{}], 'H'),
		'set_current_callback_period': FunctionInfo(5, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_current_callback_period': FunctionInfo(6, [], [], [], '', ['period'], [{}], 'I'),
		'set_analog_value_callback_period': FunctionInfo(7, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_analog_value_callback_period': FunctionInfo(8, [], [], [], '', ['period'], [{}], 'I'),
		'set_current_callback_threshold': FunctionInfo(9, ['option', 'min', 'max'], ['char', 'int', 'int'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c h h', [], [], ''),
		'get_current_callback_threshold': FunctionInfo(10, [], [], [], '', ['option', 'min', 'max'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c h h'),
		'set_analog_value_callback_threshold': FunctionInfo(11, ['option', 'min', 'max'], ['char', 'int', 'int'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c H H', [], [], ''),
		'get_analog_value_callback_threshold': FunctionInfo(12, [], [], [], '', ['option', 'min', 'max'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c H H'),
		'set_debounce_period': FunctionInfo(13, ['debounce'], ['int'], [{}], 'I', [], [], ''),
		'get_debounce_period': FunctionInfo(14, [], [], [], '', ['debounce'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'current': CallbackInfo(15, ['current'], [{}], 'h', None),
		'analog_value': CallbackInfo(16, ['value'], [{}], 'H', None),
		'current_reached': CallbackInfo(17, ['current'], [{}], 'h', None),
		'analog_value_reached': CallbackInfo(18, ['value'], [{}], 'H', None),
		'over_current': CallbackInfo(19, [], [], '', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 3; re[3] = 1; re[4] = 1; re[5] = 2; re[6] = 1; re[7] = 2; re[8] = 1; re[9] = 2; re[10] = 1; re[11] = 2; re[12] = 1; re[13] = 2; re[14] = 1; re[255] = 1

class DCBrick(MQTTCallbackDevice):
	functions = {
		'set_velocity': FunctionInfo(1, ['velocity'], ['int'], [{}], 'h', [], [], ''),
		'get_velocity': FunctionInfo(2, [], [], [], '', ['velocity'], [{}], 'h'),
		'get_current_velocity': FunctionInfo(3, [], [], [], '', ['velocity'], [{}], 'h'),
		'set_acceleration': FunctionInfo(4, ['acceleration'], ['int'], [{}], 'H', [], [], ''),
		'get_acceleration': FunctionInfo(5, [], [], [], '', ['acceleration'], [{}], 'H'),
		'set_pwm_frequency': FunctionInfo(6, ['frequency'], ['int'], [{}], 'H', [], [], ''),
		'get_pwm_frequency': FunctionInfo(7, [], [], [], '', ['frequency'], [{}], 'H'),
		'full_brake': FunctionInfo(8, [], [], [], '', [], [], ''),
		'get_stack_input_voltage': FunctionInfo(9, [], [], [], '', ['voltage'], [{}], 'H'),
		'get_external_input_voltage': FunctionInfo(10, [], [], [], '', ['voltage'], [{}], 'H'),
		'get_current_consumption': FunctionInfo(11, [], [], [], '', ['voltage'], [{}], 'H'),
		'enable': FunctionInfo(12, [], [], [], '', [], [], ''),
		'disable': FunctionInfo(13, [], [], [], '', [], [], ''),
		'is_enabled': FunctionInfo(14, [], [], [], '', ['enabled'], [{}], '!'),
		'set_minimum_voltage': FunctionInfo(15, ['voltage'], ['int'], [{}], 'H', [], [], ''),
		'get_minimum_voltage': FunctionInfo(16, [], [], [], '', ['voltage'], [{}], 'H'),
		'set_drive_mode': FunctionInfo(17, ['mode'], ['int'], [{0: 'drive_brake', 1: 'drive_coast'}], 'B', [], [], ''),
		'get_drive_mode': FunctionInfo(18, [], [], [], '', ['mode'], [{0: 'drive_brake', 1: 'drive_coast'}], 'B'),
		'set_current_velocity_period': FunctionInfo(19, ['period'], ['int'], [{}], 'H', [], [], ''),
		'get_current_velocity_period': FunctionInfo(20, [], [], [], '', ['period'], [{}], 'H'),
		'set_spitfp_baudrate_config': FunctionInfo(231, ['enable_dynamic_baudrate', 'minimum_dynamic_baudrate'], ['bool', 'int'], [{}, {}], '! I', [], [], ''),
		'get_spitfp_baudrate_config': FunctionInfo(232, [], [], [], '', ['enable_dynamic_baudrate', 'minimum_dynamic_baudrate'], [{}, {}], '! I'),
		'get_send_timeout_count': FunctionInfo(233, ['communication_method'], ['int'], [{0: 'none', 1: 'usb', 2: 'spi_stack', 3: 'chibi', 4: 'rs485', 5: 'wifi', 6: 'ethernet', 7: 'wifi_v2'}], 'B', ['timeout_count'], [{}], 'I'),
		'set_spitfp_baudrate': FunctionInfo(234, ['bricklet_port', 'baudrate'], ['char', 'int'], [{}, {}], 'c I', [], [], ''),
		'get_spitfp_baudrate': FunctionInfo(235, ['bricklet_port'], ['char'], [{}], 'c', ['baudrate'], [{}], 'I'),
		'get_spitfp_error_count': FunctionInfo(237, ['bricklet_port'], ['char'], [{}], 'c', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'enable_status_led': FunctionInfo(238, [], [], [], '', [], [], ''),
		'disable_status_led': FunctionInfo(239, [], [], [], '', [], [], ''),
		'is_status_led_enabled': FunctionInfo(240, [], [], [], '', ['enabled'], [{}], '!'),
		'get_protocol1_bricklet_name': FunctionInfo(241, ['port'], ['char'], [{}], 'c', ['protocol_version', 'firmware_version', 'name'], [{}, {}, {}], 'B 3B 40s'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'under_voltage': CallbackInfo(21, ['voltage'], [{}], 'H', None),
		'emergency_shutdown': CallbackInfo(22, [], [], '', None),
		'velocity_reached': CallbackInfo(23, ['velocity'], [{}], 'h', None),
		'current_velocity': CallbackInfo(24, ['velocity'], [{}], 'h', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 3; re[2] = 1; re[3] = 1; re[4] = 3; re[5] = 1; re[6] = 3; re[7] = 1; re[8] = 3; re[9] = 1; re[10] = 1; re[11] = 1; re[12] = 3; re[13] = 3; re[14] = 1; re[15] = 2; re[16] = 1; re[17] = 3; re[18] = 1; re[19] = 2; re[20] = 1; re[231] = 3; re[232] = 1; re[233] = 1; re[234] = 3; re[235] = 1; re[237] = 1; re[238] = 3; re[239] = 3; re[240] = 1; re[241] = 1; re[242] = 1; re[243] = 3; re[255] = 1

class DistanceIRBricklet(MQTTCallbackDevice):
	functions = {
		'get_distance': FunctionInfo(1, [], [], [], '', ['distance'], [{}], 'H'),
		'get_analog_value': FunctionInfo(2, [], [], [], '', ['value'], [{}], 'H'),
		'set_sampling_point': FunctionInfo(3, ['position', 'distance'], ['int', 'int'], [{}, {}], 'B H', [], [], ''),
		'get_sampling_point': FunctionInfo(4, ['position'], ['int'], [{}], 'B', ['distance'], [{}], 'H'),
		'set_distance_callback_period': FunctionInfo(5, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_distance_callback_period': FunctionInfo(6, [], [], [], '', ['period'], [{}], 'I'),
		'set_analog_value_callback_period': FunctionInfo(7, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_analog_value_callback_period': FunctionInfo(8, [], [], [], '', ['period'], [{}], 'I'),
		'set_distance_callback_threshold': FunctionInfo(9, ['option', 'min', 'max'], ['char', 'int', 'int'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c H H', [], [], ''),
		'get_distance_callback_threshold': FunctionInfo(10, [], [], [], '', ['option', 'min', 'max'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c H H'),
		'set_analog_value_callback_threshold': FunctionInfo(11, ['option', 'min', 'max'], ['char', 'int', 'int'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c H H', [], [], ''),
		'get_analog_value_callback_threshold': FunctionInfo(12, [], [], [], '', ['option', 'min', 'max'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c H H'),
		'set_debounce_period': FunctionInfo(13, ['debounce'], ['int'], [{}], 'I', [], [], ''),
		'get_debounce_period': FunctionInfo(14, [], [], [], '', ['debounce'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'distance': CallbackInfo(15, ['distance'], [{}], 'H', None),
		'analog_value': CallbackInfo(16, ['value'], [{}], 'H', None),
		'distance_reached': CallbackInfo(17, ['distance'], [{}], 'H', None),
		'analog_value_reached': CallbackInfo(18, ['value'], [{}], 'H', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 1; re[3] = 3; re[4] = 1; re[5] = 2; re[6] = 1; re[7] = 2; re[8] = 1; re[9] = 2; re[10] = 1; re[11] = 2; re[12] = 1; re[13] = 2; re[14] = 1; re[255] = 1

class DistanceIRV2Bricklet(MQTTCallbackDevice):
	functions = {
		'get_distance': FunctionInfo(1, [], [], [], '', ['distance'], [{}], 'H'),
		'set_distance_callback_configuration': FunctionInfo(2, ['period', 'value_has_to_change', 'option', 'min', 'max'], ['int', 'bool', 'char', 'int', 'int'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c H H', [], [], ''),
		'get_distance_callback_configuration': FunctionInfo(3, [], [], [], '', ['period', 'value_has_to_change', 'option', 'min', 'max'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c H H'),
		'get_analog_value': FunctionInfo(5, [], [], [], '', ['analog_value'], [{}], 'I'),
		'set_analog_value_callback_configuration': FunctionInfo(6, ['period', 'value_has_to_change', 'option', 'min', 'max'], ['int', 'bool', 'char', 'int', 'int'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c I I', [], [], ''),
		'get_analog_value_callback_configuration': FunctionInfo(7, [], [], [], '', ['period', 'value_has_to_change', 'option', 'min', 'max'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c I I'),
		'set_moving_average_configuration': FunctionInfo(9, ['moving_average_length'], ['int'], [{}], 'H', [], [], ''),
		'get_moving_average_configuration': FunctionInfo(10, [], [], [], '', ['moving_average_length'], [{}], 'H'),
		'set_distance_led_config': FunctionInfo(11, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_distance'}], 'B', [], [], ''),
		'get_distance_led_config': FunctionInfo(12, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_distance'}], 'B'),
		'set_sensor_type': FunctionInfo(13, ['sensor'], ['int'], [{0: '2y0a41', 1: '2y0a21', 2: '2y0a02'}], 'B', [], [], ''),
		'get_sensor_type': FunctionInfo(14, [], [], [], '', ['sensor'], [{0: '2y0a41', 1: '2y0a21', 2: '2y0a02'}], 'B'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'distance': CallbackInfo(4, ['distance'], [{}], 'H', None),
		'analog_value': CallbackInfo(8, ['analog_value'], [{}], 'I', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 2; re[3] = 1; re[5] = 1; re[6] = 2; re[7] = 1; re[9] = 3; re[10] = 1; re[11] = 3; re[12] = 1; re[13] = 3; re[14] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class DistanceUSBricklet(MQTTCallbackDevice):
	functions = {
		'get_distance_value': FunctionInfo(1, [], [], [], '', ['distance'], [{}], 'H'),
		'set_distance_callback_period': FunctionInfo(2, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_distance_callback_period': FunctionInfo(3, [], [], [], '', ['period'], [{}], 'I'),
		'set_distance_callback_threshold': FunctionInfo(4, ['option', 'min', 'max'], ['char', 'int', 'int'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c H H', [], [], ''),
		'get_distance_callback_threshold': FunctionInfo(5, [], [], [], '', ['option', 'min', 'max'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c H H'),
		'set_debounce_period': FunctionInfo(6, ['debounce'], ['int'], [{}], 'I', [], [], ''),
		'get_debounce_period': FunctionInfo(7, [], [], [], '', ['debounce'], [{}], 'I'),
		'set_moving_average': FunctionInfo(10, ['average'], ['int'], [{}], 'B', [], [], ''),
		'get_moving_average': FunctionInfo(11, [], [], [], '', ['average'], [{}], 'B'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'distance': CallbackInfo(8, ['distance'], [{}], 'H', None),
		'distance_reached': CallbackInfo(9, ['distance'], [{}], 'H', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 2; re[3] = 1; re[4] = 2; re[5] = 1; re[6] = 2; re[7] = 1; re[10] = 3; re[11] = 1; re[255] = 1

class DistanceUSV2Bricklet(MQTTCallbackDevice):
	functions = {
		'get_distance': FunctionInfo(1, [], [], [], '', ['distance'], [{}], 'H'),
		'set_distance_callback_configuration': FunctionInfo(2, ['period', 'value_has_to_change', 'option', 'min', 'max'], ['int', 'bool', 'char', 'int', 'int'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c H H', [], [], ''),
		'get_distance_callback_configuration': FunctionInfo(3, [], [], [], '', ['period', 'value_has_to_change', 'option', 'min', 'max'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c H H'),
		'set_update_rate': FunctionInfo(5, ['update_rate'], ['int'], [{0: '2_hz', 1: '10_hz'}], 'B', [], [], ''),
		'get_update_rate': FunctionInfo(6, [], [], [], '', ['update_rate'], [{0: '2_hz', 1: '10_hz'}], 'B'),
		'set_distance_led_config': FunctionInfo(7, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_distance'}], 'B', [], [], ''),
		'get_distance_led_config': FunctionInfo(8, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_distance'}], 'B'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'distance': CallbackInfo(4, ['distance'], [{}], 'H', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 2; re[3] = 1; re[5] = 3; re[6] = 1; re[7] = 3; re[8] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class DMXBricklet(MQTTCallbackDevice):
	functions = {
		'set_dmx_mode': FunctionInfo(1, ['dmx_mode'], ['int'], [{0: 'master', 1: 'slave'}], 'B', [], [], ''),
		'get_dmx_mode': FunctionInfo(2, [], [], [], '', ['dmx_mode'], [{0: 'master', 1: 'slave'}], 'B'),
		'write_frame_low_level': FunctionInfo(3, ['frame_length', 'frame_chunk_offset', 'frame_chunk_data'], ['int', 'int', ('int', 60)], [{}, {}, {}], 'H H 60B', [], [], ''),
		'write_frame': HighLevelFunctionInfo(3, 'in', ['stream_data'], [], ['stream_length', 'stream_chunk_offset', 'stream_chunk_data'], [], ['frame'], [('int', -65535)], [{}], 'H H 60B', [], [], '','0', 60, None,False, False, None),
		'read_frame_low_level': FunctionInfo(4, [], [], [], '', ['frame_length', 'frame_chunk_offset', 'frame_chunk_data', 'frame_number'], [{}, {}, {}, {}], 'H H 56B I'),
		'read_frame': HighLevelFunctionInfo(4, 'out', [], ['stream_data', None], [], ['stream_length', 'stream_chunk_offset', 'stream_chunk_data', None], [], [], [], '', ['frame', 'frame-number'], [{}, {}], 'H H 56B I',None, 56, None,False, False, None),
		'set_frame_duration': FunctionInfo(5, ['frame_duration'], ['int'], [{}], 'H', [], [], ''),
		'get_frame_duration': FunctionInfo(6, [], [], [], '', ['frame_duration'], [{}], 'H'),
		'get_frame_error_count': FunctionInfo(7, [], [], [], '', ['overrun_error_count', 'framing_error_count'], [{}, {}], 'I I'),
		'set_communication_led_config': FunctionInfo(8, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_communication'}], 'B', [], [], ''),
		'get_communication_led_config': FunctionInfo(9, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_communication'}], 'B'),
		'set_error_led_config': FunctionInfo(10, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_error'}], 'B', [], [], ''),
		'get_error_led_config': FunctionInfo(11, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_error'}], 'B'),
		'set_frame_callback_config': FunctionInfo(12, ['frame_started_callback_enabled', 'frame_available_callback_enabled', 'frame_callback_enabled', 'frame_error_count_callback_enabled'], ['bool', 'bool', 'bool', 'bool'], [{}, {}, {}, {}], '! ! ! !', [], [], ''),
		'get_frame_callback_config': FunctionInfo(13, [], [], [], '', ['frame_started_callback_enabled', 'frame_available_callback_enabled', 'frame_callback_enabled', 'frame_error_count_callback_enabled'], [{}, {}, {}, {}], '! ! ! !'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'frame_started': CallbackInfo(14, [], [], '', None),
		'frame_available': CallbackInfo(15, ['frame_number'], [{}], 'I', None),
		'frame': CallbackInfo(16, ['frame', 'frame_number'], [{}, {}], 'H H 56B I', [('stream_length', 'stream_chunk_offset', 'stream_chunk_data', None), {'fixed_length': None, 'single_chunk': False}, None]),
		'frame_error_count': CallbackInfo(17, ['overrun_error_count', 'framing_error_count'], [{}, {}], 'I I', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 3; re[2] = 1; re[3] = 2; re[4] = 1; re[5] = 3; re[6] = 1; re[7] = 1; re[8] = 3; re[9] = 1; re[10] = 3; re[11] = 1; re[12] = 2; re[13] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class DualButtonBricklet(MQTTCallbackDevice):
	functions = {
		'set_led_state': FunctionInfo(1, ['led_l', 'led_r'], ['int', 'int'], [{0: 'auto_toggle_on', 1: 'auto_toggle_off', 2: 'on', 3: 'off'}, {0: 'auto_toggle_on', 1: 'auto_toggle_off', 2: 'on', 3: 'off'}], 'B B', [], [], ''),
		'get_led_state': FunctionInfo(2, [], [], [], '', ['led_l', 'led_r'], [{0: 'auto_toggle_on', 1: 'auto_toggle_off', 2: 'on', 3: 'off'}, {0: 'auto_toggle_on', 1: 'auto_toggle_off', 2: 'on', 3: 'off'}], 'B B'),
		'get_button_state': FunctionInfo(3, [], [], [], '', ['button_l', 'button_r'], [{0: 'pressed', 1: 'released'}, {0: 'pressed', 1: 'released'}], 'B B'),
		'set_selected_led_state': FunctionInfo(5, ['led', 'state'], ['int', 'int'], [{0: 'left', 1: 'right'}, {0: 'auto_toggle_on', 1: 'auto_toggle_off', 2: 'on', 3: 'off'}], 'B B', [], [], ''),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'state_changed': CallbackInfo(4, ['button_l', 'button_r', 'led_l', 'led_r'], [{0: 'pressed', 1: 'released'}, {0: 'pressed', 1: 'released'}, {0: 'auto_toggle_on', 1: 'auto_toggle_off', 2: 'on', 3: 'off'}, {0: 'auto_toggle_on', 1: 'auto_toggle_off', 2: 'on', 3: 'off'}], 'B B B B', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 3; re[2] = 1; re[3] = 1; re[5] = 3; re[255] = 1

class DualButtonV2Bricklet(MQTTCallbackDevice):
	functions = {
		'set_led_state': FunctionInfo(1, ['led_l', 'led_r'], ['int', 'int'], [{0: 'auto_toggle_on', 1: 'auto_toggle_off', 2: 'on', 3: 'off'}, {0: 'auto_toggle_on', 1: 'auto_toggle_off', 2: 'on', 3: 'off'}], 'B B', [], [], ''),
		'get_led_state': FunctionInfo(2, [], [], [], '', ['led_l', 'led_r'], [{0: 'auto_toggle_on', 1: 'auto_toggle_off', 2: 'on', 3: 'off'}, {0: 'auto_toggle_on', 1: 'auto_toggle_off', 2: 'on', 3: 'off'}], 'B B'),
		'get_button_state': FunctionInfo(3, [], [], [], '', ['button_l', 'button_r'], [{0: 'pressed', 1: 'released'}, {0: 'pressed', 1: 'released'}], 'B B'),
		'set_selected_led_state': FunctionInfo(5, ['led', 'state'], ['int', 'int'], [{0: 'left', 1: 'right'}, {0: 'auto_toggle_on', 1: 'auto_toggle_off', 2: 'on', 3: 'off'}], 'B B', [], [], ''),
		'set_state_changed_callback_configuration': FunctionInfo(6, ['enabled'], ['bool'], [{}], '!', [], [], ''),
		'get_state_changed_callback_configuration': FunctionInfo(7, [], [], [], '', ['enabled'], [{}], '!'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'state_changed': CallbackInfo(4, ['button_l', 'button_r', 'led_l', 'led_r'], [{0: 'pressed', 1: 'released'}, {0: 'pressed', 1: 'released'}, {0: 'auto_toggle_on', 1: 'auto_toggle_off', 2: 'on', 3: 'off'}, {0: 'auto_toggle_on', 1: 'auto_toggle_off', 2: 'on', 3: 'off'}], 'B B B B', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 3; re[2] = 1; re[3] = 1; re[5] = 3; re[6] = 2; re[7] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class DualRelayBricklet(MQTTCallbackDevice):
	functions = {
		'set_state': FunctionInfo(1, ['relay1', 'relay2'], ['bool', 'bool'], [{}, {}], '! !', [], [], ''),
		'get_state': FunctionInfo(2, [], [], [], '', ['relay1', 'relay2'], [{}, {}], '! !'),
		'set_monoflop': FunctionInfo(3, ['relay', 'state', 'time'], ['int', 'bool', 'int'], [{}, {}, {}], 'B ! I', [], [], ''),
		'get_monoflop': FunctionInfo(4, ['relay'], ['int'], [{}], 'B', ['state', 'time', 'time_remaining'], [{}, {}, {}], '! I I'),
		'set_selected_state': FunctionInfo(6, ['relay', 'state'], ['int', 'bool'], [{}, {}], 'B !', [], [], ''),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'monoflop_done': CallbackInfo(5, ['relay', 'state'], [{}, {}], 'B !', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 3; re[2] = 1; re[3] = 3; re[4] = 1; re[6] = 3; re[255] = 1

class DustDetectorBricklet(MQTTCallbackDevice):
	functions = {
		'get_dust_density': FunctionInfo(1, [], [], [], '', ['dust_density'], [{}], 'H'),
		'set_dust_density_callback_period': FunctionInfo(2, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_dust_density_callback_period': FunctionInfo(3, [], [], [], '', ['period'], [{}], 'I'),
		'set_dust_density_callback_threshold': FunctionInfo(4, ['option', 'min', 'max'], ['char', 'int', 'int'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c H H', [], [], ''),
		'get_dust_density_callback_threshold': FunctionInfo(5, [], [], [], '', ['option', 'min', 'max'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c H H'),
		'set_debounce_period': FunctionInfo(6, ['debounce'], ['int'], [{}], 'I', [], [], ''),
		'get_debounce_period': FunctionInfo(7, [], [], [], '', ['debounce'], [{}], 'I'),
		'set_moving_average': FunctionInfo(10, ['average'], ['int'], [{}], 'B', [], [], ''),
		'get_moving_average': FunctionInfo(11, [], [], [], '', ['average'], [{}], 'B'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'dust_density': CallbackInfo(8, ['dust_density'], [{}], 'H', None),
		'dust_density_reached': CallbackInfo(9, ['dust_density'], [{}], 'H', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 2; re[3] = 1; re[4] = 2; re[5] = 1; re[6] = 2; re[7] = 1; re[10] = 3; re[11] = 1; re[255] = 1

class EPaper296x128Bricklet(MQTTCallbackDevice):
	functions = {
		'draw': FunctionInfo(1, [], [], [], '', [], [], ''),
		'get_draw_status': FunctionInfo(2, [], [], [], '', ['draw_status'], [{0: 'idle', 1: 'copying', 2: 'drawing'}], 'B'),
		'write_black_white_low_level': FunctionInfo(3, ['x_start', 'y_start', 'x_end', 'y_end', 'pixels_length', 'pixels_chunk_offset', 'pixels_chunk_data'], ['int', 'int', 'int', 'int', 'int', 'int', ('bool', 432)], [{}, {}, {}, {}, {}, {}, {}], 'H B H B H H 432!', [], [], ''),
		'write_black_white': HighLevelFunctionInfo(3, 'in', [None, None, None, None, 'stream_data'], [], [None, None, None, None, 'stream_length', 'stream_chunk_offset', 'stream_chunk_data'], [], ['x_start', 'y_start', 'x_end', 'y_end', 'pixels'], ['int', 'int', 'int', 'int', ('bool', -65535)], [{}, {}, {}, {}, {}], 'H B H B H H 432!', [], [], '','0', 432, None,False, False, None),
		'read_black_white_low_level': FunctionInfo(4, ['x_start', 'y_start', 'x_end', 'y_end'], ['int', 'int', 'int', 'int'], [{}, {}, {}, {}], 'H B H B', ['pixels_length', 'pixels_chunk_offset', 'pixels_chunk_data'], [{}, {}, {}], 'H H 464!'),
		'read_black_white': HighLevelFunctionInfo(4, 'out', [None, None, None, None], ['stream_data'], [None, None, None, None], ['stream_length', 'stream_chunk_offset', 'stream_chunk_data'], ['x_start', 'y_start', 'x_end', 'y_end'], ['int', 'int', 'int', 'int'], [{}, {}, {}, {}], 'H B H B', ['pixels'], [{}], 'H H 464!',None, 464, None,False, False, None),
		'write_color_low_level': FunctionInfo(5, ['x_start', 'y_start', 'x_end', 'y_end', 'pixels_length', 'pixels_chunk_offset', 'pixels_chunk_data'], ['int', 'int', 'int', 'int', 'int', 'int', ('bool', 432)], [{}, {}, {}, {}, {}, {}, {}], 'H B H B H H 432!', [], [], ''),
		'write_color': HighLevelFunctionInfo(5, 'in', [None, None, None, None, 'stream_data'], [], [None, None, None, None, 'stream_length', 'stream_chunk_offset', 'stream_chunk_data'], [], ['x_start', 'y_start', 'x_end', 'y_end', 'pixels'], ['int', 'int', 'int', 'int', ('bool', -65535)], [{}, {}, {}, {}, {}], 'H B H B H H 432!', [], [], '','0', 432, None,False, False, None),
		'read_color_low_level': FunctionInfo(6, ['x_start', 'y_start', 'x_end', 'y_end'], ['int', 'int', 'int', 'int'], [{}, {}, {}, {}], 'H B H B', ['pixels_length', 'pixels_chunk_offset', 'pixels_chunk_data'], [{}, {}, {}], 'H H 464!'),
		'read_color': HighLevelFunctionInfo(6, 'out', [None, None, None, None], ['stream_data'], [None, None, None, None], ['stream_length', 'stream_chunk_offset', 'stream_chunk_data'], ['x_start', 'y_start', 'x_end', 'y_end'], ['int', 'int', 'int', 'int'], [{}, {}, {}, {}], 'H B H B', ['pixels'], [{}], 'H H 464!',None, 464, None,False, False, None),
		'fill_display': FunctionInfo(7, ['color'], ['int'], [{0: 'black', 1: 'white', 2: 'red', 2: 'gray'}], 'B', [], [], ''),
		'draw_text': FunctionInfo(8, ['position_x', 'position_y', 'font', 'color', 'orientation', 'text'], ['int', 'int', 'int', 'int', 'int', 'string'], [{}, {}, {0: '6x8', 1: '6x16', 2: '6x24', 3: '6x32', 4: '12x16', 5: '12x24', 6: '12x32', 7: '18x24', 8: '18x32', 9: '24x32'}, {0: 'black', 1: 'white', 2: 'red', 2: 'gray'}, {0: 'horizontal', 1: 'vertical'}, {}], 'H B B B B 50s', [], [], ''),
		'draw_line': FunctionInfo(9, ['position_x_start', 'position_y_start', 'position_x_end', 'position_y_end', 'color'], ['int', 'int', 'int', 'int', 'int'], [{}, {}, {}, {}, {0: 'black', 1: 'white', 2: 'red', 2: 'gray'}], 'H B H B B', [], [], ''),
		'draw_box': FunctionInfo(10, ['position_x_start', 'position_y_start', 'position_x_end', 'position_y_end', 'fill', 'color'], ['int', 'int', 'int', 'int', 'bool', 'int'], [{}, {}, {}, {}, {}, {0: 'black', 1: 'white', 2: 'red', 2: 'gray'}], 'H B H B ! B', [], [], ''),
		'set_update_mode': FunctionInfo(12, ['update_mode'], ['int'], [{0: 'default', 1: 'black_white', 2: 'delta'}], 'B', [], [], ''),
		'get_update_mode': FunctionInfo(13, [], [], [], '', ['update_mode'], [{0: 'default', 1: 'black_white', 2: 'delta'}], 'B'),
		'set_display_type': FunctionInfo(14, ['display_type'], ['int'], [{0: 'black_white_red', 1: 'black_white_gray'}], 'B', [], [], ''),
		'get_display_type': FunctionInfo(15, [], [], [], '', ['display_type'], [{0: 'black_white_red', 1: 'black_white_gray'}], 'B'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'draw_status': CallbackInfo(11, ['draw_status'], [{0: 'idle', 1: 'copying', 2: 'drawing'}], 'B', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 3; re[2] = 1; re[3] = 2; re[4] = 1; re[5] = 2; re[6] = 1; re[7] = 3; re[8] = 3; re[9] = 3; re[10] = 3; re[12] = 3; re[13] = 1; re[14] = 3; re[15] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class EnergyMonitorBricklet(MQTTCallbackDevice):
	functions = {
		'get_energy_data': FunctionInfo(1, [], [], [], '', ['voltage', 'current', 'energy', 'real_power', 'apparent_power', 'reactive_power', 'power_factor', 'frequency'], [{}, {}, {}, {}, {}, {}, {}, {}], 'i i i i i i H H'),
		'reset_energy': FunctionInfo(2, [], [], [], '', [], [], ''),
		'get_waveform_low_level': FunctionInfo(3, [], [], [], '', ['waveform_chunk_offset', 'waveform_chunk_data'], [{}, {}], 'H 30h'),
		'get_waveform': HighLevelFunctionInfo(3, 'out', [], ['stream_data'], [], ['stream_chunk_offset', 'stream_chunk_data'], [], [], [], '', ['waveform'], [{}], 'H 30h',None, 30, 65535,False, False, 1536),
		'get_transformer_status': FunctionInfo(4, [], [], [], '', ['voltage_transformer_connected', 'current_transformer_connected'], [{}, {}], '! !'),
		'set_transformer_calibration': FunctionInfo(5, ['voltage_ratio', 'current_ratio', 'phase_shift'], ['int', 'int', 'int'], [{}, {}, {}], 'H H h', [], [], ''),
		'get_transformer_calibration': FunctionInfo(6, [], [], [], '', ['voltage_ratio', 'current_ratio', 'phase_shift'], [{}, {}, {}], 'H H h'),
		'calibrate_offset': FunctionInfo(7, [], [], [], '', [], [], ''),
		'set_energy_data_callback_configuration': FunctionInfo(8, ['period', 'value_has_to_change'], ['int', 'bool'], [{}, {}], 'I !', [], [], ''),
		'get_energy_data_callback_configuration': FunctionInfo(9, [], [], [], '', ['period', 'value_has_to_change'], [{}, {}], 'I !'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'energy_data': CallbackInfo(10, ['voltage', 'current', 'energy', 'real_power', 'apparent_power', 'reactive_power', 'power_factor', 'frequency'], [{}, {}, {}, {}, {}, {}, {}, {}], 'i i i i i i H H', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 3; re[3] = 1; re[4] = 1; re[5] = 3; re[6] = 1; re[7] = 3; re[8] = 2; re[9] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class GPSBricklet(MQTTCallbackDevice):
	functions = {
		'get_coordinates': FunctionInfo(1, [], [], [], '', ['latitude', 'ns', 'longitude', 'ew', 'pdop', 'hdop', 'vdop', 'epe'], [{}, {}, {}, {}, {}, {}, {}, {}], 'I c I c H H H H'),
		'get_status': FunctionInfo(2, [], [], [], '', ['fix', 'satellites_view', 'satellites_used'], [{1: 'no_fix', 2: '2d_fix', 3: '3d_fix'}, {}, {}], 'B B B'),
		'get_altitude': FunctionInfo(3, [], [], [], '', ['altitude', 'geoidal_separation'], [{}, {}], 'i i'),
		'get_motion': FunctionInfo(4, [], [], [], '', ['course', 'speed'], [{}, {}], 'I I'),
		'get_date_time': FunctionInfo(5, [], [], [], '', ['date', 'time'], [{}, {}], 'I I'),
		'restart': FunctionInfo(6, ['restart_type'], ['int'], [{0: 'hot_start', 1: 'warm_start', 2: 'cold_start', 3: 'factory_reset'}], 'B', [], [], ''),
		'set_coordinates_callback_period': FunctionInfo(7, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_coordinates_callback_period': FunctionInfo(8, [], [], [], '', ['period'], [{}], 'I'),
		'set_status_callback_period': FunctionInfo(9, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_status_callback_period': FunctionInfo(10, [], [], [], '', ['period'], [{}], 'I'),
		'set_altitude_callback_period': FunctionInfo(11, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_altitude_callback_period': FunctionInfo(12, [], [], [], '', ['period'], [{}], 'I'),
		'set_motion_callback_period': FunctionInfo(13, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_motion_callback_period': FunctionInfo(14, [], [], [], '', ['period'], [{}], 'I'),
		'set_date_time_callback_period': FunctionInfo(15, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_date_time_callback_period': FunctionInfo(16, [], [], [], '', ['period'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'coordinates': CallbackInfo(17, ['latitude', 'ns', 'longitude', 'ew', 'pdop', 'hdop', 'vdop', 'epe'], [{}, {}, {}, {}, {}, {}, {}, {}], 'I c I c H H H H', None),
		'status': CallbackInfo(18, ['fix', 'satellites_view', 'satellites_used'], [{1: 'no_fix', 2: '2d_fix', 3: '3d_fix'}, {}, {}], 'B B B', None),
		'altitude': CallbackInfo(19, ['altitude', 'geoidal_separation'], [{}, {}], 'i i', None),
		'motion': CallbackInfo(20, ['course', 'speed'], [{}, {}], 'I I', None),
		'date_time': CallbackInfo(21, ['date', 'time'], [{}, {}], 'I I', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 1; re[3] = 1; re[4] = 1; re[5] = 1; re[6] = 3; re[7] = 2; re[8] = 1; re[9] = 2; re[10] = 1; re[11] = 2; re[12] = 1; re[13] = 2; re[14] = 1; re[15] = 2; re[16] = 1; re[255] = 1

class GPSV2Bricklet(MQTTCallbackDevice):
	functions = {
		'get_coordinates': FunctionInfo(1, [], [], [], '', ['latitude', 'ns', 'longitude', 'ew'], [{}, {}, {}, {}], 'I c I c'),
		'get_status': FunctionInfo(2, [], [], [], '', ['has_fix', 'satellites_view'], [{}, {}], '! B'),
		'get_altitude': FunctionInfo(3, [], [], [], '', ['altitude', 'geoidal_separation'], [{}, {}], 'i i'),
		'get_motion': FunctionInfo(4, [], [], [], '', ['course', 'speed'], [{}, {}], 'I I'),
		'get_date_time': FunctionInfo(5, [], [], [], '', ['date', 'time'], [{}, {}], 'I I'),
		'restart': FunctionInfo(6, ['restart_type'], ['int'], [{0: 'hot_start', 1: 'warm_start', 2: 'cold_start', 3: 'factory_reset'}], 'B', [], [], ''),
		'get_satellite_system_status_low_level': FunctionInfo(7, ['satellite_system'], ['int'], [{0: 'gps', 1: 'glonass', 2: 'galileo'}], 'B', ['satellite_numbers_length', 'satellite_numbers_data', 'fix', 'pdop', 'hdop', 'vdop'], [{}, {}, {1: 'no_fix', 2: '2d_fix', 3: '3d_fix'}, {}, {}, {}], 'B 12B B H H H'),
		'get_satellite_system_status': HighLevelFunctionInfo(7, 'out', [None], ['stream_data', None, None, None, None], [None], ['stream_length', 'stream_chunk_data', None, None, None, None], ['satellite_system'], ['int'], [{0: 'gps', 1: 'glonass', 2: 'galileo'}], 'B', ['satellite-numbers', 'fix', 'pdop', 'hdop', 'vdop'], [{}, {1: 'no_fix', 2: '2d_fix', 3: '3d_fix'}, {}, {}, {}], 'B 12B B H H H',None, 12, None,False, True, None),
		'get_satellite_status': FunctionInfo(8, ['satellite_system', 'satellite_number'], ['int', 'int'], [{0: 'gps', 1: 'glonass', 2: 'galileo'}, {}], 'B B', ['elevation', 'azimuth', 'snr'], [{}, {}, {}], 'h h h'),
		'set_fix_led_config': FunctionInfo(9, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_fix', 4: 'show_pps'}], 'B', [], [], ''),
		'get_fix_led_config': FunctionInfo(10, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_fix', 4: 'show_pps'}], 'B'),
		'set_coordinates_callback_period': FunctionInfo(11, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_coordinates_callback_period': FunctionInfo(12, [], [], [], '', ['period'], [{}], 'I'),
		'set_status_callback_period': FunctionInfo(13, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_status_callback_period': FunctionInfo(14, [], [], [], '', ['period'], [{}], 'I'),
		'set_altitude_callback_period': FunctionInfo(15, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_altitude_callback_period': FunctionInfo(16, [], [], [], '', ['period'], [{}], 'I'),
		'set_motion_callback_period': FunctionInfo(17, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_motion_callback_period': FunctionInfo(18, [], [], [], '', ['period'], [{}], 'I'),
		'set_date_time_callback_period': FunctionInfo(19, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_date_time_callback_period': FunctionInfo(20, [], [], [], '', ['period'], [{}], 'I'),
		'set_sbas_config': FunctionInfo(27, ['sbas_config'], ['int'], [{0: 'enabled', 1: 'disabled'}], 'B', [], [], ''),
		'get_sbas_config': FunctionInfo(28, [], [], [], '', ['sbas_config'], [{0: 'enabled', 1: 'disabled'}], 'B'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'pulse_per_second': CallbackInfo(21, [], [], '', None),
		'coordinates': CallbackInfo(22, ['latitude', 'ns', 'longitude', 'ew'], [{}, {}, {}, {}], 'I c I c', None),
		'status': CallbackInfo(23, ['has_fix', 'satellites_view'], [{}, {}], '! B', None),
		'altitude': CallbackInfo(24, ['altitude', 'geoidal_separation'], [{}, {}], 'i i', None),
		'motion': CallbackInfo(25, ['course', 'speed'], [{}, {}], 'I I', None),
		'date_time': CallbackInfo(26, ['date', 'time'], [{}, {}], 'I I', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 1; re[3] = 1; re[4] = 1; re[5] = 1; re[6] = 3; re[7] = 1; re[8] = 1; re[9] = 3; re[10] = 1; re[11] = 2; re[12] = 1; re[13] = 2; re[14] = 1; re[15] = 2; re[16] = 1; re[17] = 2; re[18] = 1; re[19] = 2; re[20] = 1; re[27] = 3; re[28] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class HallEffectBricklet(MQTTCallbackDevice):
	functions = {
		'get_value': FunctionInfo(1, [], [], [], '', ['value'], [{}], '!'),
		'get_edge_count': FunctionInfo(2, ['reset_counter'], ['bool'], [{}], '!', ['count'], [{}], 'I'),
		'set_edge_count_config': FunctionInfo(3, ['edge_type', 'debounce'], ['int', 'int'], [{0: 'rising', 1: 'falling', 2: 'both'}, {}], 'B B', [], [], ''),
		'get_edge_count_config': FunctionInfo(4, [], [], [], '', ['edge_type', 'debounce'], [{0: 'rising', 1: 'falling', 2: 'both'}, {}], 'B B'),
		'set_edge_interrupt': FunctionInfo(5, ['edges'], ['int'], [{}], 'I', [], [], ''),
		'get_edge_interrupt': FunctionInfo(6, [], [], [], '', ['edges'], [{}], 'I'),
		'set_edge_count_callback_period': FunctionInfo(7, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_edge_count_callback_period': FunctionInfo(8, [], [], [], '', ['period'], [{}], 'I'),
		'edge_interrupt': FunctionInfo(9, [], [], [], '', ['count', 'value'], [{}, {}], 'I !'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'edge_count': CallbackInfo(10, ['count', 'value'], [{}, {}], 'I !', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 1; re[3] = 3; re[4] = 1; re[5] = 2; re[6] = 1; re[7] = 2; re[8] = 1; re[9] = 1; re[255] = 1

class HallEffectV2Bricklet(MQTTCallbackDevice):
	functions = {
		'get_magnetic_flux_density': FunctionInfo(1, [], [], [], '', ['magnetic_flux_density'], [{}], 'h'),
		'set_magnetic_flux_density_callback_configuration': FunctionInfo(2, ['period', 'value_has_to_change', 'option', 'min', 'max'], ['int', 'bool', 'char', 'int', 'int'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c h h', [], [], ''),
		'get_magnetic_flux_density_callback_configuration': FunctionInfo(3, [], [], [], '', ['period', 'value_has_to_change', 'option', 'min', 'max'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c h h'),
		'get_counter': FunctionInfo(5, ['reset_counter'], ['bool'], [{}], '!', ['count'], [{}], 'I'),
		'set_counter_config': FunctionInfo(6, ['high_threshold', 'low_threshold', 'debounce'], ['int', 'int', 'int'], [{}, {}, {}], 'h h I', [], [], ''),
		'get_counter_config': FunctionInfo(7, [], [], [], '', ['high_threshold', 'low_threshold', 'debounce'], [{}, {}, {}], 'h h I'),
		'set_counter_callback_configuration': FunctionInfo(8, ['period', 'value_has_to_change'], ['int', 'bool'], [{}, {}], 'I !', [], [], ''),
		'get_counter_callback_configuration': FunctionInfo(9, [], [], [], '', ['period', 'value_has_to_change'], [{}, {}], 'I !'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'magnetic_flux_density': CallbackInfo(4, ['magnetic_flux_density'], [{}], 'h', None),
		'counter': CallbackInfo(10, ['count'], [{}], 'I', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 2; re[3] = 1; re[5] = 1; re[6] = 3; re[7] = 1; re[8] = 2; re[9] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class HATBrick(MQTTCallbackDevice):
	functions = {
		'set_sleep_mode': FunctionInfo(1, ['power_off_delay', 'power_off_duration', 'raspberry_pi_off', 'bricklets_off', 'enable_sleep_indicator'], ['int', 'int', 'bool', 'bool', 'bool'], [{}, {}, {}, {}, {}], 'I I ! ! !', [], [], ''),
		'get_sleep_mode': FunctionInfo(2, [], [], [], '', ['power_off_delay', 'power_off_duration', 'raspberry_pi_off', 'bricklets_off', 'enable_sleep_indicator'], [{}, {}, {}, {}, {}], 'I I ! ! !'),
		'set_bricklet_power': FunctionInfo(3, ['bricklet_power'], ['bool'], [{}], '!', [], [], ''),
		'get_bricklet_power': FunctionInfo(4, [], [], [], '', ['bricklet_power'], [{}], '!'),
		'get_voltages': FunctionInfo(5, [], [], [], '', ['voltage_usb', 'voltage_dc'], [{}, {}], 'H H'),
		'set_voltages_callback_configuration': FunctionInfo(6, ['period', 'value_has_to_change'], ['int', 'bool'], [{}, {}], 'I !', [], [], ''),
		'get_voltages_callback_configuration': FunctionInfo(7, [], [], [], '', ['period', 'value_has_to_change'], [{}, {}], 'I !'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'voltages': CallbackInfo(8, ['voltage_usb', 'voltage_dc'], [{}, {}], 'H H', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 3; re[2] = 1; re[3] = 3; re[4] = 1; re[5] = 1; re[6] = 2; re[7] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class HATZeroBrick(MQTTCallbackDevice):
	functions = {
		'get_usb_voltage': FunctionInfo(1, [], [], [], '', ['voltage'], [{}], 'H'),
		'set_usb_voltage_callback_configuration': FunctionInfo(2, ['period', 'value_has_to_change', 'option', 'min', 'max'], ['int', 'bool', 'char', 'int', 'int'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c H H', [], [], ''),
		'get_usb_voltage_callback_configuration': FunctionInfo(3, [], [], [], '', ['period', 'value_has_to_change', 'option', 'min', 'max'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c H H'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'usb_voltage': CallbackInfo(4, ['voltage'], [{}], 'H', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 2; re[3] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class HumidityBricklet(MQTTCallbackDevice):
	functions = {
		'get_humidity': FunctionInfo(1, [], [], [], '', ['humidity'], [{}], 'H'),
		'get_analog_value': FunctionInfo(2, [], [], [], '', ['value'], [{}], 'H'),
		'set_humidity_callback_period': FunctionInfo(3, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_humidity_callback_period': FunctionInfo(4, [], [], [], '', ['period'], [{}], 'I'),
		'set_analog_value_callback_period': FunctionInfo(5, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_analog_value_callback_period': FunctionInfo(6, [], [], [], '', ['period'], [{}], 'I'),
		'set_humidity_callback_threshold': FunctionInfo(7, ['option', 'min', 'max'], ['char', 'int', 'int'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c H H', [], [], ''),
		'get_humidity_callback_threshold': FunctionInfo(8, [], [], [], '', ['option', 'min', 'max'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c H H'),
		'set_analog_value_callback_threshold': FunctionInfo(9, ['option', 'min', 'max'], ['char', 'int', 'int'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c H H', [], [], ''),
		'get_analog_value_callback_threshold': FunctionInfo(10, [], [], [], '', ['option', 'min', 'max'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c H H'),
		'set_debounce_period': FunctionInfo(11, ['debounce'], ['int'], [{}], 'I', [], [], ''),
		'get_debounce_period': FunctionInfo(12, [], [], [], '', ['debounce'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'humidity': CallbackInfo(13, ['humidity'], [{}], 'H', None),
		'analog_value': CallbackInfo(14, ['value'], [{}], 'H', None),
		'humidity_reached': CallbackInfo(15, ['humidity'], [{}], 'H', None),
		'analog_value_reached': CallbackInfo(16, ['value'], [{}], 'H', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 1; re[3] = 2; re[4] = 1; re[5] = 2; re[6] = 1; re[7] = 2; re[8] = 1; re[9] = 2; re[10] = 1; re[11] = 2; re[12] = 1; re[255] = 1

class HumidityV2Bricklet(MQTTCallbackDevice):
	functions = {
		'get_humidity': FunctionInfo(1, [], [], [], '', ['humidity'], [{}], 'H'),
		'set_humidity_callback_configuration': FunctionInfo(2, ['period', 'value_has_to_change', 'option', 'min', 'max'], ['int', 'bool', 'char', 'int', 'int'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c H H', [], [], ''),
		'get_humidity_callback_configuration': FunctionInfo(3, [], [], [], '', ['period', 'value_has_to_change', 'option', 'min', 'max'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c H H'),
		'get_temperature': FunctionInfo(5, [], [], [], '', ['temperature'], [{}], 'h'),
		'set_temperature_callback_configuration': FunctionInfo(6, ['period', 'value_has_to_change', 'option', 'min', 'max'], ['int', 'bool', 'char', 'int', 'int'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c h h', [], [], ''),
		'get_temperature_callback_configuration': FunctionInfo(7, [], [], [], '', ['period', 'value_has_to_change', 'option', 'min', 'max'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c h h'),
		'set_heater_configuration': FunctionInfo(9, ['heater_config'], ['int'], [{0: 'disabled', 1: 'enabled'}], 'B', [], [], ''),
		'get_heater_configuration': FunctionInfo(10, [], [], [], '', ['heater_config'], [{0: 'disabled', 1: 'enabled'}], 'B'),
		'set_moving_average_configuration': FunctionInfo(11, ['moving_average_length_humidity', 'moving_average_length_temperature'], ['int', 'int'], [{}, {}], 'H H', [], [], ''),
		'get_moving_average_configuration': FunctionInfo(12, [], [], [], '', ['moving_average_length_humidity', 'moving_average_length_temperature'], [{}, {}], 'H H'),
		'set_samples_per_second': FunctionInfo(13, ['sps'], ['int'], [{0: '20', 1: '10', 2: '5', 3: '1', 4: '02', 5: '01'}], 'B', [], [], ''),
		'get_samples_per_second': FunctionInfo(14, [], [], [], '', ['sps'], [{0: '20', 1: '10', 2: '5', 3: '1', 4: '02', 5: '01'}], 'B'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'humidity': CallbackInfo(4, ['humidity'], [{}], 'H', None),
		'temperature': CallbackInfo(8, ['temperature'], [{}], 'h', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 2; re[3] = 1; re[5] = 1; re[6] = 2; re[7] = 1; re[9] = 3; re[10] = 1; re[11] = 3; re[12] = 1; re[13] = 3; re[14] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class IMUBrick(MQTTCallbackDevice):
	functions = {
		'get_acceleration': FunctionInfo(1, [], [], [], '', ['x', 'y', 'z'], [{}, {}, {}], 'h h h'),
		'get_magnetic_field': FunctionInfo(2, [], [], [], '', ['x', 'y', 'z'], [{}, {}, {}], 'h h h'),
		'get_angular_velocity': FunctionInfo(3, [], [], [], '', ['x', 'y', 'z'], [{}, {}, {}], 'h h h'),
		'get_all_data': FunctionInfo(4, [], [], [], '', ['acc_x', 'acc_y', 'acc_z', 'mag_x', 'mag_y', 'mag_z', 'ang_x', 'ang_y', 'ang_z', 'temperature'], [{}, {}, {}, {}, {}, {}, {}, {}, {}, {}], 'h h h h h h h h h h'),
		'get_orientation': FunctionInfo(5, [], [], [], '', ['roll', 'pitch', 'yaw'], [{}, {}, {}], 'h h h'),
		'get_quaternion': FunctionInfo(6, [], [], [], '', ['x', 'y', 'z', 'w'], [{}, {}, {}, {}], 'f f f f'),
		'get_imu_temperature': FunctionInfo(7, [], [], [], '', ['temperature'], [{}], 'h'),
		'leds_on': FunctionInfo(8, [], [], [], '', [], [], ''),
		'leds_off': FunctionInfo(9, [], [], [], '', [], [], ''),
		'are_leds_on': FunctionInfo(10, [], [], [], '', ['leds'], [{}], '!'),
		'set_acceleration_range': FunctionInfo(11, ['range'], ['int'], [{}], 'B', [], [], ''),
		'get_acceleration_range': FunctionInfo(12, [], [], [], '', ['range'], [{}], 'B'),
		'set_magnetometer_range': FunctionInfo(13, ['range'], ['int'], [{}], 'B', [], [], ''),
		'get_magnetometer_range': FunctionInfo(14, [], [], [], '', ['range'], [{}], 'B'),
		'set_convergence_speed': FunctionInfo(15, ['speed'], ['int'], [{}], 'H', [], [], ''),
		'get_convergence_speed': FunctionInfo(16, [], [], [], '', ['speed'], [{}], 'H'),
		'set_calibration': FunctionInfo(17, ['typ', 'data'], ['int', ('int', 10)], [{0: 'accelerometer_gain', 1: 'accelerometer_bias', 2: 'magnetometer_gain', 3: 'magnetometer_bias', 4: 'gyroscope_gain', 5: 'gyroscope_bias'}, {}], 'B 10h', [], [], ''),
		'get_calibration': FunctionInfo(18, ['typ'], ['int'], [{0: 'accelerometer_gain', 1: 'accelerometer_bias', 2: 'magnetometer_gain', 3: 'magnetometer_bias', 4: 'gyroscope_gain', 5: 'gyroscope_bias'}], 'B', ['data'], [{}], '10h'),
		'set_acceleration_period': FunctionInfo(19, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_acceleration_period': FunctionInfo(20, [], [], [], '', ['period'], [{}], 'I'),
		'set_magnetic_field_period': FunctionInfo(21, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_magnetic_field_period': FunctionInfo(22, [], [], [], '', ['period'], [{}], 'I'),
		'set_angular_velocity_period': FunctionInfo(23, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_angular_velocity_period': FunctionInfo(24, [], [], [], '', ['period'], [{}], 'I'),
		'set_all_data_period': FunctionInfo(25, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_all_data_period': FunctionInfo(26, [], [], [], '', ['period'], [{}], 'I'),
		'set_orientation_period': FunctionInfo(27, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_orientation_period': FunctionInfo(28, [], [], [], '', ['period'], [{}], 'I'),
		'set_quaternion_period': FunctionInfo(29, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_quaternion_period': FunctionInfo(30, [], [], [], '', ['period'], [{}], 'I'),
		'orientation_calculation_on': FunctionInfo(37, [], [], [], '', [], [], ''),
		'orientation_calculation_off': FunctionInfo(38, [], [], [], '', [], [], ''),
		'is_orientation_calculation_on': FunctionInfo(39, [], [], [], '', ['orientation_calculation_on'], [{}], '!'),
		'set_spitfp_baudrate_config': FunctionInfo(231, ['enable_dynamic_baudrate', 'minimum_dynamic_baudrate'], ['bool', 'int'], [{}, {}], '! I', [], [], ''),
		'get_spitfp_baudrate_config': FunctionInfo(232, [], [], [], '', ['enable_dynamic_baudrate', 'minimum_dynamic_baudrate'], [{}, {}], '! I'),
		'get_send_timeout_count': FunctionInfo(233, ['communication_method'], ['int'], [{0: 'none', 1: 'usb', 2: 'spi_stack', 3: 'chibi', 4: 'rs485', 5: 'wifi', 6: 'ethernet', 7: 'wifi_v2'}], 'B', ['timeout_count'], [{}], 'I'),
		'set_spitfp_baudrate': FunctionInfo(234, ['bricklet_port', 'baudrate'], ['char', 'int'], [{}, {}], 'c I', [], [], ''),
		'get_spitfp_baudrate': FunctionInfo(235, ['bricklet_port'], ['char'], [{}], 'c', ['baudrate'], [{}], 'I'),
		'get_spitfp_error_count': FunctionInfo(237, ['bricklet_port'], ['char'], [{}], 'c', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'enable_status_led': FunctionInfo(238, [], [], [], '', [], [], ''),
		'disable_status_led': FunctionInfo(239, [], [], [], '', [], [], ''),
		'is_status_led_enabled': FunctionInfo(240, [], [], [], '', ['enabled'], [{}], '!'),
		'get_protocol1_bricklet_name': FunctionInfo(241, ['port'], ['char'], [{}], 'c', ['protocol_version', 'firmware_version', 'name'], [{}, {}, {}], 'B 3B 40s'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'acceleration': CallbackInfo(31, ['x', 'y', 'z'], [{}, {}, {}], 'h h h', None),
		'magnetic_field': CallbackInfo(32, ['x', 'y', 'z'], [{}, {}, {}], 'h h h', None),
		'angular_velocity': CallbackInfo(33, ['x', 'y', 'z'], [{}, {}, {}], 'h h h', None),
		'all_data': CallbackInfo(34, ['acc_x', 'acc_y', 'acc_z', 'mag_x', 'mag_y', 'mag_z', 'ang_x', 'ang_y', 'ang_z', 'temperature'], [{}, {}, {}, {}, {}, {}, {}, {}, {}, {}], 'h h h h h h h h h h', None),
		'orientation': CallbackInfo(35, ['roll', 'pitch', 'yaw'], [{}, {}, {}], 'h h h', None),
		'quaternion': CallbackInfo(36, ['x', 'y', 'z', 'w'], [{}, {}, {}, {}], 'f f f f', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 1; re[3] = 1; re[4] = 1; re[5] = 1; re[6] = 1; re[7] = 1; re[8] = 3; re[9] = 3; re[10] = 1; re[11] = 3; re[12] = 1; re[13] = 3; re[14] = 1; re[15] = 3; re[16] = 1; re[17] = 3; re[18] = 1; re[19] = 2; re[20] = 1; re[21] = 2; re[22] = 1; re[23] = 2; re[24] = 1; re[25] = 2; re[26] = 1; re[27] = 2; re[28] = 1; re[29] = 2; re[30] = 1; re[37] = 3; re[38] = 3; re[39] = 1; re[231] = 3; re[232] = 1; re[233] = 1; re[234] = 3; re[235] = 1; re[237] = 1; re[238] = 3; re[239] = 3; re[240] = 1; re[241] = 1; re[242] = 1; re[243] = 3; re[255] = 1

class IMUV2Brick(MQTTCallbackDevice):
	functions = {
		'get_acceleration': FunctionInfo(1, [], [], [], '', ['x', 'y', 'z'], [{}, {}, {}], 'h h h'),
		'get_magnetic_field': FunctionInfo(2, [], [], [], '', ['x', 'y', 'z'], [{}, {}, {}], 'h h h'),
		'get_angular_velocity': FunctionInfo(3, [], [], [], '', ['x', 'y', 'z'], [{}, {}, {}], 'h h h'),
		'get_temperature': FunctionInfo(4, [], [], [], '', ['temperature'], [{}], 'b'),
		'get_orientation': FunctionInfo(5, [], [], [], '', ['heading', 'roll', 'pitch'], [{}, {}, {}], 'h h h'),
		'get_linear_acceleration': FunctionInfo(6, [], [], [], '', ['x', 'y', 'z'], [{}, {}, {}], 'h h h'),
		'get_gravity_vector': FunctionInfo(7, [], [], [], '', ['x', 'y', 'z'], [{}, {}, {}], 'h h h'),
		'get_quaternion': FunctionInfo(8, [], [], [], '', ['w', 'x', 'y', 'z'], [{}, {}, {}, {}], 'h h h h'),
		'get_all_data': FunctionInfo(9, [], [], [], '', ['acceleration', 'magnetic_field', 'angular_velocity', 'euler_angle', 'quaternion', 'linear_acceleration', 'gravity_vector', 'temperature', 'calibration_status'], [{}, {}, {}, {}, {}, {}, {}, {}, {}], '3h 3h 3h 3h 4h 3h 3h b B'),
		'leds_on': FunctionInfo(10, [], [], [], '', [], [], ''),
		'leds_off': FunctionInfo(11, [], [], [], '', [], [], ''),
		'are_leds_on': FunctionInfo(12, [], [], [], '', ['leds'], [{}], '!'),
		'save_calibration': FunctionInfo(13, [], [], [], '', ['calibration_done'], [{}], '!'),
		'set_acceleration_period': FunctionInfo(14, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_acceleration_period': FunctionInfo(15, [], [], [], '', ['period'], [{}], 'I'),
		'set_magnetic_field_period': FunctionInfo(16, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_magnetic_field_period': FunctionInfo(17, [], [], [], '', ['period'], [{}], 'I'),
		'set_angular_velocity_period': FunctionInfo(18, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_angular_velocity_period': FunctionInfo(19, [], [], [], '', ['period'], [{}], 'I'),
		'set_temperature_period': FunctionInfo(20, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_temperature_period': FunctionInfo(21, [], [], [], '', ['period'], [{}], 'I'),
		'set_orientation_period': FunctionInfo(22, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_orientation_period': FunctionInfo(23, [], [], [], '', ['period'], [{}], 'I'),
		'set_linear_acceleration_period': FunctionInfo(24, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_linear_acceleration_period': FunctionInfo(25, [], [], [], '', ['period'], [{}], 'I'),
		'set_gravity_vector_period': FunctionInfo(26, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_gravity_vector_period': FunctionInfo(27, [], [], [], '', ['period'], [{}], 'I'),
		'set_quaternion_period': FunctionInfo(28, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_quaternion_period': FunctionInfo(29, [], [], [], '', ['period'], [{}], 'I'),
		'set_all_data_period': FunctionInfo(30, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_all_data_period': FunctionInfo(31, [], [], [], '', ['period'], [{}], 'I'),
		'set_sensor_configuration': FunctionInfo(41, ['magnetometer_rate', 'gyroscope_range', 'gyroscope_bandwidth', 'accelerometer_range', 'accelerometer_bandwidth'], ['int', 'int', 'int', 'int', 'int'], [{0: '2hz', 1: '6hz', 2: '8hz', 3: '10hz', 4: '15hz', 5: '20hz', 6: '25hz', 7: '30hz'}, {0: '2000dps', 1: '1000dps', 2: '500dps', 3: '250dps', 4: '125dps'}, {0: '523hz', 1: '230hz', 2: '116hz', 3: '47hz', 4: '23hz', 5: '12hz', 6: '64hz', 7: '32hz'}, {0: '2g', 1: '4g', 2: '8g', 3: '16g'}, {0: '7_81hz', 1: '15_63hz', 2: '31_25hz', 3: '62_5hz', 4: '125hz', 5: '250hz', 6: '500hz', 7: '1000hz'}], 'B B B B B', [], [], ''),
		'get_sensor_configuration': FunctionInfo(42, [], [], [], '', ['magnetometer_rate', 'gyroscope_range', 'gyroscope_bandwidth', 'accelerometer_range', 'accelerometer_bandwidth'], [{0: '2hz', 1: '6hz', 2: '8hz', 3: '10hz', 4: '15hz', 5: '20hz', 6: '25hz', 7: '30hz'}, {0: '2000dps', 1: '1000dps', 2: '500dps', 3: '250dps', 4: '125dps'}, {0: '523hz', 1: '230hz', 2: '116hz', 3: '47hz', 4: '23hz', 5: '12hz', 6: '64hz', 7: '32hz'}, {0: '2g', 1: '4g', 2: '8g', 3: '16g'}, {0: '7_81hz', 1: '15_63hz', 2: '31_25hz', 3: '62_5hz', 4: '125hz', 5: '250hz', 6: '500hz', 7: '1000hz'}], 'B B B B B'),
		'set_sensor_fusion_mode': FunctionInfo(43, ['mode'], ['int'], [{0: 'off', 1: 'on', 2: 'on_without_magnetometer', 3: 'on_without_fast_magnetometer_calibration'}], 'B', [], [], ''),
		'get_sensor_fusion_mode': FunctionInfo(44, [], [], [], '', ['mode'], [{0: 'off', 1: 'on', 2: 'on_without_magnetometer', 3: 'on_without_fast_magnetometer_calibration'}], 'B'),
		'set_spitfp_baudrate_config': FunctionInfo(231, ['enable_dynamic_baudrate', 'minimum_dynamic_baudrate'], ['bool', 'int'], [{}, {}], '! I', [], [], ''),
		'get_spitfp_baudrate_config': FunctionInfo(232, [], [], [], '', ['enable_dynamic_baudrate', 'minimum_dynamic_baudrate'], [{}, {}], '! I'),
		'get_send_timeout_count': FunctionInfo(233, ['communication_method'], ['int'], [{0: 'none', 1: 'usb', 2: 'spi_stack', 3: 'chibi', 4: 'rs485', 5: 'wifi', 6: 'ethernet', 7: 'wifi_v2'}], 'B', ['timeout_count'], [{}], 'I'),
		'set_spitfp_baudrate': FunctionInfo(234, ['bricklet_port', 'baudrate'], ['char', 'int'], [{}, {}], 'c I', [], [], ''),
		'get_spitfp_baudrate': FunctionInfo(235, ['bricklet_port'], ['char'], [{}], 'c', ['baudrate'], [{}], 'I'),
		'get_spitfp_error_count': FunctionInfo(237, ['bricklet_port'], ['char'], [{}], 'c', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'enable_status_led': FunctionInfo(238, [], [], [], '', [], [], ''),
		'disable_status_led': FunctionInfo(239, [], [], [], '', [], [], ''),
		'is_status_led_enabled': FunctionInfo(240, [], [], [], '', ['enabled'], [{}], '!'),
		'get_protocol1_bricklet_name': FunctionInfo(241, ['port'], ['char'], [{}], 'c', ['protocol_version', 'firmware_version', 'name'], [{}, {}, {}], 'B 3B 40s'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'acceleration': CallbackInfo(32, ['x', 'y', 'z'], [{}, {}, {}], 'h h h', None),
		'magnetic_field': CallbackInfo(33, ['x', 'y', 'z'], [{}, {}, {}], 'h h h', None),
		'angular_velocity': CallbackInfo(34, ['x', 'y', 'z'], [{}, {}, {}], 'h h h', None),
		'temperature': CallbackInfo(35, ['temperature'], [{}], 'b', None),
		'linear_acceleration': CallbackInfo(36, ['x', 'y', 'z'], [{}, {}, {}], 'h h h', None),
		'gravity_vector': CallbackInfo(37, ['x', 'y', 'z'], [{}, {}, {}], 'h h h', None),
		'orientation': CallbackInfo(38, ['heading', 'roll', 'pitch'], [{}, {}, {}], 'h h h', None),
		'quaternion': CallbackInfo(39, ['w', 'x', 'y', 'z'], [{}, {}, {}, {}], 'h h h h', None),
		'all_data': CallbackInfo(40, ['acceleration', 'magnetic_field', 'angular_velocity', 'euler_angle', 'quaternion', 'linear_acceleration', 'gravity_vector', 'temperature', 'calibration_status'], [{}, {}, {}, {}, {}, {}, {}, {}, {}], '3h 3h 3h 3h 4h 3h 3h b B', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 1; re[3] = 1; re[4] = 1; re[5] = 1; re[6] = 1; re[7] = 1; re[8] = 1; re[9] = 1; re[10] = 3; re[11] = 3; re[12] = 1; re[13] = 1; re[14] = 2; re[15] = 1; re[16] = 2; re[17] = 1; re[18] = 2; re[19] = 1; re[20] = 2; re[21] = 1; re[22] = 2; re[23] = 1; re[24] = 2; re[25] = 1; re[26] = 2; re[27] = 1; re[28] = 2; re[29] = 1; re[30] = 2; re[31] = 1; re[41] = 3; re[42] = 1; re[43] = 3; re[44] = 1; re[231] = 3; re[232] = 1; re[233] = 1; re[234] = 3; re[235] = 1; re[237] = 1; re[238] = 3; re[239] = 3; re[240] = 1; re[241] = 1; re[242] = 1; re[243] = 3; re[255] = 1

class IndustrialAnalogOutBricklet(MQTTCallbackDevice):
	functions = {
		'enable': FunctionInfo(1, [], [], [], '', [], [], ''),
		'disable': FunctionInfo(2, [], [], [], '', [], [], ''),
		'is_enabled': FunctionInfo(3, [], [], [], '', ['enabled'], [{}], '!'),
		'set_voltage': FunctionInfo(4, ['voltage'], ['int'], [{}], 'H', [], [], ''),
		'get_voltage': FunctionInfo(5, [], [], [], '', ['voltage'], [{}], 'H'),
		'set_current': FunctionInfo(6, ['current'], ['int'], [{}], 'H', [], [], ''),
		'get_current': FunctionInfo(7, [], [], [], '', ['current'], [{}], 'H'),
		'set_configuration': FunctionInfo(8, ['voltage_range', 'current_range'], ['int', 'int'], [{0: '0_to_5v', 1: '0_to_10v'}, {0: '4_to_20ma', 1: '0_to_20ma', 2: '0_to_24ma'}], 'B B', [], [], ''),
		'get_configuration': FunctionInfo(9, [], [], [], '', ['voltage_range', 'current_range'], [{0: '0_to_5v', 1: '0_to_10v'}, {0: '4_to_20ma', 1: '0_to_20ma', 2: '0_to_24ma'}], 'B B'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 3; re[2] = 3; re[3] = 1; re[4] = 3; re[5] = 1; re[6] = 3; re[7] = 1; re[8] = 3; re[9] = 1; re[255] = 1

class IndustrialAnalogOutV2Bricklet(MQTTCallbackDevice):
	functions = {
		'set_enabled': FunctionInfo(1, ['enabled'], ['bool'], [{}], '!', [], [], ''),
		'get_enabled': FunctionInfo(2, [], [], [], '', ['enabled'], [{}], '!'),
		'set_voltage': FunctionInfo(3, ['voltage'], ['int'], [{}], 'H', [], [], ''),
		'get_voltage': FunctionInfo(4, [], [], [], '', ['voltage'], [{}], 'H'),
		'set_current': FunctionInfo(5, ['current'], ['int'], [{}], 'H', [], [], ''),
		'get_current': FunctionInfo(6, [], [], [], '', ['current'], [{}], 'H'),
		'set_configuration': FunctionInfo(7, ['voltage_range', 'current_range'], ['int', 'int'], [{0: '0_to_5v', 1: '0_to_10v'}, {0: '4_to_20ma', 1: '0_to_20ma', 2: '0_to_24ma'}], 'B B', [], [], ''),
		'get_configuration': FunctionInfo(8, [], [], [], '', ['voltage_range', 'current_range'], [{0: '0_to_5v', 1: '0_to_10v'}, {0: '4_to_20ma', 1: '0_to_20ma', 2: '0_to_24ma'}], 'B B'),
		'set_out_led_config': FunctionInfo(9, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_out_status'}], 'B', [], [], ''),
		'get_out_led_config': FunctionInfo(10, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_out_status'}], 'B'),
		'set_out_led_status_config': FunctionInfo(11, ['min', 'max', 'config'], ['int', 'int', 'int'], [{}, {}, {0: 'threshold', 1: 'intensity'}], 'H H B', [], [], ''),
		'get_out_led_status_config': FunctionInfo(12, [], [], [], '', ['min', 'max', 'config'], [{}, {}, {0: 'threshold', 1: 'intensity'}], 'H H B'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 3; re[2] = 1; re[3] = 3; re[4] = 1; re[5] = 3; re[6] = 1; re[7] = 3; re[8] = 1; re[9] = 3; re[10] = 1; re[11] = 3; re[12] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class IndustrialCounterBricklet(MQTTCallbackDevice):
	functions = {
		'get_counter': FunctionInfo(1, ['channel'], ['int'], [{0: '0', 1: '1', 2: '2', 3: '3'}], 'B', ['counter'], [{}], 'q'),
		'get_all_counter': FunctionInfo(2, [], [], [], '', ['counter'], [{}], '4q'),
		'set_counter': FunctionInfo(3, ['channel', 'counter'], ['int', 'int'], [{0: '0', 1: '1', 2: '2', 3: '3'}, {}], 'B q', [], [], ''),
		'set_all_counter': FunctionInfo(4, ['counter'], [('int', 4)], [{}], '4q', [], [], ''),
		'get_signal_data': FunctionInfo(5, ['channel'], ['int'], [{0: '0', 1: '1', 2: '2', 3: '3'}], 'B', ['duty_cycle', 'period', 'frequency', 'value'], [{}, {}, {}, {}], 'H Q I !'),
		'get_all_signal_data': FunctionInfo(6, [], [], [], '', ['duty_cycle', 'period', 'frequency', 'value'], [{}, {}, {}, {}], '4H 4Q 4I 4!'),
		'set_counter_active': FunctionInfo(7, ['channel', 'active'], ['int', 'bool'], [{0: '0', 1: '1', 2: '2', 3: '3'}, {}], 'B !', [], [], ''),
		'set_all_counter_active': FunctionInfo(8, ['active'], [('bool', 4)], [{}], '4!', [], [], ''),
		'get_counter_active': FunctionInfo(9, ['channel'], ['int'], [{0: '0', 1: '1', 2: '2', 3: '3'}], 'B', ['active'], [{}], '!'),
		'get_all_counter_active': FunctionInfo(10, [], [], [], '', ['active'], [{}], '4!'),
		'set_counter_configuration': FunctionInfo(11, ['channel', 'count_edge', 'count_direction', 'duty_cycle_prescaler', 'frequency_integration_time'], ['int', 'int', 'int', 'int', 'int'], [{0: '0', 1: '1', 2: '2', 3: '3'}, {0: 'rising', 1: 'falling', 2: 'both'}, {0: 'up', 1: 'down', 2: 'external_up', 3: 'external_down'}, {0: '1', 1: '2', 2: '4', 3: '8', 4: '16', 5: '32', 6: '64', 7: '128', 8: '256', 9: '512', 10: '1024', 11: '2048', 12: '4096', 13: '8192', 14: '16384', 15: '32768'}, {0: '128_ms', 1: '256_ms', 2: '512_ms', 3: '1024_ms', 4: '2048_ms', 5: '4096_ms', 6: '8192_ms', 7: '16384_ms', 8: '32768_ms'}], 'B B B B B', [], [], ''),
		'get_counter_configuration': FunctionInfo(12, ['channel'], ['int'], [{0: '0', 1: '1', 2: '2', 3: '3'}], 'B', ['count_edge', 'count_direction', 'duty_cycle_prescaler', 'frequency_integration_time'], [{0: 'rising', 1: 'falling', 2: 'both'}, {0: 'up', 1: 'down', 2: 'external_up', 3: 'external_down'}, {0: '1', 1: '2', 2: '4', 3: '8', 4: '16', 5: '32', 6: '64', 7: '128', 8: '256', 9: '512', 10: '1024', 11: '2048', 12: '4096', 13: '8192', 14: '16384', 15: '32768'}, {0: '128_ms', 1: '256_ms', 2: '512_ms', 3: '1024_ms', 4: '2048_ms', 5: '4096_ms', 6: '8192_ms', 7: '16384_ms', 8: '32768_ms'}], 'B B B B'),
		'set_all_counter_callback_configuration': FunctionInfo(13, ['period', 'value_has_to_change'], ['int', 'bool'], [{}, {}], 'I !', [], [], ''),
		'get_all_counter_callback_configuration': FunctionInfo(14, [], [], [], '', ['period', 'value_has_to_change'], [{}, {}], 'I !'),
		'set_all_signal_data_callback_configuration': FunctionInfo(15, ['period', 'value_has_to_change'], ['int', 'bool'], [{}, {}], 'I !', [], [], ''),
		'get_all_signal_data_callback_configuration': FunctionInfo(16, [], [], [], '', ['period', 'value_has_to_change'], [{}, {}], 'I !'),
		'set_channel_led_config': FunctionInfo(17, ['channel', 'config'], ['int', 'int'], [{0: '0', 1: '1', 2: '2', 3: '3'}, {0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_channel_status'}], 'B B', [], [], ''),
		'get_channel_led_config': FunctionInfo(18, ['channel'], ['int'], [{0: '0', 1: '1', 2: '2', 3: '3'}], 'B', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_channel_status'}], 'B'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'all_counter': CallbackInfo(19, ['counter'], [{}], '4q', None),
		'all_signal_data': CallbackInfo(20, ['duty_cycle', 'period', 'frequency', 'value'], [{}, {}, {}, {}], '4H 4Q 4I 4!', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 1; re[3] = 3; re[4] = 3; re[5] = 1; re[6] = 1; re[7] = 3; re[8] = 3; re[9] = 1; re[10] = 1; re[11] = 3; re[12] = 1; re[13] = 2; re[14] = 1; re[15] = 2; re[16] = 1; re[17] = 3; re[18] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class IndustrialDigitalIn4Bricklet(MQTTCallbackDevice):
	functions = {
		'get_value': FunctionInfo(1, [], [], [], '', ['value_mask'], [{}], 'H'),
		'set_group': FunctionInfo(2, ['group'], [('char', 4)], [{}], '4c', [], [], ''),
		'get_group': FunctionInfo(3, [], [], [], '', ['group'], [{}], '4c'),
		'get_available_for_group': FunctionInfo(4, [], [], [], '', ['available'], [{}], 'B'),
		'set_debounce_period': FunctionInfo(5, ['debounce'], ['int'], [{}], 'I', [], [], ''),
		'get_debounce_period': FunctionInfo(6, [], [], [], '', ['debounce'], [{}], 'I'),
		'set_interrupt': FunctionInfo(7, ['interrupt_mask'], ['int'], [{}], 'H', [], [], ''),
		'get_interrupt': FunctionInfo(8, [], [], [], '', ['interrupt_mask'], [{}], 'H'),
		'get_edge_count': FunctionInfo(10, ['pin', 'reset_counter'], ['int', 'bool'], [{}, {}], 'B !', ['count'], [{}], 'I'),
		'set_edge_count_config': FunctionInfo(11, ['selection_mask', 'edge_type', 'debounce'], ['int', 'int', 'int'], [{}, {0: 'rising', 1: 'falling', 2: 'both'}, {}], 'H B B', [], [], ''),
		'get_edge_count_config': FunctionInfo(12, ['pin'], ['int'], [{}], 'B', ['edge_type', 'debounce'], [{0: 'rising', 1: 'falling', 2: 'both'}, {}], 'B B'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'interrupt': CallbackInfo(9, ['interrupt_mask', 'value_mask'], [{}, {}], 'H H', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 3; re[3] = 1; re[4] = 1; re[5] = 2; re[6] = 1; re[7] = 2; re[8] = 1; re[10] = 1; re[11] = 3; re[12] = 1; re[255] = 1

class IndustrialDigitalIn4V2Bricklet(MQTTCallbackDevice):
	functions = {
		'get_value': FunctionInfo(1, [], [], [], '', ['value'], [{}], '4!'),
		'set_value_callback_configuration': FunctionInfo(2, ['channel', 'period', 'value_has_to_change'], ['int', 'int', 'bool'], [{0: '0', 1: '1', 2: '2', 3: '3'}, {}, {}], 'B I !', [], [], ''),
		'get_value_callback_configuration': FunctionInfo(3, ['channel'], ['int'], [{0: '0', 1: '1', 2: '2', 3: '3'}], 'B', ['period', 'value_has_to_change'], [{}, {}], 'I !'),
		'set_all_value_callback_configuration': FunctionInfo(4, ['period', 'value_has_to_change'], ['int', 'bool'], [{}, {}], 'I !', [], [], ''),
		'get_all_value_callback_configuration': FunctionInfo(5, [], [], [], '', ['period', 'value_has_to_change'], [{}, {}], 'I !'),
		'get_edge_count': FunctionInfo(6, ['channel', 'reset_counter'], ['int', 'bool'], [{0: '0', 1: '1', 2: '2', 3: '3'}, {}], 'B !', ['count'], [{}], 'I'),
		'set_edge_count_configuration': FunctionInfo(7, ['channel', 'edge_type', 'debounce'], ['int', 'int', 'int'], [{0: '0', 1: '1', 2: '2', 3: '3'}, {0: 'rising', 1: 'falling', 2: 'both'}, {}], 'B B B', [], [], ''),
		'get_edge_count_configuration': FunctionInfo(8, ['channel'], ['int'], [{0: '0', 1: '1', 2: '2', 3: '3'}], 'B', ['edge_type', 'debounce'], [{0: 'rising', 1: 'falling', 2: 'both'}, {}], 'B B'),
		'set_channel_led_config': FunctionInfo(9, ['channel', 'config'], ['int', 'int'], [{0: '0', 1: '1', 2: '2', 3: '3'}, {0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_channel_status'}], 'B B', [], [], ''),
		'get_channel_led_config': FunctionInfo(10, ['channel'], ['int'], [{0: '0', 1: '1', 2: '2', 3: '3'}], 'B', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_channel_status'}], 'B'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'value': CallbackInfo(11, ['channel', 'changed', 'value'], [{0: '0', 1: '1', 2: '2', 3: '3'}, {}, {}], 'B ! !', None),
		'all_value': CallbackInfo(12, ['changed', 'value'], [{}, {}], '4! 4!', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 2; re[3] = 1; re[4] = 2; re[5] = 1; re[6] = 1; re[7] = 3; re[8] = 1; re[9] = 3; re[10] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class IndustrialDigitalOut4Bricklet(MQTTCallbackDevice):
	functions = {
		'set_value': FunctionInfo(1, ['value_mask'], ['int'], [{}], 'H', [], [], ''),
		'get_value': FunctionInfo(2, [], [], [], '', ['value_mask'], [{}], 'H'),
		'set_monoflop': FunctionInfo(3, ['selection_mask', 'value_mask', 'time'], ['int', 'int', 'int'], [{}, {}, {}], 'H H I', [], [], ''),
		'get_monoflop': FunctionInfo(4, ['pin'], ['int'], [{}], 'B', ['value', 'time', 'time_remaining'], [{}, {}, {}], 'H I I'),
		'set_group': FunctionInfo(5, ['group'], [('char', 4)], [{}], '4c', [], [], ''),
		'get_group': FunctionInfo(6, [], [], [], '', ['group'], [{}], '4c'),
		'get_available_for_group': FunctionInfo(7, [], [], [], '', ['available'], [{}], 'B'),
		'set_selected_values': FunctionInfo(9, ['selection_mask', 'value_mask'], ['int', 'int'], [{}, {}], 'H H', [], [], ''),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'monoflop_done': CallbackInfo(8, ['selection_mask', 'value_mask'], [{}, {}], 'H H', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 3; re[2] = 1; re[3] = 3; re[4] = 1; re[5] = 3; re[6] = 1; re[7] = 1; re[9] = 3; re[255] = 1

class IndustrialDigitalOut4V2Bricklet(MQTTCallbackDevice):
	functions = {
		'set_value': FunctionInfo(1, ['value'], [('bool', 4)], [{}], '4!', [], [], ''),
		'get_value': FunctionInfo(2, [], [], [], '', ['value'], [{}], '4!'),
		'set_selected_value': FunctionInfo(3, ['channel', 'value'], ['int', 'bool'], [{}, {}], 'B !', [], [], ''),
		'set_monoflop': FunctionInfo(4, ['channel', 'value', 'time'], ['int', 'bool', 'int'], [{}, {}, {}], 'B ! I', [], [], ''),
		'get_monoflop': FunctionInfo(5, ['channel'], ['int'], [{}], 'B', ['value', 'time', 'time_remaining'], [{}, {}, {}], '! I I'),
		'set_channel_led_config': FunctionInfo(7, ['channel', 'config'], ['int', 'int'], [{}, {0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_channel_status'}], 'B B', [], [], ''),
		'get_channel_led_config': FunctionInfo(8, ['channel'], ['int'], [{}], 'B', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_channel_status'}], 'B'),
		'set_pwm_configuration': FunctionInfo(9, ['channel', 'frequency', 'duty_cycle'], ['int', 'int', 'int'], [{}, {}, {}], 'B I H', [], [], ''),
		'get_pwm_configuration': FunctionInfo(10, ['channel'], ['int'], [{}], 'B', ['frequency', 'duty_cycle'], [{}, {}], 'I H'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'monoflop_done': CallbackInfo(6, ['channel', 'value'], [{}, {}], 'B !', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 3; re[2] = 1; re[3] = 3; re[4] = 3; re[5] = 1; re[7] = 3; re[8] = 1; re[9] = 3; re[10] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class IndustrialDual020mABricklet(MQTTCallbackDevice):
	functions = {
		'get_current': FunctionInfo(1, ['sensor'], ['int'], [{}], 'B', ['current'], [{}], 'i'),
		'set_current_callback_period': FunctionInfo(2, ['sensor', 'period'], ['int', 'int'], [{}, {}], 'B I', [], [], ''),
		'get_current_callback_period': FunctionInfo(3, ['sensor'], ['int'], [{}], 'B', ['period'], [{}], 'I'),
		'set_current_callback_threshold': FunctionInfo(4, ['sensor', 'option', 'min', 'max'], ['int', 'char', 'int', 'int'], [{}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'B c i i', [], [], ''),
		'get_current_callback_threshold': FunctionInfo(5, ['sensor'], ['int'], [{}], 'B', ['option', 'min', 'max'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c i i'),
		'set_debounce_period': FunctionInfo(6, ['debounce'], ['int'], [{}], 'I', [], [], ''),
		'get_debounce_period': FunctionInfo(7, [], [], [], '', ['debounce'], [{}], 'I'),
		'set_sample_rate': FunctionInfo(8, ['rate'], ['int'], [{0: '240_sps', 1: '60_sps', 2: '15_sps', 3: '4_sps'}], 'B', [], [], ''),
		'get_sample_rate': FunctionInfo(9, [], [], [], '', ['rate'], [{0: '240_sps', 1: '60_sps', 2: '15_sps', 3: '4_sps'}], 'B'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'current': CallbackInfo(10, ['sensor', 'current'], [{}, {}], 'B i', None),
		'current_reached': CallbackInfo(11, ['sensor', 'current'], [{}, {}], 'B i', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 2; re[3] = 1; re[4] = 2; re[5] = 1; re[6] = 2; re[7] = 1; re[8] = 3; re[9] = 1; re[255] = 1

class IndustrialDual020mAV2Bricklet(MQTTCallbackDevice):
	functions = {
		'get_current': FunctionInfo(1, ['channel'], ['int'], [{}], 'B', ['current'], [{}], 'i'),
		'set_current_callback_configuration': FunctionInfo(2, ['channel', 'period', 'value_has_to_change', 'option', 'min', 'max'], ['int', 'int', 'bool', 'char', 'int', 'int'], [{}, {}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'B I ! c i i', [], [], ''),
		'get_current_callback_configuration': FunctionInfo(3, ['channel'], ['int'], [{}], 'B', ['period', 'value_has_to_change', 'option', 'min', 'max'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c i i'),
		'set_sample_rate': FunctionInfo(5, ['rate'], ['int'], [{0: '240_sps', 1: '60_sps', 2: '15_sps', 3: '4_sps'}], 'B', [], [], ''),
		'get_sample_rate': FunctionInfo(6, [], [], [], '', ['rate'], [{0: '240_sps', 1: '60_sps', 2: '15_sps', 3: '4_sps'}], 'B'),
		'set_gain': FunctionInfo(7, ['gain'], ['int'], [{0: '1x', 1: '2x', 2: '4x', 3: '8x'}], 'B', [], [], ''),
		'get_gain': FunctionInfo(8, [], [], [], '', ['gain'], [{0: '1x', 1: '2x', 2: '4x', 3: '8x'}], 'B'),
		'set_channel_led_config': FunctionInfo(9, ['channel', 'config'], ['int', 'int'], [{}, {0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_channel_status'}], 'B B', [], [], ''),
		'get_channel_led_config': FunctionInfo(10, ['channel'], ['int'], [{}], 'B', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_channel_status'}], 'B'),
		'set_channel_led_status_config': FunctionInfo(11, ['channel', 'min', 'max', 'config'], ['int', 'int', 'int', 'int'], [{}, {}, {}, {0: 'threshold', 1: 'intensity'}], 'B i i B', [], [], ''),
		'get_channel_led_status_config': FunctionInfo(12, ['channel'], ['int'], [{}], 'B', ['min', 'max', 'config'], [{}, {}, {0: 'threshold', 1: 'intensity'}], 'i i B'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'current': CallbackInfo(4, ['channel', 'current'], [{}, {}], 'B i', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 2; re[3] = 1; re[5] = 3; re[6] = 1; re[7] = 3; re[8] = 1; re[9] = 3; re[10] = 1; re[11] = 3; re[12] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class IndustrialDualAnalogInBricklet(MQTTCallbackDevice):
	functions = {
		'get_voltage': FunctionInfo(1, ['channel'], ['int'], [{}], 'B', ['voltage'], [{}], 'i'),
		'set_voltage_callback_period': FunctionInfo(2, ['channel', 'period'], ['int', 'int'], [{}, {}], 'B I', [], [], ''),
		'get_voltage_callback_period': FunctionInfo(3, ['channel'], ['int'], [{}], 'B', ['period'], [{}], 'I'),
		'set_voltage_callback_threshold': FunctionInfo(4, ['channel', 'option', 'min', 'max'], ['int', 'char', 'int', 'int'], [{}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'B c i i', [], [], ''),
		'get_voltage_callback_threshold': FunctionInfo(5, ['channel'], ['int'], [{}], 'B', ['option', 'min', 'max'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c i i'),
		'set_debounce_period': FunctionInfo(6, ['debounce'], ['int'], [{}], 'I', [], [], ''),
		'get_debounce_period': FunctionInfo(7, [], [], [], '', ['debounce'], [{}], 'I'),
		'set_sample_rate': FunctionInfo(8, ['rate'], ['int'], [{0: '976_sps', 1: '488_sps', 2: '244_sps', 3: '122_sps', 4: '61_sps', 5: '4_sps', 6: '2_sps', 7: '1_sps'}], 'B', [], [], ''),
		'get_sample_rate': FunctionInfo(9, [], [], [], '', ['rate'], [{0: '976_sps', 1: '488_sps', 2: '244_sps', 3: '122_sps', 4: '61_sps', 5: '4_sps', 6: '2_sps', 7: '1_sps'}], 'B'),
		'set_calibration': FunctionInfo(10, ['offset', 'gain'], [('int', 2), ('int', 2)], [{}, {}], '2i 2i', [], [], ''),
		'get_calibration': FunctionInfo(11, [], [], [], '', ['offset', 'gain'], [{}, {}], '2i 2i'),
		'get_adc_values': FunctionInfo(12, [], [], [], '', ['value'], [{}], '2i'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'voltage': CallbackInfo(13, ['channel', 'voltage'], [{}, {}], 'B i', None),
		'voltage_reached': CallbackInfo(14, ['channel', 'voltage'], [{}, {}], 'B i', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 2; re[3] = 1; re[4] = 2; re[5] = 1; re[6] = 2; re[7] = 1; re[8] = 3; re[9] = 1; re[10] = 3; re[11] = 1; re[12] = 1; re[255] = 1

class IndustrialDualAnalogInV2Bricklet(MQTTCallbackDevice):
	functions = {
		'get_voltage': FunctionInfo(1, ['channel'], ['int'], [{}], 'B', ['voltage'], [{}], 'i'),
		'set_voltage_callback_configuration': FunctionInfo(2, ['channel', 'period', 'value_has_to_change', 'option', 'min', 'max'], ['int', 'int', 'bool', 'char', 'int', 'int'], [{}, {}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'B I ! c i i', [], [], ''),
		'get_voltage_callback_configuration': FunctionInfo(3, ['channel'], ['int'], [{}], 'B', ['period', 'value_has_to_change', 'option', 'min', 'max'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c i i'),
		'set_sample_rate': FunctionInfo(5, ['rate'], ['int'], [{0: '976_sps', 1: '488_sps', 2: '244_sps', 3: '122_sps', 4: '61_sps', 5: '4_sps', 6: '2_sps', 7: '1_sps'}], 'B', [], [], ''),
		'get_sample_rate': FunctionInfo(6, [], [], [], '', ['rate'], [{0: '976_sps', 1: '488_sps', 2: '244_sps', 3: '122_sps', 4: '61_sps', 5: '4_sps', 6: '2_sps', 7: '1_sps'}], 'B'),
		'set_calibration': FunctionInfo(7, ['offset', 'gain'], [('int', 2), ('int', 2)], [{}, {}], '2i 2i', [], [], ''),
		'get_calibration': FunctionInfo(8, [], [], [], '', ['offset', 'gain'], [{}, {}], '2i 2i'),
		'get_adc_values': FunctionInfo(9, [], [], [], '', ['value'], [{}], '2i'),
		'set_channel_led_config': FunctionInfo(10, ['channel', 'config'], ['int', 'int'], [{}, {0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_channel_status'}], 'B B', [], [], ''),
		'get_channel_led_config': FunctionInfo(11, ['channel'], ['int'], [{}], 'B', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_channel_status'}], 'B'),
		'set_channel_led_status_config': FunctionInfo(12, ['channel', 'min', 'max', 'config'], ['int', 'int', 'int', 'int'], [{}, {}, {}, {0: 'threshold', 1: 'intensity'}], 'B i i B', [], [], ''),
		'get_channel_led_status_config': FunctionInfo(13, ['channel'], ['int'], [{}], 'B', ['min', 'max', 'config'], [{}, {}, {0: 'threshold', 1: 'intensity'}], 'i i B'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'voltage': CallbackInfo(4, ['channel', 'voltage'], [{}, {}], 'B i', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 2; re[3] = 1; re[5] = 3; re[6] = 1; re[7] = 3; re[8] = 1; re[9] = 1; re[10] = 3; re[11] = 1; re[12] = 3; re[13] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class IndustrialDualRelayBricklet(MQTTCallbackDevice):
	functions = {
		'set_value': FunctionInfo(1, ['channel0', 'channel1'], ['bool', 'bool'], [{}, {}], '! !', [], [], ''),
		'get_value': FunctionInfo(2, [], [], [], '', ['channel0', 'channel1'], [{}, {}], '! !'),
		'set_monoflop': FunctionInfo(3, ['channel', 'value', 'time'], ['int', 'bool', 'int'], [{}, {}, {}], 'B ! I', [], [], ''),
		'get_monoflop': FunctionInfo(4, ['channel'], ['int'], [{}], 'B', ['value', 'time', 'time_remaining'], [{}, {}, {}], '! I I'),
		'set_selected_value': FunctionInfo(6, ['channel', 'value'], ['int', 'bool'], [{}, {}], 'B !', [], [], ''),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'monoflop_done': CallbackInfo(5, ['channel', 'value'], [{}, {}], 'B !', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 3; re[2] = 1; re[3] = 3; re[4] = 1; re[6] = 3; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class IndustrialQuadRelayBricklet(MQTTCallbackDevice):
	functions = {
		'set_value': FunctionInfo(1, ['value_mask'], ['int'], [{}], 'H', [], [], ''),
		'get_value': FunctionInfo(2, [], [], [], '', ['value_mask'], [{}], 'H'),
		'set_monoflop': FunctionInfo(3, ['selection_mask', 'value_mask', 'time'], ['int', 'int', 'int'], [{}, {}, {}], 'H H I', [], [], ''),
		'get_monoflop': FunctionInfo(4, ['pin'], ['int'], [{}], 'B', ['value', 'time', 'time_remaining'], [{}, {}, {}], 'H I I'),
		'set_group': FunctionInfo(5, ['group'], [('char', 4)], [{}], '4c', [], [], ''),
		'get_group': FunctionInfo(6, [], [], [], '', ['group'], [{}], '4c'),
		'get_available_for_group': FunctionInfo(7, [], [], [], '', ['available'], [{}], 'B'),
		'set_selected_values': FunctionInfo(9, ['selection_mask', 'value_mask'], ['int', 'int'], [{}, {}], 'H H', [], [], ''),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'monoflop_done': CallbackInfo(8, ['selection_mask', 'value_mask'], [{}, {}], 'H H', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 3; re[2] = 1; re[3] = 3; re[4] = 1; re[5] = 3; re[6] = 1; re[7] = 1; re[9] = 3; re[255] = 1

class IndustrialQuadRelayV2Bricklet(MQTTCallbackDevice):
	functions = {
		'set_value': FunctionInfo(1, ['value'], [('bool', 4)], [{}], '4!', [], [], ''),
		'get_value': FunctionInfo(2, [], [], [], '', ['value'], [{}], '4!'),
		'set_monoflop': FunctionInfo(3, ['channel', 'value', 'time'], ['int', 'bool', 'int'], [{}, {}, {}], 'B ! I', [], [], ''),
		'get_monoflop': FunctionInfo(4, ['channel'], ['int'], [{}], 'B', ['value', 'time', 'time_remaining'], [{}, {}, {}], '! I I'),
		'set_selected_value': FunctionInfo(5, ['channel', 'value'], ['int', 'bool'], [{}, {}], 'B !', [], [], ''),
		'set_channel_led_config': FunctionInfo(6, ['channel', 'config'], ['int', 'int'], [{}, {0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_channel_status'}], 'B B', [], [], ''),
		'get_channel_led_config': FunctionInfo(7, ['channel'], ['int'], [{}], 'B', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_channel_status'}], 'B'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'monoflop_done': CallbackInfo(8, ['channel', 'value'], [{}, {}], 'B !', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 3; re[2] = 1; re[3] = 3; re[4] = 1; re[5] = 3; re[6] = 3; re[7] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class IO16Bricklet(MQTTCallbackDevice):
	functions = {
		'set_port': FunctionInfo(1, ['port', 'value_mask'], ['char', 'int'], [{}, {}], 'c B', [], [], ''),
		'get_port': FunctionInfo(2, ['port'], ['char'], [{}], 'c', ['value_mask'], [{}], 'B'),
		'set_port_configuration': FunctionInfo(3, ['port', 'selection_mask', 'direction', 'value'], ['char', 'int', 'char', 'bool'], [{}, {}, {'i': 'in', 'o': 'out'}, {}], 'c B c !', [], [], ''),
		'get_port_configuration': FunctionInfo(4, ['port'], ['char'], [{}], 'c', ['direction_mask', 'value_mask'], [{}, {}], 'B B'),
		'set_debounce_period': FunctionInfo(5, ['debounce'], ['int'], [{}], 'I', [], [], ''),
		'get_debounce_period': FunctionInfo(6, [], [], [], '', ['debounce'], [{}], 'I'),
		'set_port_interrupt': FunctionInfo(7, ['port', 'interrupt_mask'], ['char', 'int'], [{}, {}], 'c B', [], [], ''),
		'get_port_interrupt': FunctionInfo(8, ['port'], ['char'], [{}], 'c', ['interrupt_mask'], [{}], 'B'),
		'set_port_monoflop': FunctionInfo(10, ['port', 'selection_mask', 'value_mask', 'time'], ['char', 'int', 'int', 'int'], [{}, {}, {}, {}], 'c B B I', [], [], ''),
		'get_port_monoflop': FunctionInfo(11, ['port', 'pin'], ['char', 'int'], [{}, {}], 'c B', ['value', 'time', 'time_remaining'], [{}, {}, {}], 'B I I'),
		'set_selected_values': FunctionInfo(13, ['port', 'selection_mask', 'value_mask'], ['char', 'int', 'int'], [{}, {}, {}], 'c B B', [], [], ''),
		'get_edge_count': FunctionInfo(14, ['pin', 'reset_counter'], ['int', 'bool'], [{}, {}], 'B !', ['count'], [{}], 'I'),
		'set_edge_count_config': FunctionInfo(15, ['pin', 'edge_type', 'debounce'], ['int', 'int', 'int'], [{}, {0: 'rising', 1: 'falling', 2: 'both'}, {}], 'B B B', [], [], ''),
		'get_edge_count_config': FunctionInfo(16, ['pin'], ['int'], [{}], 'B', ['edge_type', 'debounce'], [{0: 'rising', 1: 'falling', 2: 'both'}, {}], 'B B'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'interrupt': CallbackInfo(9, ['port', 'interrupt_mask', 'value_mask'], [{}, {}, {}], 'c B B', None),
		'monoflop_done': CallbackInfo(12, ['port', 'selection_mask', 'value_mask'], [{}, {}, {}], 'c B B', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 3; re[2] = 1; re[3] = 3; re[4] = 1; re[5] = 2; re[6] = 1; re[7] = 2; re[8] = 1; re[10] = 3; re[11] = 1; re[13] = 3; re[14] = 1; re[15] = 3; re[16] = 1; re[255] = 1

class IO16V2Bricklet(MQTTCallbackDevice):
	functions = {
		'set_value': FunctionInfo(1, ['value'], [('bool', 16)], [{}], '16!', [], [], ''),
		'get_value': FunctionInfo(2, [], [], [], '', ['value'], [{}], '16!'),
		'set_selected_value': FunctionInfo(3, ['channel', 'value'], ['int', 'bool'], [{}, {}], 'B !', [], [], ''),
		'set_configuration': FunctionInfo(4, ['channel', 'direction', 'value'], ['int', 'char', 'bool'], [{}, {'i': 'in', 'o': 'out'}, {}], 'B c !', [], [], ''),
		'get_configuration': FunctionInfo(5, ['channel'], ['int'], [{}], 'B', ['direction', 'value'], [{'i': 'in', 'o': 'out'}, {}], 'c !'),
		'set_input_value_callback_configuration': FunctionInfo(6, ['channel', 'period', 'value_has_to_change'], ['int', 'int', 'bool'], [{}, {}, {}], 'B I !', [], [], ''),
		'get_input_value_callback_configuration': FunctionInfo(7, ['channel'], ['int'], [{}], 'B', ['period', 'value_has_to_change'], [{}, {}], 'I !'),
		'set_all_input_value_callback_configuration': FunctionInfo(8, ['period', 'value_has_to_change'], ['int', 'bool'], [{}, {}], 'I !', [], [], ''),
		'get_all_input_value_callback_configuration': FunctionInfo(9, [], [], [], '', ['period', 'value_has_to_change'], [{}, {}], 'I !'),
		'set_monoflop': FunctionInfo(10, ['channel', 'value', 'time'], ['int', 'bool', 'int'], [{}, {}, {}], 'B ! I', [], [], ''),
		'get_monoflop': FunctionInfo(11, ['channel'], ['int'], [{}], 'B', ['value', 'time', 'time_remaining'], [{}, {}, {}], '! I I'),
		'get_edge_count': FunctionInfo(12, ['channel', 'reset_counter'], ['int', 'bool'], [{}, {}], 'B !', ['count'], [{}], 'I'),
		'set_edge_count_configuration': FunctionInfo(13, ['channel', 'edge_type', 'debounce'], ['int', 'int', 'int'], [{}, {0: 'rising', 1: 'falling', 2: 'both'}, {}], 'B B B', [], [], ''),
		'get_edge_count_configuration': FunctionInfo(14, ['channel'], ['int'], [{}], 'B', ['edge_type', 'debounce'], [{0: 'rising', 1: 'falling', 2: 'both'}, {}], 'B B'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'input_value': CallbackInfo(15, ['channel', 'changed', 'value'], [{}, {}, {}], 'B ! !', None),
		'all_input_value': CallbackInfo(16, ['changed', 'value'], [{}, {}], '16! 16!', None),
		'monoflop_done': CallbackInfo(17, ['channel', 'value'], [{}, {}], 'B !', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 3; re[2] = 1; re[3] = 3; re[4] = 3; re[5] = 1; re[6] = 2; re[7] = 1; re[8] = 2; re[9] = 1; re[10] = 3; re[11] = 1; re[12] = 1; re[13] = 3; re[14] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class IO4Bricklet(MQTTCallbackDevice):
	functions = {
		'set_value': FunctionInfo(1, ['value_mask'], ['int'], [{}], 'B', [], [], ''),
		'get_value': FunctionInfo(2, [], [], [], '', ['value_mask'], [{}], 'B'),
		'set_configuration': FunctionInfo(3, ['selection_mask', 'direction', 'value'], ['int', 'char', 'bool'], [{}, {'i': 'in', 'o': 'out'}, {}], 'B c !', [], [], ''),
		'get_configuration': FunctionInfo(4, [], [], [], '', ['direction_mask', 'value_mask'], [{}, {}], 'B B'),
		'set_debounce_period': FunctionInfo(5, ['debounce'], ['int'], [{}], 'I', [], [], ''),
		'get_debounce_period': FunctionInfo(6, [], [], [], '', ['debounce'], [{}], 'I'),
		'set_interrupt': FunctionInfo(7, ['interrupt_mask'], ['int'], [{}], 'B', [], [], ''),
		'get_interrupt': FunctionInfo(8, [], [], [], '', ['interrupt_mask'], [{}], 'B'),
		'set_monoflop': FunctionInfo(10, ['selection_mask', 'value_mask', 'time'], ['int', 'int', 'int'], [{}, {}, {}], 'B B I', [], [], ''),
		'get_monoflop': FunctionInfo(11, ['pin'], ['int'], [{}], 'B', ['value', 'time', 'time_remaining'], [{}, {}, {}], 'B I I'),
		'set_selected_values': FunctionInfo(13, ['selection_mask', 'value_mask'], ['int', 'int'], [{}, {}], 'B B', [], [], ''),
		'get_edge_count': FunctionInfo(14, ['pin', 'reset_counter'], ['int', 'bool'], [{}, {}], 'B !', ['count'], [{}], 'I'),
		'set_edge_count_config': FunctionInfo(15, ['selection_mask', 'edge_type', 'debounce'], ['int', 'int', 'int'], [{}, {0: 'rising', 1: 'falling', 2: 'both'}, {}], 'B B B', [], [], ''),
		'get_edge_count_config': FunctionInfo(16, ['pin'], ['int'], [{}], 'B', ['edge_type', 'debounce'], [{0: 'rising', 1: 'falling', 2: 'both'}, {}], 'B B'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'interrupt': CallbackInfo(9, ['interrupt_mask', 'value_mask'], [{}, {}], 'B B', None),
		'monoflop_done': CallbackInfo(12, ['selection_mask', 'value_mask'], [{}, {}], 'B B', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 3; re[2] = 1; re[3] = 3; re[4] = 1; re[5] = 2; re[6] = 1; re[7] = 2; re[8] = 1; re[10] = 3; re[11] = 1; re[13] = 3; re[14] = 1; re[15] = 3; re[16] = 1; re[255] = 1

class IO4V2Bricklet(MQTTCallbackDevice):
	functions = {
		'set_value': FunctionInfo(1, ['value'], [('bool', 4)], [{}], '4!', [], [], ''),
		'get_value': FunctionInfo(2, [], [], [], '', ['value'], [{}], '4!'),
		'set_selected_value': FunctionInfo(3, ['channel', 'value'], ['int', 'bool'], [{}, {}], 'B !', [], [], ''),
		'set_configuration': FunctionInfo(4, ['channel', 'direction', 'value'], ['int', 'char', 'bool'], [{}, {'i': 'in', 'o': 'out'}, {}], 'B c !', [], [], ''),
		'get_configuration': FunctionInfo(5, ['channel'], ['int'], [{}], 'B', ['direction', 'value'], [{'i': 'in', 'o': 'out'}, {}], 'c !'),
		'set_input_value_callback_configuration': FunctionInfo(6, ['channel', 'period', 'value_has_to_change'], ['int', 'int', 'bool'], [{}, {}, {}], 'B I !', [], [], ''),
		'get_input_value_callback_configuration': FunctionInfo(7, ['channel'], ['int'], [{}], 'B', ['period', 'value_has_to_change'], [{}, {}], 'I !'),
		'set_all_input_value_callback_configuration': FunctionInfo(8, ['period', 'value_has_to_change'], ['int', 'bool'], [{}, {}], 'I !', [], [], ''),
		'get_all_input_value_callback_configuration': FunctionInfo(9, [], [], [], '', ['period', 'value_has_to_change'], [{}, {}], 'I !'),
		'set_monoflop': FunctionInfo(10, ['channel', 'value', 'time'], ['int', 'bool', 'int'], [{}, {}, {}], 'B ! I', [], [], ''),
		'get_monoflop': FunctionInfo(11, ['channel'], ['int'], [{}], 'B', ['value', 'time', 'time_remaining'], [{}, {}, {}], '! I I'),
		'get_edge_count': FunctionInfo(12, ['channel', 'reset_counter'], ['int', 'bool'], [{}, {}], 'B !', ['count'], [{}], 'I'),
		'set_edge_count_configuration': FunctionInfo(13, ['channel', 'edge_type', 'debounce'], ['int', 'int', 'int'], [{}, {0: 'rising', 1: 'falling', 2: 'both'}, {}], 'B B B', [], [], ''),
		'get_edge_count_configuration': FunctionInfo(14, ['channel'], ['int'], [{}], 'B', ['edge_type', 'debounce'], [{0: 'rising', 1: 'falling', 2: 'both'}, {}], 'B B'),
		'set_pwm_configuration': FunctionInfo(15, ['channel', 'frequency', 'duty_cycle'], ['int', 'int', 'int'], [{}, {}, {}], 'B I H', [], [], ''),
		'get_pwm_configuration': FunctionInfo(16, ['channel'], ['int'], [{}], 'B', ['frequency', 'duty_cycle'], [{}, {}], 'I H'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'input_value': CallbackInfo(17, ['channel', 'changed', 'value'], [{}, {}, {}], 'B ! !', None),
		'all_input_value': CallbackInfo(18, ['changed', 'value'], [{}, {}], '4! 4!', None),
		'monoflop_done': CallbackInfo(19, ['channel', 'value'], [{}, {}], 'B !', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 3; re[2] = 1; re[3] = 3; re[4] = 3; re[5] = 1; re[6] = 2; re[7] = 1; re[8] = 2; re[9] = 1; re[10] = 3; re[11] = 1; re[12] = 1; re[13] = 3; re[14] = 1; re[15] = 3; re[16] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class IsolatorBricklet(MQTTCallbackDevice):
	functions = {
		'get_statistics': FunctionInfo(1, [], [], [], '', ['messages_from_brick', 'messages_from_bricklet', 'connected_bricklet_device_identifier', 'connected_bricklet_uid'], [{}, {}, {}, {}], 'I I H 8s'),
		'set_spitfp_baudrate_config': FunctionInfo(2, ['enable_dynamic_baudrate', 'minimum_dynamic_baudrate'], ['bool', 'int'], [{}, {}], '! I', [], [], ''),
		'get_spitfp_baudrate_config': FunctionInfo(3, [], [], [], '', ['enable_dynamic_baudrate', 'minimum_dynamic_baudrate'], [{}, {}], '! I'),
		'set_spitfp_baudrate': FunctionInfo(4, ['baudrate'], ['int'], [{}], 'I', [], [], ''),
		'get_spitfp_baudrate': FunctionInfo(5, [], [], [], '', ['baudrate'], [{}], 'I'),
		'get_isolator_spitfp_error_count': FunctionInfo(6, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_statistics_callback_configuration': FunctionInfo(7, ['period', 'value_has_to_change'], ['int', 'bool'], [{}, {}], 'I !', [], [], ''),
		'get_statistics_callback_configuration': FunctionInfo(8, [], [], [], '', ['period', 'value_has_to_change'], [{}, {}], 'I !'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'statistics': CallbackInfo(9, ['messages_from_brick', 'messages_from_bricklet', 'connected_bricklet_device_identifier', 'connected_bricklet_uid'], [{}, {}, {}, {}], 'I I H 8s', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 3; re[3] = 1; re[4] = 3; re[5] = 1; re[6] = 1; re[7] = 2; re[8] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class JoystickBricklet(MQTTCallbackDevice):
	functions = {
		'get_position': FunctionInfo(1, [], [], [], '', ['x', 'y'], [{}, {}], 'h h'),
		'is_pressed': FunctionInfo(2, [], [], [], '', ['pressed'], [{}], '!'),
		'get_analog_value': FunctionInfo(3, [], [], [], '', ['x', 'y'], [{}, {}], 'H H'),
		'calibrate': FunctionInfo(4, [], [], [], '', [], [], ''),
		'set_position_callback_period': FunctionInfo(5, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_position_callback_period': FunctionInfo(6, [], [], [], '', ['period'], [{}], 'I'),
		'set_analog_value_callback_period': FunctionInfo(7, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_analog_value_callback_period': FunctionInfo(8, [], [], [], '', ['period'], [{}], 'I'),
		'set_position_callback_threshold': FunctionInfo(9, ['option', 'min_x', 'max_x', 'min_y', 'max_y'], ['char', 'int', 'int', 'int', 'int'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}, {}, {}], 'c h h h h', [], [], ''),
		'get_position_callback_threshold': FunctionInfo(10, [], [], [], '', ['option', 'min_x', 'max_x', 'min_y', 'max_y'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}, {}, {}], 'c h h h h'),
		'set_analog_value_callback_threshold': FunctionInfo(11, ['option', 'min_x', 'max_x', 'min_y', 'max_y'], ['char', 'int', 'int', 'int', 'int'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}, {}, {}], 'c H H H H', [], [], ''),
		'get_analog_value_callback_threshold': FunctionInfo(12, [], [], [], '', ['option', 'min_x', 'max_x', 'min_y', 'max_y'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}, {}, {}], 'c H H H H'),
		'set_debounce_period': FunctionInfo(13, ['debounce'], ['int'], [{}], 'I', [], [], ''),
		'get_debounce_period': FunctionInfo(14, [], [], [], '', ['debounce'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'position': CallbackInfo(15, ['x', 'y'], [{}, {}], 'h h', None),
		'analog_value': CallbackInfo(16, ['x', 'y'], [{}, {}], 'H H', None),
		'position_reached': CallbackInfo(17, ['x', 'y'], [{}, {}], 'h h', None),
		'analog_value_reached': CallbackInfo(18, ['x', 'y'], [{}, {}], 'H H', None),
		'pressed': CallbackInfo(19, [], [], '', None),
		'released': CallbackInfo(20, [], [], '', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 1; re[3] = 1; re[4] = 3; re[5] = 2; re[6] = 1; re[7] = 2; re[8] = 1; re[9] = 2; re[10] = 1; re[11] = 2; re[12] = 1; re[13] = 2; re[14] = 1; re[255] = 1

class JoystickV2Bricklet(MQTTCallbackDevice):
	functions = {
		'get_position': FunctionInfo(1, [], [], [], '', ['x', 'y'], [{}, {}], 'h h'),
		'is_pressed': FunctionInfo(2, [], [], [], '', ['pressed'], [{}], '!'),
		'calibrate': FunctionInfo(3, [], [], [], '', [], [], ''),
		'set_position_callback_configuration': FunctionInfo(4, ['period', 'value_has_to_change'], ['int', 'bool'], [{}, {}], 'I !', [], [], ''),
		'get_position_callback_configuration': FunctionInfo(5, [], [], [], '', ['period', 'value_has_to_change'], [{}, {}], 'I !'),
		'set_pressed_callback_configuration': FunctionInfo(7, ['period', 'value_has_to_change'], ['int', 'bool'], [{}, {}], 'I !', [], [], ''),
		'get_pressed_callback_configuration': FunctionInfo(8, [], [], [], '', ['period', 'value_has_to_change'], [{}, {}], 'I !'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'position': CallbackInfo(6, ['x', 'y'], [{}, {}], 'h h', None),
		'pressed': CallbackInfo(9, ['pressed'], [{}], '!', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 1; re[3] = 3; re[4] = 2; re[5] = 1; re[7] = 2; re[8] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class LaserRangeFinderBricklet(MQTTCallbackDevice):
	functions = {
		'get_distance': FunctionInfo(1, [], [], [], '', ['distance'], [{}], 'H'),
		'get_velocity': FunctionInfo(2, [], [], [], '', ['velocity'], [{}], 'h'),
		'set_distance_callback_period': FunctionInfo(3, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_distance_callback_period': FunctionInfo(4, [], [], [], '', ['period'], [{}], 'I'),
		'set_velocity_callback_period': FunctionInfo(5, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_velocity_callback_period': FunctionInfo(6, [], [], [], '', ['period'], [{}], 'I'),
		'set_distance_callback_threshold': FunctionInfo(7, ['option', 'min', 'max'], ['char', 'int', 'int'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c H H', [], [], ''),
		'get_distance_callback_threshold': FunctionInfo(8, [], [], [], '', ['option', 'min', 'max'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c H H'),
		'set_velocity_callback_threshold': FunctionInfo(9, ['option', 'min', 'max'], ['char', 'int', 'int'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c h h', [], [], ''),
		'get_velocity_callback_threshold': FunctionInfo(10, [], [], [], '', ['option', 'min', 'max'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c h h'),
		'set_debounce_period': FunctionInfo(11, ['debounce'], ['int'], [{}], 'I', [], [], ''),
		'get_debounce_period': FunctionInfo(12, [], [], [], '', ['debounce'], [{}], 'I'),
		'set_moving_average': FunctionInfo(13, ['distance_average_length', 'velocity_average_length'], ['int', 'int'], [{}, {}], 'B B', [], [], ''),
		'get_moving_average': FunctionInfo(14, [], [], [], '', ['distance_average_length', 'velocity_average_length'], [{}, {}], 'B B'),
		'set_mode': FunctionInfo(15, ['mode'], ['int'], [{0: 'distance', 1: 'velocity_max_13ms', 2: 'velocity_max_32ms', 3: 'velocity_max_64ms', 4: 'velocity_max_127ms'}], 'B', [], [], ''),
		'get_mode': FunctionInfo(16, [], [], [], '', ['mode'], [{0: 'distance', 1: 'velocity_max_13ms', 2: 'velocity_max_32ms', 3: 'velocity_max_64ms', 4: 'velocity_max_127ms'}], 'B'),
		'enable_laser': FunctionInfo(17, [], [], [], '', [], [], ''),
		'disable_laser': FunctionInfo(18, [], [], [], '', [], [], ''),
		'is_laser_enabled': FunctionInfo(19, [], [], [], '', ['laser_enabled'], [{}], '!'),
		'get_sensor_hardware_version': FunctionInfo(24, [], [], [], '', ['version'], [{1: '1', 3: '3'}], 'B'),
		'set_configuration': FunctionInfo(25, ['acquisition_count', 'enable_quick_termination', 'threshold_value', 'measurement_frequency'], ['int', 'bool', 'int', 'int'], [{}, {}, {}, {}], 'B ! B H', [], [], ''),
		'get_configuration': FunctionInfo(26, [], [], [], '', ['acquisition_count', 'enable_quick_termination', 'threshold_value', 'measurement_frequency'], [{}, {}, {}, {}], 'B ! B H'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'distance': CallbackInfo(20, ['distance'], [{}], 'H', None),
		'velocity': CallbackInfo(21, ['velocity'], [{}], 'h', None),
		'distance_reached': CallbackInfo(22, ['distance'], [{}], 'H', None),
		'velocity_reached': CallbackInfo(23, ['velocity'], [{}], 'h', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 1; re[3] = 2; re[4] = 1; re[5] = 2; re[6] = 1; re[7] = 2; re[8] = 1; re[9] = 2; re[10] = 1; re[11] = 2; re[12] = 1; re[13] = 3; re[14] = 1; re[15] = 3; re[16] = 1; re[17] = 3; re[18] = 3; re[19] = 1; re[24] = 1; re[25] = 3; re[26] = 1; re[255] = 1

class LaserRangeFinderV2Bricklet(MQTTCallbackDevice):
	functions = {
		'get_distance': FunctionInfo(1, [], [], [], '', ['distance'], [{}], 'h'),
		'set_distance_callback_configuration': FunctionInfo(2, ['period', 'value_has_to_change', 'option', 'min', 'max'], ['int', 'bool', 'char', 'int', 'int'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c h h', [], [], ''),
		'get_distance_callback_configuration': FunctionInfo(3, [], [], [], '', ['period', 'value_has_to_change', 'option', 'min', 'max'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c h h'),
		'get_velocity': FunctionInfo(5, [], [], [], '', ['velocity'], [{}], 'h'),
		'set_velocity_callback_configuration': FunctionInfo(6, ['period', 'value_has_to_change', 'option', 'min', 'max'], ['int', 'bool', 'char', 'int', 'int'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c h h', [], [], ''),
		'get_velocity_callback_configuration': FunctionInfo(7, [], [], [], '', ['period', 'value_has_to_change', 'option', 'min', 'max'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c h h'),
		'set_enable': FunctionInfo(9, ['enable'], ['bool'], [{}], '!', [], [], ''),
		'get_enable': FunctionInfo(10, [], [], [], '', ['enable'], [{}], '!'),
		'set_configuration': FunctionInfo(11, ['acquisition_count', 'enable_quick_termination', 'threshold_value', 'measurement_frequency'], ['int', 'bool', 'int', 'int'], [{}, {}, {}, {}], 'B ! B H', [], [], ''),
		'get_configuration': FunctionInfo(12, [], [], [], '', ['acquisition_count', 'enable_quick_termination', 'threshold_value', 'measurement_frequency'], [{}, {}, {}, {}], 'B ! B H'),
		'set_moving_average': FunctionInfo(13, ['distance_average_length', 'velocity_average_length'], ['int', 'int'], [{}, {}], 'B B', [], [], ''),
		'get_moving_average': FunctionInfo(14, [], [], [], '', ['distance_average_length', 'velocity_average_length'], [{}, {}], 'B B'),
		'set_offset_calibration': FunctionInfo(15, ['offset'], ['int'], [{}], 'h', [], [], ''),
		'get_offset_calibration': FunctionInfo(16, [], [], [], '', ['offset'], [{}], 'h'),
		'set_distance_led_config': FunctionInfo(17, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_distance'}], 'B', [], [], ''),
		'get_distance_led_config': FunctionInfo(18, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_distance'}], 'B'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'distance': CallbackInfo(4, ['distance'], [{}], 'h', None),
		'velocity': CallbackInfo(8, ['velocity'], [{}], 'h', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 2; re[3] = 1; re[5] = 1; re[6] = 2; re[7] = 1; re[9] = 3; re[10] = 1; re[11] = 3; re[12] = 1; re[13] = 3; re[14] = 1; re[15] = 3; re[16] = 1; re[17] = 3; re[18] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class LCD128x64Bricklet(MQTTCallbackDevice):
	functions = {
		'write_pixels_low_level': FunctionInfo(1, ['x_start', 'y_start', 'x_end', 'y_end', 'pixels_length', 'pixels_chunk_offset', 'pixels_chunk_data'], ['int', 'int', 'int', 'int', 'int', 'int', ('bool', 448)], [{}, {}, {}, {}, {}, {}, {}], 'B B B B H H 448!', [], [], ''),
		'write_pixels': HighLevelFunctionInfo(1, 'in', [None, None, None, None, 'stream_data'], [], [None, None, None, None, 'stream_length', 'stream_chunk_offset', 'stream_chunk_data'], [], ['x_start', 'y_start', 'x_end', 'y_end', 'pixels'], ['int', 'int', 'int', 'int', ('bool', -65535)], [{}, {}, {}, {}, {}], 'B B B B H H 448!', [], [], '','0', 448, None,False, False, None),
		'read_pixels_low_level': FunctionInfo(2, ['x_start', 'y_start', 'x_end', 'y_end'], ['int', 'int', 'int', 'int'], [{}, {}, {}, {}], 'B B B B', ['pixels_length', 'pixels_chunk_offset', 'pixels_chunk_data'], [{}, {}, {}], 'H H 480!'),
		'read_pixels': HighLevelFunctionInfo(2, 'out', [None, None, None, None], ['stream_data'], [None, None, None, None], ['stream_length', 'stream_chunk_offset', 'stream_chunk_data'], ['x_start', 'y_start', 'x_end', 'y_end'], ['int', 'int', 'int', 'int'], [{}, {}, {}, {}], 'B B B B', ['pixels'], [{}], 'H H 480!',None, 480, None,False, False, None),
		'clear_display': FunctionInfo(3, [], [], [], '', [], [], ''),
		'set_display_configuration': FunctionInfo(4, ['contrast', 'backlight', 'invert', 'automatic_draw'], ['int', 'int', 'bool', 'bool'], [{}, {}, {}, {}], 'B B ! !', [], [], ''),
		'get_display_configuration': FunctionInfo(5, [], [], [], '', ['contrast', 'backlight', 'invert', 'automatic_draw'], [{}, {}, {}, {}], 'B B ! !'),
		'write_line': FunctionInfo(6, ['line', 'position', 'text'], ['int', 'int', 'string'], [{}, {}, {}], 'B B 22s', [], [], ''),
		'draw_buffered_frame': FunctionInfo(7, ['force_complete_redraw'], ['bool'], [{}], '!', [], [], ''),
		'get_touch_position': FunctionInfo(8, [], [], [], '', ['pressure', 'x', 'y', 'age'], [{}, {}, {}, {}], 'H H H I'),
		'set_touch_position_callback_configuration': FunctionInfo(9, ['period', 'value_has_to_change'], ['int', 'bool'], [{}, {}], 'I !', [], [], ''),
		'get_touch_position_callback_configuration': FunctionInfo(10, [], [], [], '', ['period', 'value_has_to_change'], [{}, {}], 'I !'),
		'get_touch_gesture': FunctionInfo(12, [], [], [], '', ['gesture', 'duration', 'pressure_max', 'x_start', 'y_start', 'x_end', 'y_end', 'age'], [{0: 'left_to_right', 1: 'right_to_left', 2: 'top_to_bottom', 3: 'bottom_to_top'}, {}, {}, {}, {}, {}, {}, {}], 'B I H H H H H I'),
		'set_touch_gesture_callback_configuration': FunctionInfo(13, ['period', 'value_has_to_change'], ['int', 'bool'], [{}, {}], 'I !', [], [], ''),
		'get_touch_gesture_callback_configuration': FunctionInfo(14, [], [], [], '', ['period', 'value_has_to_change'], [{}, {}], 'I !'),
		'draw_line': FunctionInfo(16, ['position_x_start', 'position_y_start', 'position_x_end', 'position_y_end', 'color'], ['int', 'int', 'int', 'int', 'bool'], [{}, {}, {}, {}, {False: 'white', True: 'black'}], 'B B B B !', [], [], ''),
		'draw_box': FunctionInfo(17, ['position_x_start', 'position_y_start', 'position_x_end', 'position_y_end', 'fill', 'color'], ['int', 'int', 'int', 'int', 'bool', 'bool'], [{}, {}, {}, {}, {}, {False: 'white', True: 'black'}], 'B B B B ! !', [], [], ''),
		'draw_text': FunctionInfo(18, ['position_x', 'position_y', 'font', 'color', 'text'], ['int', 'int', 'int', 'bool', 'string'], [{}, {}, {0: '6x8', 1: '6x16', 2: '6x24', 3: '6x32', 4: '12x16', 5: '12x24', 6: '12x32', 7: '18x24', 8: '18x32', 9: '24x32'}, {False: 'white', True: 'black'}, {}], 'B B B ! 22s', [], [], ''),
		'set_gui_button': FunctionInfo(19, ['index', 'position_x', 'position_y', 'width', 'height', 'text'], ['int', 'int', 'int', 'int', 'int', 'string'], [{}, {}, {}, {}, {}, {}], 'B B B B B 16s', [], [], ''),
		'get_gui_button': FunctionInfo(20, ['index'], ['int'], [{}], 'B', ['active', 'position_x', 'position_y', 'width', 'height', 'text'], [{}, {}, {}, {}, {}, {}], '! B B B B 16s'),
		'remove_gui_button': FunctionInfo(21, ['index'], ['int'], [{}], 'B', [], [], ''),
		'set_gui_button_pressed_callback_configuration': FunctionInfo(22, ['period', 'value_has_to_change'], ['int', 'bool'], [{}, {}], 'I !', [], [], ''),
		'get_gui_button_pressed_callback_configuration': FunctionInfo(23, [], [], [], '', ['period', 'value_has_to_change'], [{}, {}], 'I !'),
		'get_gui_button_pressed': FunctionInfo(24, ['index'], ['int'], [{}], 'B', ['pressed'], [{}], '!'),
		'set_gui_slider': FunctionInfo(26, ['index', 'position_x', 'position_y', 'length', 'direction', 'value'], ['int', 'int', 'int', 'int', 'int', 'int'], [{}, {}, {}, {}, {0: 'horizontal', 1: 'vertical'}, {}], 'B B B B B B', [], [], ''),
		'get_gui_slider': FunctionInfo(27, ['index'], ['int'], [{}], 'B', ['active', 'position_x', 'position_y', 'length', 'direction', 'value'], [{}, {}, {}, {}, {0: 'horizontal', 1: 'vertical'}, {}], '! B B B B B'),
		'remove_gui_slider': FunctionInfo(28, ['index'], ['int'], [{}], 'B', [], [], ''),
		'set_gui_slider_value_callback_configuration': FunctionInfo(29, ['period', 'value_has_to_change'], ['int', 'bool'], [{}, {}], 'I !', [], [], ''),
		'get_gui_slider_value_callback_configuration': FunctionInfo(30, [], [], [], '', ['period', 'value_has_to_change'], [{}, {}], 'I !'),
		'get_gui_slider_value': FunctionInfo(31, ['index'], ['int'], [{}], 'B', ['value'], [{}], 'B'),
		'set_gui_tab_configuration': FunctionInfo(33, ['change_tab_config', 'clear_gui'], ['int', 'bool'], [{1: 'click', 2: 'swipe', 3: 'click_and_swipe'}, {}], 'B !', [], [], ''),
		'get_gui_tab_configuration': FunctionInfo(34, [], [], [], '', ['change_tab_config', 'clear_gui'], [{1: 'click', 2: 'swipe', 3: 'click_and_swipe'}, {}], 'B !'),
		'set_gui_tab_text': FunctionInfo(35, ['index', 'text'], ['int', 'string'], [{}, {}], 'B 5s', [], [], ''),
		'get_gui_tab_text': FunctionInfo(36, ['index'], ['int'], [{}], 'B', ['active', 'text'], [{}, {}], '! 5s'),
		'set_gui_tab_icon': FunctionInfo(37, ['index', 'icon'], ['int', ('bool', 168)], [{}, {}], 'B 168!', [], [], ''),
		'get_gui_tab_icon': FunctionInfo(38, ['index'], ['int'], [{}], 'B', ['active', 'icon'], [{}, {}], '! 168!'),
		'remove_gui_tab': FunctionInfo(39, ['index'], ['int'], [{}], 'B', [], [], ''),
		'set_gui_tab_selected': FunctionInfo(40, ['index'], ['int'], [{}], 'B', [], [], ''),
		'set_gui_tab_selected_callback_configuration': FunctionInfo(41, ['period', 'value_has_to_change'], ['int', 'bool'], [{}, {}], 'I !', [], [], ''),
		'get_gui_tab_selected_callback_configuration': FunctionInfo(42, [], [], [], '', ['period', 'value_has_to_change'], [{}, {}], 'I !'),
		'get_gui_tab_selected': FunctionInfo(43, [], [], [], '', ['index'], [{}], 'b'),
		'set_gui_graph_configuration': FunctionInfo(45, ['index', 'graph_type', 'position_x', 'position_y', 'width', 'height', 'text_x', 'text_y'], ['int', 'int', 'int', 'int', 'int', 'int', 'string', 'string'], [{}, {0: 'dot', 1: 'line', 2: 'bar'}, {}, {}, {}, {}, {}, {}], 'B B B B B B 4s 4s', [], [], ''),
		'get_gui_graph_configuration': FunctionInfo(46, ['index'], ['int'], [{}], 'B', ['active', 'graph_type', 'position_x', 'position_y', 'width', 'height', 'text_x', 'text_y'], [{}, {0: 'dot', 1: 'line', 2: 'bar'}, {}, {}, {}, {}, {}, {}], '! B B B B B 4s 4s'),
		'set_gui_graph_data_low_level': FunctionInfo(47, ['index', 'data_length', 'data_chunk_offset', 'data_chunk_data'], ['int', 'int', 'int', ('int', 59)], [{}, {}, {}, {}], 'B H H 59B', [], [], ''),
		'set_gui_graph_data': HighLevelFunctionInfo(47, 'in', [None, 'stream_data'], [], [None, 'stream_length', 'stream_chunk_offset', 'stream_chunk_data'], [], ['index', 'data'], ['int', ('int', -65535)], [{}, {}], 'B H H 59B', [], [], '','0', 59, None,False, False, None),
		'get_gui_graph_data_low_level': FunctionInfo(48, ['index'], ['int'], [{}], 'B', ['data_length', 'data_chunk_offset', 'data_chunk_data'], [{}, {}, {}], 'H H 59B'),
		'get_gui_graph_data': HighLevelFunctionInfo(48, 'out', [None], ['stream_data'], [None], ['stream_length', 'stream_chunk_offset', 'stream_chunk_data'], ['index'], ['int'], [{}], 'B', ['data'], [{}], 'H H 59B',None, 59, None,False, False, None),
		'remove_gui_graph': FunctionInfo(49, ['index'], ['int'], [{}], 'B', [], [], ''),
		'remove_all_gui': FunctionInfo(50, [], [], [], '', [], [], ''),
		'set_touch_led_config': FunctionInfo(51, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_touch'}], 'B', [], [], ''),
		'get_touch_led_config': FunctionInfo(52, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_touch'}], 'B'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'touch_position': CallbackInfo(11, ['pressure', 'x', 'y', 'age'], [{}, {}, {}, {}], 'H H H I', None),
		'touch_gesture': CallbackInfo(15, ['gesture', 'duration', 'pressure_max', 'x_start', 'y_start', 'x_end', 'y_end', 'age'], [{0: 'left_to_right', 1: 'right_to_left', 2: 'top_to_bottom', 3: 'bottom_to_top'}, {}, {}, {}, {}, {}, {}, {}], 'B I H H H H H I', None),
		'gui_button_pressed': CallbackInfo(25, ['index', 'pressed'], [{}, {}], 'B !', None),
		'gui_slider_value': CallbackInfo(32, ['index', 'value'], [{}, {}], 'B B', None),
		'gui_tab_selected': CallbackInfo(44, ['index'], [{}], 'b', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 2; re[2] = 1; re[3] = 3; re[4] = 3; re[5] = 1; re[6] = 3; re[7] = 3; re[8] = 1; re[9] = 2; re[10] = 1; re[12] = 1; re[13] = 2; re[14] = 1; re[16] = 3; re[17] = 3; re[18] = 3; re[19] = 3; re[20] = 1; re[21] = 3; re[22] = 2; re[23] = 1; re[24] = 1; re[26] = 3; re[27] = 1; re[28] = 3; re[29] = 2; re[30] = 1; re[31] = 1; re[33] = 3; re[34] = 1; re[35] = 3; re[36] = 1; re[37] = 3; re[38] = 1; re[39] = 3; re[40] = 3; re[41] = 2; re[42] = 1; re[43] = 1; re[45] = 3; re[46] = 1; re[47] = 2; re[48] = 1; re[49] = 3; re[50] = 3; re[51] = 3; re[52] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class LCD16x2Bricklet(MQTTCallbackDevice):
	functions = {
		'write_line': FunctionInfo(1, ['line', 'position', 'text'], ['int', 'int', 'string'], [{}, {}, {}], 'B B 16s', [], [], ''),
		'clear_display': FunctionInfo(2, [], [], [], '', [], [], ''),
		'backlight_on': FunctionInfo(3, [], [], [], '', [], [], ''),
		'backlight_off': FunctionInfo(4, [], [], [], '', [], [], ''),
		'is_backlight_on': FunctionInfo(5, [], [], [], '', ['backlight'], [{}], '!'),
		'set_config': FunctionInfo(6, ['cursor', 'blinking'], ['bool', 'bool'], [{}, {}], '! !', [], [], ''),
		'get_config': FunctionInfo(7, [], [], [], '', ['cursor', 'blinking'], [{}, {}], '! !'),
		'is_button_pressed': FunctionInfo(8, ['button'], ['int'], [{}], 'B', ['pressed'], [{}], '!'),
		'set_custom_character': FunctionInfo(11, ['index', 'character'], ['int', ('int', 8)], [{}, {}], 'B 8B', [], [], ''),
		'get_custom_character': FunctionInfo(12, ['index'], ['int'], [{}], 'B', ['character'], [{}], '8B'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'button_pressed': CallbackInfo(9, ['button'], [{}], 'B', None),
		'button_released': CallbackInfo(10, ['button'], [{}], 'B', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 3; re[2] = 3; re[3] = 3; re[4] = 3; re[5] = 1; re[6] = 3; re[7] = 1; re[8] = 1; re[11] = 3; re[12] = 1; re[255] = 1

class LCD20x4Bricklet(MQTTCallbackDevice):
	functions = {
		'write_line': FunctionInfo(1, ['line', 'position', 'text'], ['int', 'int', 'string'], [{}, {}, {}], 'B B 20s', [], [], ''),
		'clear_display': FunctionInfo(2, [], [], [], '', [], [], ''),
		'backlight_on': FunctionInfo(3, [], [], [], '', [], [], ''),
		'backlight_off': FunctionInfo(4, [], [], [], '', [], [], ''),
		'is_backlight_on': FunctionInfo(5, [], [], [], '', ['backlight'], [{}], '!'),
		'set_config': FunctionInfo(6, ['cursor', 'blinking'], ['bool', 'bool'], [{}, {}], '! !', [], [], ''),
		'get_config': FunctionInfo(7, [], [], [], '', ['cursor', 'blinking'], [{}, {}], '! !'),
		'is_button_pressed': FunctionInfo(8, ['button'], ['int'], [{}], 'B', ['pressed'], [{}], '!'),
		'set_custom_character': FunctionInfo(11, ['index', 'character'], ['int', ('int', 8)], [{}, {}], 'B 8B', [], [], ''),
		'get_custom_character': FunctionInfo(12, ['index'], ['int'], [{}], 'B', ['character'], [{}], '8B'),
		'set_default_text': FunctionInfo(13, ['line', 'text'], ['int', 'string'], [{}, {}], 'B 20s', [], [], ''),
		'get_default_text': FunctionInfo(14, ['line'], ['int'], [{}], 'B', ['text'], [{}], '20s'),
		'set_default_text_counter': FunctionInfo(15, ['counter'], ['int'], [{}], 'i', [], [], ''),
		'get_default_text_counter': FunctionInfo(16, [], [], [], '', ['counter'], [{}], 'i'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'button_pressed': CallbackInfo(9, ['button'], [{}], 'B', None),
		'button_released': CallbackInfo(10, ['button'], [{}], 'B', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 3; re[2] = 3; re[3] = 3; re[4] = 3; re[5] = 1; re[6] = 3; re[7] = 1; re[8] = 1; re[11] = 3; re[12] = 1; re[13] = 3; re[14] = 1; re[15] = 3; re[16] = 1; re[255] = 1

class LEDStripBricklet(MQTTCallbackDevice):
	functions = {
		'set_rgb_values': FunctionInfo(1, ['index', 'length', 'r', 'g', 'b'], ['int', 'int', ('int', 16), ('int', 16), ('int', 16)], [{}, {}, {}, {}, {}], 'H B 16B 16B 16B', [], [], ''),
		'get_rgb_values': FunctionInfo(2, ['index', 'length'], ['int', 'int'], [{}, {}], 'H B', ['r', 'g', 'b'], [{}, {}, {}], '16B 16B 16B'),
		'set_frame_duration': FunctionInfo(3, ['duration'], ['int'], [{}], 'H', [], [], ''),
		'get_frame_duration': FunctionInfo(4, [], [], [], '', ['duration'], [{}], 'H'),
		'get_supply_voltage': FunctionInfo(5, [], [], [], '', ['voltage'], [{}], 'H'),
		'set_clock_frequency': FunctionInfo(7, ['frequency'], ['int'], [{}], 'I', [], [], ''),
		'get_clock_frequency': FunctionInfo(8, [], [], [], '', ['frequency'], [{}], 'I'),
		'set_chip_type': FunctionInfo(9, ['chip'], ['int'], [{2801: 'ws2801', 2811: 'ws2811', 2812: 'ws2812', 8806: 'lpd8806', 102: 'apa102'}], 'H', [], [], ''),
		'get_chip_type': FunctionInfo(10, [], [], [], '', ['chip'], [{2801: 'ws2801', 2811: 'ws2811', 2812: 'ws2812', 8806: 'lpd8806', 102: 'apa102'}], 'H'),
		'set_rgbw_values': FunctionInfo(11, ['index', 'length', 'r', 'g', 'b', 'w'], ['int', 'int', ('int', 12), ('int', 12), ('int', 12), ('int', 12)], [{}, {}, {}, {}, {}, {}], 'H B 12B 12B 12B 12B', [], [], ''),
		'get_rgbw_values': FunctionInfo(12, ['index', 'length'], ['int', 'int'], [{}, {}], 'H B', ['r', 'g', 'b', 'w'], [{}, {}, {}, {}], '12B 12B 12B 12B'),
		'set_channel_mapping': FunctionInfo(13, ['mapping'], ['int'], [{6: 'rgb', 9: 'rbg', 33: 'brg', 36: 'bgr', 18: 'grb', 24: 'gbr', 27: 'rgbw', 30: 'rgwb', 39: 'rbgw', 45: 'rbwg', 54: 'rwgb', 57: 'rwbg', 78: 'grwb', 75: 'grbw', 108: 'gbwr', 99: 'gbrw', 120: 'gwbr', 114: 'gwrb', 135: 'brgw', 141: 'brwg', 147: 'bgrw', 156: 'bgwr', 177: 'bwrg', 180: 'bwgr', 201: 'wrbg', 198: 'wrgb', 216: 'wgbr', 210: 'wgrb', 228: 'wbgr', 225: 'wbrg'}], 'B', [], [], ''),
		'get_channel_mapping': FunctionInfo(14, [], [], [], '', ['mapping'], [{6: 'rgb', 9: 'rbg', 33: 'brg', 36: 'bgr', 18: 'grb', 24: 'gbr', 27: 'rgbw', 30: 'rgwb', 39: 'rbgw', 45: 'rbwg', 54: 'rwgb', 57: 'rwbg', 78: 'grwb', 75: 'grbw', 108: 'gbwr', 99: 'gbrw', 120: 'gwbr', 114: 'gwrb', 135: 'brgw', 141: 'brwg', 147: 'bgrw', 156: 'bgwr', 177: 'bwrg', 180: 'bwgr', 201: 'wrbg', 198: 'wrgb', 216: 'wgbr', 210: 'wgrb', 228: 'wbgr', 225: 'wbrg'}], 'B'),
		'enable_frame_rendered_callback': FunctionInfo(15, [], [], [], '', [], [], ''),
		'disable_frame_rendered_callback': FunctionInfo(16, [], [], [], '', [], [], ''),
		'is_frame_rendered_callback_enabled': FunctionInfo(17, [], [], [], '', ['enabled'], [{}], '!'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'frame_rendered': CallbackInfo(6, ['length'], [{}], 'H', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 3; re[2] = 1; re[3] = 3; re[4] = 1; re[5] = 1; re[7] = 3; re[8] = 1; re[9] = 3; re[10] = 1; re[11] = 3; re[12] = 1; re[13] = 3; re[14] = 1; re[15] = 2; re[16] = 2; re[17] = 1; re[255] = 1

class LEDStripV2Bricklet(MQTTCallbackDevice):
	functions = {
		'set_led_values_low_level': FunctionInfo(1, ['index', 'value_length', 'value_chunk_offset', 'value_chunk_data'], ['int', 'int', 'int', ('int', 58)], [{}, {}, {}, {}], 'H H H 58B', [], [], ''),
		'set_led_values': HighLevelFunctionInfo(1, 'in', [None, 'stream_data'], [], [None, 'stream_length', 'stream_chunk_offset', 'stream_chunk_data'], [], ['index', 'value'], ['int', ('int', -65535)], [{}, {}], 'H H H 58B', [], [], '','0', 58, None,False, False, None),
		'get_led_values_low_level': FunctionInfo(2, ['index', 'length'], ['int', 'int'], [{}, {}], 'H H', ['value_length', 'value_chunk_offset', 'value_chunk_data'], [{}, {}, {}], 'H H 60B'),
		'get_led_values': HighLevelFunctionInfo(2, 'out', [None, None], ['stream_data'], [None, None], ['stream_length', 'stream_chunk_offset', 'stream_chunk_data'], ['index', 'length'], ['int', 'int'], [{}, {}], 'H H', ['value'], [{}], 'H H 60B',None, 60, None,False, False, None),
		'set_frame_duration': FunctionInfo(3, ['duration'], ['int'], [{}], 'H', [], [], ''),
		'get_frame_duration': FunctionInfo(4, [], [], [], '', ['duration'], [{}], 'H'),
		'get_supply_voltage': FunctionInfo(5, [], [], [], '', ['voltage'], [{}], 'H'),
		'set_clock_frequency': FunctionInfo(7, ['frequency'], ['int'], [{}], 'I', [], [], ''),
		'get_clock_frequency': FunctionInfo(8, [], [], [], '', ['frequency'], [{}], 'I'),
		'set_chip_type': FunctionInfo(9, ['chip'], ['int'], [{2801: 'ws2801', 2811: 'ws2811', 2812: 'ws2812', 8806: 'lpd8806', 102: 'apa102'}], 'H', [], [], ''),
		'get_chip_type': FunctionInfo(10, [], [], [], '', ['chip'], [{2801: 'ws2801', 2811: 'ws2811', 2812: 'ws2812', 8806: 'lpd8806', 102: 'apa102'}], 'H'),
		'set_channel_mapping': FunctionInfo(11, ['mapping'], ['int'], [{6: 'rgb', 9: 'rbg', 33: 'brg', 36: 'bgr', 18: 'grb', 24: 'gbr', 27: 'rgbw', 30: 'rgwb', 39: 'rbgw', 45: 'rbwg', 54: 'rwgb', 57: 'rwbg', 78: 'grwb', 75: 'grbw', 108: 'gbwr', 99: 'gbrw', 120: 'gwbr', 114: 'gwrb', 135: 'brgw', 141: 'brwg', 147: 'bgrw', 156: 'bgwr', 177: 'bwrg', 180: 'bwgr', 201: 'wrbg', 198: 'wrgb', 216: 'wgbr', 210: 'wgrb', 228: 'wbgr', 225: 'wbrg'}], 'B', [], [], ''),
		'get_channel_mapping': FunctionInfo(12, [], [], [], '', ['mapping'], [{6: 'rgb', 9: 'rbg', 33: 'brg', 36: 'bgr', 18: 'grb', 24: 'gbr', 27: 'rgbw', 30: 'rgwb', 39: 'rbgw', 45: 'rbwg', 54: 'rwgb', 57: 'rwbg', 78: 'grwb', 75: 'grbw', 108: 'gbwr', 99: 'gbrw', 120: 'gwbr', 114: 'gwrb', 135: 'brgw', 141: 'brwg', 147: 'bgrw', 156: 'bgwr', 177: 'bwrg', 180: 'bwgr', 201: 'wrbg', 198: 'wrgb', 216: 'wgbr', 210: 'wgrb', 228: 'wbgr', 225: 'wbrg'}], 'B'),
		'set_frame_started_callback_configuration': FunctionInfo(13, ['enable'], ['bool'], [{}], '!', [], [], ''),
		'get_frame_started_callback_configuration': FunctionInfo(14, [], [], [], '', ['enable'], [{}], '!'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'frame_started': CallbackInfo(6, ['length'], [{}], 'H', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 2; re[2] = 1; re[3] = 3; re[4] = 1; re[5] = 1; re[7] = 3; re[8] = 1; re[9] = 3; re[10] = 1; re[11] = 3; re[12] = 1; re[13] = 2; re[14] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class LineBricklet(MQTTCallbackDevice):
	functions = {
		'get_reflectivity': FunctionInfo(1, [], [], [], '', ['reflectivity'], [{}], 'H'),
		'set_reflectivity_callback_period': FunctionInfo(2, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_reflectivity_callback_period': FunctionInfo(3, [], [], [], '', ['period'], [{}], 'I'),
		'set_reflectivity_callback_threshold': FunctionInfo(4, ['option', 'min', 'max'], ['char', 'int', 'int'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c H H', [], [], ''),
		'get_reflectivity_callback_threshold': FunctionInfo(5, [], [], [], '', ['option', 'min', 'max'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c H H'),
		'set_debounce_period': FunctionInfo(6, ['debounce'], ['int'], [{}], 'I', [], [], ''),
		'get_debounce_period': FunctionInfo(7, [], [], [], '', ['debounce'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'reflectivity': CallbackInfo(8, ['reflectivity'], [{}], 'H', None),
		'reflectivity_reached': CallbackInfo(9, ['reflectivity'], [{}], 'H', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 2; re[3] = 1; re[4] = 2; re[5] = 1; re[6] = 2; re[7] = 1; re[255] = 1

class LinearPotiBricklet(MQTTCallbackDevice):
	functions = {
		'get_position': FunctionInfo(1, [], [], [], '', ['position'], [{}], 'H'),
		'get_analog_value': FunctionInfo(2, [], [], [], '', ['value'], [{}], 'H'),
		'set_position_callback_period': FunctionInfo(3, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_position_callback_period': FunctionInfo(4, [], [], [], '', ['period'], [{}], 'I'),
		'set_analog_value_callback_period': FunctionInfo(5, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_analog_value_callback_period': FunctionInfo(6, [], [], [], '', ['period'], [{}], 'I'),
		'set_position_callback_threshold': FunctionInfo(7, ['option', 'min', 'max'], ['char', 'int', 'int'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c H H', [], [], ''),
		'get_position_callback_threshold': FunctionInfo(8, [], [], [], '', ['option', 'min', 'max'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c H H'),
		'set_analog_value_callback_threshold': FunctionInfo(9, ['option', 'min', 'max'], ['char', 'int', 'int'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c H H', [], [], ''),
		'get_analog_value_callback_threshold': FunctionInfo(10, [], [], [], '', ['option', 'min', 'max'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c H H'),
		'set_debounce_period': FunctionInfo(11, ['debounce'], ['int'], [{}], 'I', [], [], ''),
		'get_debounce_period': FunctionInfo(12, [], [], [], '', ['debounce'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'position': CallbackInfo(13, ['position'], [{}], 'H', None),
		'analog_value': CallbackInfo(14, ['value'], [{}], 'H', None),
		'position_reached': CallbackInfo(15, ['position'], [{}], 'H', None),
		'analog_value_reached': CallbackInfo(16, ['value'], [{}], 'H', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 1; re[3] = 2; re[4] = 1; re[5] = 2; re[6] = 1; re[7] = 2; re[8] = 1; re[9] = 2; re[10] = 1; re[11] = 2; re[12] = 1; re[255] = 1

class LinearPotiV2Bricklet(MQTTCallbackDevice):
	functions = {
		'get_position': FunctionInfo(1, [], [], [], '', ['position'], [{}], 'B'),
		'set_position_callback_configuration': FunctionInfo(2, ['period', 'value_has_to_change', 'option', 'min', 'max'], ['int', 'bool', 'char', 'int', 'int'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c B B', [], [], ''),
		'get_position_callback_configuration': FunctionInfo(3, [], [], [], '', ['period', 'value_has_to_change', 'option', 'min', 'max'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c B B'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'position': CallbackInfo(4, ['position'], [{}], 'B', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 2; re[3] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class LoadCellBricklet(MQTTCallbackDevice):
	functions = {
		'get_weight': FunctionInfo(1, [], [], [], '', ['weight'], [{}], 'i'),
		'set_weight_callback_period': FunctionInfo(2, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_weight_callback_period': FunctionInfo(3, [], [], [], '', ['period'], [{}], 'I'),
		'set_weight_callback_threshold': FunctionInfo(4, ['option', 'min', 'max'], ['char', 'int', 'int'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c i i', [], [], ''),
		'get_weight_callback_threshold': FunctionInfo(5, [], [], [], '', ['option', 'min', 'max'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c i i'),
		'set_debounce_period': FunctionInfo(6, ['debounce'], ['int'], [{}], 'I', [], [], ''),
		'get_debounce_period': FunctionInfo(7, [], [], [], '', ['debounce'], [{}], 'I'),
		'set_moving_average': FunctionInfo(8, ['average'], ['int'], [{}], 'B', [], [], ''),
		'get_moving_average': FunctionInfo(9, [], [], [], '', ['average'], [{}], 'B'),
		'led_on': FunctionInfo(10, [], [], [], '', [], [], ''),
		'led_off': FunctionInfo(11, [], [], [], '', [], [], ''),
		'is_led_on': FunctionInfo(12, [], [], [], '', ['on'], [{}], '!'),
		'calibrate': FunctionInfo(13, ['weight'], ['int'], [{}], 'I', [], [], ''),
		'tare': FunctionInfo(14, [], [], [], '', [], [], ''),
		'set_configuration': FunctionInfo(15, ['rate', 'gain'], ['int', 'int'], [{0: '10hz', 1: '80hz'}, {0: '128x', 1: '64x', 2: '32x'}], 'B B', [], [], ''),
		'get_configuration': FunctionInfo(16, [], [], [], '', ['rate', 'gain'], [{0: '10hz', 1: '80hz'}, {0: '128x', 1: '64x', 2: '32x'}], 'B B'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'weight': CallbackInfo(17, ['weight'], [{}], 'i', None),
		'weight_reached': CallbackInfo(18, ['weight'], [{}], 'i', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 2; re[3] = 1; re[4] = 2; re[5] = 1; re[6] = 2; re[7] = 1; re[8] = 3; re[9] = 1; re[10] = 3; re[11] = 3; re[12] = 1; re[13] = 3; re[14] = 3; re[15] = 3; re[16] = 1; re[255] = 1

class LoadCellV2Bricklet(MQTTCallbackDevice):
	functions = {
		'get_weight': FunctionInfo(1, [], [], [], '', ['weight'], [{}], 'i'),
		'set_weight_callback_configuration': FunctionInfo(2, ['period', 'value_has_to_change', 'option', 'min', 'max'], ['int', 'bool', 'char', 'int', 'int'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c i i', [], [], ''),
		'get_weight_callback_configuration': FunctionInfo(3, [], [], [], '', ['period', 'value_has_to_change', 'option', 'min', 'max'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c i i'),
		'set_moving_average': FunctionInfo(5, ['average'], ['int'], [{}], 'H', [], [], ''),
		'get_moving_average': FunctionInfo(6, [], [], [], '', ['average'], [{}], 'H'),
		'set_info_led_config': FunctionInfo(7, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat'}], 'B', [], [], ''),
		'get_info_led_config': FunctionInfo(8, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat'}], 'B'),
		'calibrate': FunctionInfo(9, ['weight'], ['int'], [{}], 'I', [], [], ''),
		'tare': FunctionInfo(10, [], [], [], '', [], [], ''),
		'set_configuration': FunctionInfo(11, ['rate', 'gain'], ['int', 'int'], [{0: '10hz', 1: '80hz'}, {0: '128x', 1: '64x', 2: '32x'}], 'B B', [], [], ''),
		'get_configuration': FunctionInfo(12, [], [], [], '', ['rate', 'gain'], [{0: '10hz', 1: '80hz'}, {0: '128x', 1: '64x', 2: '32x'}], 'B B'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'weight': CallbackInfo(4, ['weight'], [{}], 'i', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 2; re[3] = 1; re[5] = 3; re[6] = 1; re[7] = 3; re[8] = 1; re[9] = 3; re[10] = 3; re[11] = 3; re[12] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class MasterBrick(MQTTCallbackDevice):
	functions = {
		'get_stack_voltage': FunctionInfo(1, [], [], [], '', ['voltage'], [{}], 'H'),
		'get_stack_current': FunctionInfo(2, [], [], [], '', ['current'], [{}], 'H'),
		'set_extension_type': FunctionInfo(3, ['extension', 'exttype'], ['int', 'int'], [{}, {1: 'chibi', 2: 'rs485', 3: 'wifi', 4: 'ethernet', 5: 'wifi2'}], 'B I', [], [], ''),
		'get_extension_type': FunctionInfo(4, ['extension'], ['int'], [{}], 'B', ['exttype'], [{1: 'chibi', 2: 'rs485', 3: 'wifi', 4: 'ethernet', 5: 'wifi2'}], 'I'),
		'is_chibi_present': FunctionInfo(5, [], [], [], '', ['present'], [{}], '!'),
		'set_chibi_address': FunctionInfo(6, ['address'], ['int'], [{}], 'B', [], [], ''),
		'get_chibi_address': FunctionInfo(7, [], [], [], '', ['address'], [{}], 'B'),
		'set_chibi_master_address': FunctionInfo(8, ['address'], ['int'], [{}], 'B', [], [], ''),
		'get_chibi_master_address': FunctionInfo(9, [], [], [], '', ['address'], [{}], 'B'),
		'set_chibi_slave_address': FunctionInfo(10, ['num', 'address'], ['int', 'int'], [{}, {}], 'B B', [], [], ''),
		'get_chibi_slave_address': FunctionInfo(11, ['num'], ['int'], [{}], 'B', ['address'], [{}], 'B'),
		'get_chibi_signal_strength': FunctionInfo(12, [], [], [], '', ['signal_strength'], [{}], 'B'),
		'get_chibi_error_log': FunctionInfo(13, [], [], [], '', ['underrun', 'crc_error', 'no_ack', 'overflow'], [{}, {}, {}, {}], 'H H H H'),
		'set_chibi_frequency': FunctionInfo(14, ['frequency'], ['int'], [{0: 'oqpsk_868_mhz', 1: 'oqpsk_915_mhz', 2: 'oqpsk_780_mhz', 3: 'bpsk40_915_mhz'}], 'B', [], [], ''),
		'get_chibi_frequency': FunctionInfo(15, [], [], [], '', ['frequency'], [{0: 'oqpsk_868_mhz', 1: 'oqpsk_915_mhz', 2: 'oqpsk_780_mhz', 3: 'bpsk40_915_mhz'}], 'B'),
		'set_chibi_channel': FunctionInfo(16, ['channel'], ['int'], [{}], 'B', [], [], ''),
		'get_chibi_channel': FunctionInfo(17, [], [], [], '', ['channel'], [{}], 'B'),
		'is_rs485_present': FunctionInfo(18, [], [], [], '', ['present'], [{}], '!'),
		'set_rs485_address': FunctionInfo(19, ['address'], ['int'], [{}], 'B', [], [], ''),
		'get_rs485_address': FunctionInfo(20, [], [], [], '', ['address'], [{}], 'B'),
		'set_rs485_slave_address': FunctionInfo(21, ['num', 'address'], ['int', 'int'], [{}, {}], 'B B', [], [], ''),
		'get_rs485_slave_address': FunctionInfo(22, ['num'], ['int'], [{}], 'B', ['address'], [{}], 'B'),
		'get_rs485_error_log': FunctionInfo(23, [], [], [], '', ['crc_error'], [{}], 'H'),
		'set_rs485_configuration': FunctionInfo(24, ['speed', 'parity', 'stopbits'], ['int', 'char', 'int'], [{}, {'n': 'none', 'e': 'even', 'o': 'odd'}, {}], 'I c B', [], [], ''),
		'get_rs485_configuration': FunctionInfo(25, [], [], [], '', ['speed', 'parity', 'stopbits'], [{}, {'n': 'none', 'e': 'even', 'o': 'odd'}, {}], 'I c B'),
		'is_wifi_present': FunctionInfo(26, [], [], [], '', ['present'], [{}], '!'),
		'set_wifi_configuration': FunctionInfo(27, ['ssid', 'connection', 'ip', 'subnet_mask', 'gateway', 'port'], ['string', 'int', ('int', 4), ('int', 4), ('int', 4), 'int'], [{}, {0: 'dhcp', 1: 'static_ip', 2: 'access_point_dhcp', 3: 'access_point_static_ip', 4: 'ad_hoc_dhcp', 5: 'ad_hoc_static_ip'}, {}, {}, {}, {}], '32s B 4B 4B 4B H', [], [], ''),
		'get_wifi_configuration': FunctionInfo(28, [], [], [], '', ['ssid', 'connection', 'ip', 'subnet_mask', 'gateway', 'port'], [{}, {0: 'dhcp', 1: 'static_ip', 2: 'access_point_dhcp', 3: 'access_point_static_ip', 4: 'ad_hoc_dhcp', 5: 'ad_hoc_static_ip'}, {}, {}, {}, {}], '32s B 4B 4B 4B H'),
		'set_wifi_encryption': FunctionInfo(29, ['encryption', 'key', 'key_index', 'eap_options', 'ca_certificate_length', 'client_certificate_length', 'private_key_length'], ['int', 'string', 'int', 'int', 'int', 'int', 'int'], [{0: 'wpa_wpa2', 1: 'wpa_enterprise', 2: 'wep', 3: 'no_encryption'}, {}, {}, {0: 'outer_auth_eap_fast', 1: 'outer_auth_eap_tls', 2: 'outer_auth_eap_ttls', 3: 'outer_auth_eap_peap', 0: 'inner_auth_eap_mschap', 4: 'inner_auth_eap_gtc', 0: 'cert_type_ca_cert', 8: 'cert_type_client_cert', 16: 'cert_type_private_key'}, {}, {}, {}], 'B 50s B B H H H', [], [], ''),
		'get_wifi_encryption': FunctionInfo(30, [], [], [], '', ['encryption', 'key', 'key_index', 'eap_options', 'ca_certificate_length', 'client_certificate_length', 'private_key_length'], [{0: 'wpa_wpa2', 1: 'wpa_enterprise', 2: 'wep', 3: 'no_encryption'}, {}, {}, {0: 'outer_auth_eap_fast', 1: 'outer_auth_eap_tls', 2: 'outer_auth_eap_ttls', 3: 'outer_auth_eap_peap', 0: 'inner_auth_eap_mschap', 4: 'inner_auth_eap_gtc', 0: 'cert_type_ca_cert', 8: 'cert_type_client_cert', 16: 'cert_type_private_key'}, {}, {}, {}], 'B 50s B B H H H'),
		'get_wifi_status': FunctionInfo(31, [], [], [], '', ['mac_address', 'bssid', 'channel', 'rssi', 'ip', 'subnet_mask', 'gateway', 'rx_count', 'tx_count', 'state'], [{}, {}, {}, {}, {}, {}, {}, {}, {}, {0: 'disassociated', 1: 'associated', 2: 'associating', 3: 'error', 255: 'not_initialized_yet'}], '6B 6B B h 4B 4B 4B I I B'),
		'refresh_wifi_status': FunctionInfo(32, [], [], [], '', [], [], ''),
		'set_wifi_certificate': FunctionInfo(33, ['index', 'data', 'data_length'], ['int', ('int', 32), 'int'], [{}, {}, {}], 'H 32B B', [], [], ''),
		'get_wifi_certificate': FunctionInfo(34, ['index'], ['int'], [{}], 'H', ['data', 'data_length'], [{}, {}], '32B B'),
		'set_wifi_power_mode': FunctionInfo(35, ['mode'], ['int'], [{0: 'full_speed', 1: 'low_power'}], 'B', [], [], ''),
		'get_wifi_power_mode': FunctionInfo(36, [], [], [], '', ['mode'], [{0: 'full_speed', 1: 'low_power'}], 'B'),
		'get_wifi_buffer_info': FunctionInfo(37, [], [], [], '', ['overflow', 'low_watermark', 'used'], [{}, {}, {}], 'I H H'),
		'set_wifi_regulatory_domain': FunctionInfo(38, ['domain'], ['int'], [{0: 'channel_1to11', 1: 'channel_1to13', 2: 'channel_1to14'}], 'B', [], [], ''),
		'get_wifi_regulatory_domain': FunctionInfo(39, [], [], [], '', ['domain'], [{0: 'channel_1to11', 1: 'channel_1to13', 2: 'channel_1to14'}], 'B'),
		'get_usb_voltage': FunctionInfo(40, [], [], [], '', ['voltage'], [{}], 'H'),
		'set_long_wifi_key': FunctionInfo(41, ['key'], ['string'], [{}], '64s', [], [], ''),
		'get_long_wifi_key': FunctionInfo(42, [], [], [], '', ['key'], [{}], '64s'),
		'set_wifi_hostname': FunctionInfo(43, ['hostname'], ['string'], [{}], '16s', [], [], ''),
		'get_wifi_hostname': FunctionInfo(44, [], [], [], '', ['hostname'], [{}], '16s'),
		'set_stack_current_callback_period': FunctionInfo(45, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_stack_current_callback_period': FunctionInfo(46, [], [], [], '', ['period'], [{}], 'I'),
		'set_stack_voltage_callback_period': FunctionInfo(47, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_stack_voltage_callback_period': FunctionInfo(48, [], [], [], '', ['period'], [{}], 'I'),
		'set_usb_voltage_callback_period': FunctionInfo(49, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_usb_voltage_callback_period': FunctionInfo(50, [], [], [], '', ['period'], [{}], 'I'),
		'set_stack_current_callback_threshold': FunctionInfo(51, ['option', 'min', 'max'], ['char', 'int', 'int'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c H H', [], [], ''),
		'get_stack_current_callback_threshold': FunctionInfo(52, [], [], [], '', ['option', 'min', 'max'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c H H'),
		'set_stack_voltage_callback_threshold': FunctionInfo(53, ['option', 'min', 'max'], ['char', 'int', 'int'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c H H', [], [], ''),
		'get_stack_voltage_callback_threshold': FunctionInfo(54, [], [], [], '', ['option', 'min', 'max'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c H H'),
		'set_usb_voltage_callback_threshold': FunctionInfo(55, ['option', 'min', 'max'], ['char', 'int', 'int'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c H H', [], [], ''),
		'get_usb_voltage_callback_threshold': FunctionInfo(56, [], [], [], '', ['option', 'min', 'max'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c H H'),
		'set_debounce_period': FunctionInfo(57, ['debounce'], ['int'], [{}], 'I', [], [], ''),
		'get_debounce_period': FunctionInfo(58, [], [], [], '', ['debounce'], [{}], 'I'),
		'is_ethernet_present': FunctionInfo(65, [], [], [], '', ['present'], [{}], '!'),
		'set_ethernet_configuration': FunctionInfo(66, ['connection', 'ip', 'subnet_mask', 'gateway', 'port'], ['int', ('int', 4), ('int', 4), ('int', 4), 'int'], [{0: 'dhcp', 1: 'static_ip'}, {}, {}, {}, {}], 'B 4B 4B 4B H', [], [], ''),
		'get_ethernet_configuration': FunctionInfo(67, [], [], [], '', ['connection', 'ip', 'subnet_mask', 'gateway', 'port'], [{0: 'dhcp', 1: 'static_ip'}, {}, {}, {}, {}], 'B 4B 4B 4B H'),
		'get_ethernet_status': FunctionInfo(68, [], [], [], '', ['mac_address', 'ip', 'subnet_mask', 'gateway', 'rx_count', 'tx_count', 'hostname'], [{}, {}, {}, {}, {}, {}, {}], '6B 4B 4B 4B I I 32s'),
		'set_ethernet_hostname': FunctionInfo(69, ['hostname'], ['string'], [{}], '32s', [], [], ''),
		'set_ethernet_mac_address': FunctionInfo(70, ['mac_address'], [('int', 6)], [{}], '6B', [], [], ''),
		'set_ethernet_websocket_configuration': FunctionInfo(71, ['sockets', 'port'], ['int', 'int'], [{}, {}], 'B H', [], [], ''),
		'get_ethernet_websocket_configuration': FunctionInfo(72, [], [], [], '', ['sockets', 'port'], [{}, {}], 'B H'),
		'set_ethernet_authentication_secret': FunctionInfo(73, ['secret'], ['string'], [{}], '64s', [], [], ''),
		'get_ethernet_authentication_secret': FunctionInfo(74, [], [], [], '', ['secret'], [{}], '64s'),
		'set_wifi_authentication_secret': FunctionInfo(75, ['secret'], ['string'], [{}], '64s', [], [], ''),
		'get_wifi_authentication_secret': FunctionInfo(76, [], [], [], '', ['secret'], [{}], '64s'),
		'get_connection_type': FunctionInfo(77, [], [], [], '', ['connection_type'], [{0: 'none', 1: 'usb', 2: 'spi_stack', 3: 'chibi', 4: 'rs485', 5: 'wifi', 6: 'ethernet', 7: 'wifi2'}], 'B'),
		'is_wifi2_present': FunctionInfo(78, [], [], [], '', ['present'], [{}], '!'),
		'start_wifi2_bootloader': FunctionInfo(79, [], [], [], '', ['result'], [{}], 'b'),
		'write_wifi2_serial_port': FunctionInfo(80, ['data', 'length'], [('int', 60), 'int'], [{}, {}], '60B B', ['result'], [{}], 'b'),
		'read_wifi2_serial_port': FunctionInfo(81, ['length'], ['int'], [{}], 'B', ['data', 'result'], [{}, {}], '60B B'),
		'set_wifi2_authentication_secret': FunctionInfo(82, ['secret'], ['string'], [{}], '64s', [], [], ''),
		'get_wifi2_authentication_secret': FunctionInfo(83, [], [], [], '', ['secret'], [{}], '64s'),
		'set_wifi2_configuration': FunctionInfo(84, ['port', 'websocket_port', 'website_port', 'phy_mode', 'sleep_mode', 'website'], ['int', 'int', 'int', 'int', 'int', 'int'], [{}, {}, {}, {0: 'b', 1: 'g', 2: 'n'}, {}, {}], 'H H H B B B', [], [], ''),
		'get_wifi2_configuration': FunctionInfo(85, [], [], [], '', ['port', 'websocket_port', 'website_port', 'phy_mode', 'sleep_mode', 'website'], [{}, {}, {}, {0: 'b', 1: 'g', 2: 'n'}, {}, {}], 'H H H B B B'),
		'get_wifi2_status': FunctionInfo(86, [], [], [], '', ['client_enabled', 'client_status', 'client_ip', 'client_subnet_mask', 'client_gateway', 'client_mac_address', 'client_rx_count', 'client_tx_count', 'client_rssi', 'ap_enabled', 'ap_ip', 'ap_subnet_mask', 'ap_gateway', 'ap_mac_address', 'ap_rx_count', 'ap_tx_count', 'ap_connected_count'], [{}, {0: 'idle', 1: 'connecting', 2: 'wrong_password', 3: 'no_ap_found', 4: 'connect_failed', 5: 'got_ip', 255: 'unknown'}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}], '! B 4B 4B 4B 6B I I b ! 4B 4B 4B 6B I I B'),
		'set_wifi2_client_configuration': FunctionInfo(87, ['enable', 'ssid', 'ip', 'subnet_mask', 'gateway', 'mac_address', 'bssid'], ['bool', 'string', ('int', 4), ('int', 4), ('int', 4), ('int', 6), ('int', 6)], [{}, {}, {}, {}, {}, {}, {}], '! 32s 4B 4B 4B 6B 6B', [], [], ''),
		'get_wifi2_client_configuration': FunctionInfo(88, [], [], [], '', ['enable', 'ssid', 'ip', 'subnet_mask', 'gateway', 'mac_address', 'bssid'], [{}, {}, {}, {}, {}, {}, {}], '! 32s 4B 4B 4B 6B 6B'),
		'set_wifi2_client_hostname': FunctionInfo(89, ['hostname'], ['string'], [{}], '32s', [], [], ''),
		'get_wifi2_client_hostname': FunctionInfo(90, [], [], [], '', ['hostname'], [{}], '32s'),
		'set_wifi2_client_password': FunctionInfo(91, ['password'], ['string'], [{}], '64s', [], [], ''),
		'get_wifi2_client_password': FunctionInfo(92, [], [], [], '', ['password'], [{}], '64s'),
		'set_wifi2_ap_configuration': FunctionInfo(93, ['enable', 'ssid', 'ip', 'subnet_mask', 'gateway', 'encryption', 'hidden', 'channel', 'mac_address'], ['bool', 'string', ('int', 4), ('int', 4), ('int', 4), 'int', 'bool', 'int', ('int', 6)], [{}, {}, {}, {}, {}, {0: 'open', 1: 'wep', 2: 'wpa_psk', 3: 'wpa2_psk', 4: 'wpa_wpa2_psk'}, {}, {}, {}], '! 32s 4B 4B 4B B ! B 6B', [], [], ''),
		'get_wifi2_ap_configuration': FunctionInfo(94, [], [], [], '', ['enable', 'ssid', 'ip', 'subnet_mask', 'gateway', 'encryption', 'hidden', 'channel', 'mac_address'], [{}, {}, {}, {}, {}, {0: 'open', 1: 'wep', 2: 'wpa_psk', 3: 'wpa2_psk', 4: 'wpa_wpa2_psk'}, {}, {}, {}], '! 32s 4B 4B 4B B ! B 6B'),
		'set_wifi2_ap_password': FunctionInfo(95, ['password'], ['string'], [{}], '64s', [], [], ''),
		'get_wifi2_ap_password': FunctionInfo(96, [], [], [], '', ['password'], [{}], '64s'),
		'save_wifi2_configuration': FunctionInfo(97, [], [], [], '', ['result'], [{}], 'B'),
		'get_wifi2_firmware_version': FunctionInfo(98, [], [], [], '', ['firmware_version'], [{}], '3B'),
		'enable_wifi2_status_led': FunctionInfo(99, [], [], [], '', [], [], ''),
		'disable_wifi2_status_led': FunctionInfo(100, [], [], [], '', [], [], ''),
		'is_wifi2_status_led_enabled': FunctionInfo(101, [], [], [], '', ['enabled'], [{}], '!'),
		'set_wifi2_mesh_configuration': FunctionInfo(102, ['enable', 'root_ip', 'root_subnet_mask', 'root_gateway', 'router_bssid', 'group_id', 'group_ssid_prefix', 'gateway_ip', 'gateway_port'], ['bool', ('int', 4), ('int', 4), ('int', 4), ('int', 6), ('int', 6), 'string', ('int', 4), 'int'], [{}, {}, {}, {}, {}, {}, {}, {}, {}], '! 4B 4B 4B 6B 6B 16s 4B H', [], [], ''),
		'get_wifi2_mesh_configuration': FunctionInfo(103, [], [], [], '', ['enable', 'root_ip', 'root_subnet_mask', 'root_gateway', 'router_bssid', 'group_id', 'group_ssid_prefix', 'gateway_ip', 'gateway_port'], [{}, {}, {}, {}, {}, {}, {}, {}, {}], '! 4B 4B 4B 6B 6B 16s 4B H'),
		'set_wifi2_mesh_router_ssid': FunctionInfo(104, ['ssid'], ['string'], [{}], '32s', [], [], ''),
		'get_wifi2_mesh_router_ssid': FunctionInfo(105, [], [], [], '', ['ssid'], [{}], '32s'),
		'set_wifi2_mesh_router_password': FunctionInfo(106, ['password'], ['string'], [{}], '64s', [], [], ''),
		'get_wifi2_mesh_router_password': FunctionInfo(107, [], [], [], '', ['password'], [{}], '64s'),
		'get_wifi2_mesh_common_status': FunctionInfo(108, [], [], [], '', ['status', 'root_node', 'root_candidate', 'connected_nodes', 'rx_count', 'tx_count'], [{0: 'disabled', 1: 'wifi_connecting', 2: 'got_ip', 3: 'mesh_local', 4: 'mesh_online', 5: 'ap_available', 6: 'ap_setup', 7: 'leaf_available'}, {}, {}, {}, {}, {}], 'B ! ! H I I'),
		'get_wifi2_mesh_client_status': FunctionInfo(109, [], [], [], '', ['hostname', 'ip', 'subnet_mask', 'gateway', 'mac_address'], [{}, {}, {}, {}, {}], '32s 4B 4B 4B 6B'),
		'get_wifi2_mesh_ap_status': FunctionInfo(110, [], [], [], '', ['ssid', 'ip', 'subnet_mask', 'gateway', 'mac_address'], [{}, {}, {}, {}, {}], '32s 4B 4B 4B 6B'),
		'set_spitfp_baudrate_config': FunctionInfo(231, ['enable_dynamic_baudrate', 'minimum_dynamic_baudrate'], ['bool', 'int'], [{}, {}], '! I', [], [], ''),
		'get_spitfp_baudrate_config': FunctionInfo(232, [], [], [], '', ['enable_dynamic_baudrate', 'minimum_dynamic_baudrate'], [{}, {}], '! I'),
		'get_send_timeout_count': FunctionInfo(233, ['communication_method'], ['int'], [{0: 'none', 1: 'usb', 2: 'spi_stack', 3: 'chibi', 4: 'rs485', 5: 'wifi', 6: 'ethernet', 7: 'wifi_v2'}], 'B', ['timeout_count'], [{}], 'I'),
		'set_spitfp_baudrate': FunctionInfo(234, ['bricklet_port', 'baudrate'], ['char', 'int'], [{}, {}], 'c I', [], [], ''),
		'get_spitfp_baudrate': FunctionInfo(235, ['bricklet_port'], ['char'], [{}], 'c', ['baudrate'], [{}], 'I'),
		'get_spitfp_error_count': FunctionInfo(237, ['bricklet_port'], ['char'], [{}], 'c', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'enable_status_led': FunctionInfo(238, [], [], [], '', [], [], ''),
		'disable_status_led': FunctionInfo(239, [], [], [], '', [], [], ''),
		'is_status_led_enabled': FunctionInfo(240, [], [], [], '', ['enabled'], [{}], '!'),
		'get_protocol1_bricklet_name': FunctionInfo(241, ['port'], ['char'], [{}], 'c', ['protocol_version', 'firmware_version', 'name'], [{}, {}, {}], 'B 3B 40s'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'stack_current': CallbackInfo(59, ['current'], [{}], 'H', None),
		'stack_voltage': CallbackInfo(60, ['voltage'], [{}], 'H', None),
		'usb_voltage': CallbackInfo(61, ['voltage'], [{}], 'H', None),
		'stack_current_reached': CallbackInfo(62, ['current'], [{}], 'H', None),
		'stack_voltage_reached': CallbackInfo(63, ['voltage'], [{}], 'H', None),
		'usb_voltage_reached': CallbackInfo(64, ['voltage'], [{}], 'H', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 1; re[3] = 3; re[4] = 1; re[5] = 1; re[6] = 3; re[7] = 1; re[8] = 3; re[9] = 1; re[10] = 3; re[11] = 1; re[12] = 1; re[13] = 1; re[14] = 3; re[15] = 1; re[16] = 3; re[17] = 1; re[18] = 1; re[19] = 3; re[20] = 1; re[21] = 3; re[22] = 1; re[23] = 1; re[24] = 3; re[25] = 1; re[26] = 1; re[27] = 3; re[28] = 1; re[29] = 3; re[30] = 1; re[31] = 1; re[32] = 3; re[33] = 3; re[34] = 1; re[35] = 3; re[36] = 1; re[37] = 1; re[38] = 3; re[39] = 1; re[40] = 1; re[41] = 3; re[42] = 1; re[43] = 3; re[44] = 1; re[45] = 2; re[46] = 1; re[47] = 2; re[48] = 1; re[49] = 2; re[50] = 1; re[51] = 2; re[52] = 1; re[53] = 2; re[54] = 1; re[55] = 2; re[56] = 1; re[57] = 2; re[58] = 1; re[65] = 1; re[66] = 3; re[67] = 1; re[68] = 1; re[69] = 3; re[70] = 3; re[71] = 3; re[72] = 1; re[73] = 3; re[74] = 1; re[75] = 3; re[76] = 1; re[77] = 1; re[78] = 1; re[79] = 1; re[80] = 1; re[81] = 1; re[82] = 3; re[83] = 1; re[84] = 3; re[85] = 1; re[86] = 1; re[87] = 3; re[88] = 1; re[89] = 3; re[90] = 1; re[91] = 3; re[92] = 1; re[93] = 3; re[94] = 1; re[95] = 3; re[96] = 1; re[97] = 1; re[98] = 1; re[99] = 3; re[100] = 3; re[101] = 1; re[102] = 3; re[103] = 1; re[104] = 3; re[105] = 1; re[106] = 3; re[107] = 1; re[108] = 1; re[109] = 1; re[110] = 1; re[231] = 3; re[232] = 1; re[233] = 1; re[234] = 3; re[235] = 1; re[237] = 1; re[238] = 3; re[239] = 3; re[240] = 1; re[241] = 1; re[242] = 1; re[243] = 3; re[255] = 1

class MoistureBricklet(MQTTCallbackDevice):
	functions = {
		'get_moisture_value': FunctionInfo(1, [], [], [], '', ['moisture'], [{}], 'H'),
		'set_moisture_callback_period': FunctionInfo(2, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_moisture_callback_period': FunctionInfo(3, [], [], [], '', ['period'], [{}], 'I'),
		'set_moisture_callback_threshold': FunctionInfo(4, ['option', 'min', 'max'], ['char', 'int', 'int'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c H H', [], [], ''),
		'get_moisture_callback_threshold': FunctionInfo(5, [], [], [], '', ['option', 'min', 'max'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c H H'),
		'set_debounce_period': FunctionInfo(6, ['debounce'], ['int'], [{}], 'I', [], [], ''),
		'get_debounce_period': FunctionInfo(7, [], [], [], '', ['debounce'], [{}], 'I'),
		'set_moving_average': FunctionInfo(10, ['average'], ['int'], [{}], 'B', [], [], ''),
		'get_moving_average': FunctionInfo(11, [], [], [], '', ['average'], [{}], 'B'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'moisture': CallbackInfo(8, ['moisture'], [{}], 'H', None),
		'moisture_reached': CallbackInfo(9, ['moisture'], [{}], 'H', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 2; re[3] = 1; re[4] = 2; re[5] = 1; re[6] = 2; re[7] = 1; re[10] = 3; re[11] = 1; re[255] = 1

class MotionDetectorBricklet(MQTTCallbackDevice):
	functions = {
		'get_motion_detected': FunctionInfo(1, [], [], [], '', ['motion'], [{0: 'not_detected', 1: 'detected'}], 'B'),
		'set_status_led_config': FunctionInfo(4, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(5, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_status'}], 'B'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'motion_detected': CallbackInfo(2, [], [], '', None),
		'detection_cycle_ended': CallbackInfo(3, [], [], '', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[4] = 3; re[5] = 1; re[255] = 1

class MotionDetectorV2Bricklet(MQTTCallbackDevice):
	functions = {
		'get_motion_detected': FunctionInfo(1, [], [], [], '', ['motion'], [{0: 'not_detected', 1: 'detected'}], 'B'),
		'set_sensitivity': FunctionInfo(2, ['sensitivity'], ['int'], [{}], 'B', [], [], ''),
		'get_sensitivity': FunctionInfo(3, [], [], [], '', ['sensitivity'], [{}], 'B'),
		'set_indicator': FunctionInfo(4, ['top_left', 'top_right', 'bottom'], ['int', 'int', 'int'], [{}, {}, {}], 'B B B', [], [], ''),
		'get_indicator': FunctionInfo(5, [], [], [], '', ['top_left', 'top_right', 'bottom'], [{}, {}, {}], 'B B B'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'motion_detected': CallbackInfo(6, [], [], '', None),
		'detection_cycle_ended': CallbackInfo(7, [], [], '', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 3; re[3] = 1; re[4] = 3; re[5] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class MotorizedLinearPotiBricklet(MQTTCallbackDevice):
	functions = {
		'get_position': FunctionInfo(1, [], [], [], '', ['position'], [{}], 'H'),
		'set_position_callback_configuration': FunctionInfo(2, ['period', 'value_has_to_change', 'option', 'min', 'max'], ['int', 'bool', 'char', 'int', 'int'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c H H', [], [], ''),
		'get_position_callback_configuration': FunctionInfo(3, [], [], [], '', ['period', 'value_has_to_change', 'option', 'min', 'max'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c H H'),
		'set_motor_position': FunctionInfo(5, ['position', 'drive_mode', 'hold_position'], ['int', 'int', 'bool'], [{}, {0: 'fast', 1: 'smooth'}, {}], 'H B !', [], [], ''),
		'get_motor_position': FunctionInfo(6, [], [], [], '', ['position', 'drive_mode', 'hold_position', 'position_reached'], [{}, {0: 'fast', 1: 'smooth'}, {}, {}], 'H B ! !'),
		'calibrate': FunctionInfo(7, [], [], [], '', [], [], ''),
		'set_position_reached_callback_configuration': FunctionInfo(8, ['enabled'], ['bool'], [{}], '!', [], [], ''),
		'get_position_reached_callback_configuration': FunctionInfo(9, [], [], [], '', ['enabled'], [{}], '!'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'position': CallbackInfo(4, ['position'], [{}], 'H', None),
		'position_reached': CallbackInfo(10, ['position'], [{}], 'H', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 2; re[3] = 1; re[5] = 3; re[6] = 1; re[7] = 3; re[8] = 2; re[9] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class MultiTouchBricklet(MQTTCallbackDevice):
	functions = {
		'get_touch_state': FunctionInfo(1, [], [], [], '', ['state'], [{}], 'H'),
		'recalibrate': FunctionInfo(2, [], [], [], '', [], [], ''),
		'set_electrode_config': FunctionInfo(3, ['enabled_electrodes'], ['int'], [{}], 'H', [], [], ''),
		'get_electrode_config': FunctionInfo(4, [], [], [], '', ['enabled_electrodes'], [{}], 'H'),
		'set_electrode_sensitivity': FunctionInfo(6, ['sensitivity'], ['int'], [{}], 'B', [], [], ''),
		'get_electrode_sensitivity': FunctionInfo(7, [], [], [], '', ['sensitivity'], [{}], 'B'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'touch_state': CallbackInfo(5, ['state'], [{}], 'H', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 3; re[3] = 3; re[4] = 1; re[6] = 3; re[7] = 1; re[255] = 1

class MultiTouchV2Bricklet(MQTTCallbackDevice):
	functions = {
		'get_touch_state': FunctionInfo(1, [], [], [], '', ['state'], [{}], '13!'),
		'set_touch_state_callback_configuration': FunctionInfo(2, ['period', 'value_has_to_change'], ['int', 'bool'], [{}, {}], 'I !', [], [], ''),
		'get_touch_state_callback_configuration': FunctionInfo(3, [], [], [], '', ['period', 'value_has_to_change'], [{}, {}], 'I !'),
		'recalibrate': FunctionInfo(5, [], [], [], '', [], [], ''),
		'set_electrode_config': FunctionInfo(6, ['enabled_electrodes'], [('bool', 13)], [{}], '13!', [], [], ''),
		'get_electrode_config': FunctionInfo(7, [], [], [], '', ['enabled_electrodes'], [{}], '13!'),
		'set_electrode_sensitivity': FunctionInfo(8, ['sensitivity'], ['int'], [{}], 'B', [], [], ''),
		'get_electrode_sensitivity': FunctionInfo(9, [], [], [], '', ['sensitivity'], [{}], 'B'),
		'set_touch_led_config': FunctionInfo(10, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_touch'}], 'B', [], [], ''),
		'get_touch_led_config': FunctionInfo(11, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_touch'}], 'B'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'touch_state': CallbackInfo(4, ['state'], [{}], '13!', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 2; re[3] = 1; re[5] = 3; re[6] = 3; re[7] = 1; re[8] = 3; re[9] = 1; re[10] = 3; re[11] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class NFCBricklet(MQTTCallbackDevice):
	functions = {
		'set_mode': FunctionInfo(1, ['mode'], ['int'], [{0: 'off', 1: 'cardemu', 2: 'p2p', 3: 'reader'}], 'B', [], [], ''),
		'get_mode': FunctionInfo(2, [], [], [], '', ['mode'], [{0: 'off', 1: 'cardemu', 2: 'p2p', 3: 'reader'}], 'B'),
		'reader_request_tag_id': FunctionInfo(3, [], [], [], '', [], [], ''),
		'reader_get_tag_id_low_level': FunctionInfo(4, [], [], [], '', ['tag_type', 'tag_id_length', 'tag_id_data'], [{0: 'mifare_classic', 1: 'type1', 2: 'type2', 3: 'type3', 4: 'type4'}, {}, {}], 'B B 32B'),
		'reader_get_tag_id': HighLevelFunctionInfo(4, 'out', [], [None, 'stream_data'], [], [None, 'stream_length', 'stream_chunk_data'], [], [], [], '', ['tag-type', 'tag-id'], [{0: 'mifare_classic', 1: 'type1', 2: 'type2', 3: 'type3', 4: 'type4'}, {}], 'B B 32B',None, 32, None,False, True, None),
		'reader_get_state': FunctionInfo(5, [], [], [], '', ['state', 'idle'], [{0: 'initialization', 128: 'idle', 192: 'error', 2: 'request_tag_id', 130: 'request_tag_id_ready', 194: 'request_tag_id_error', 3: 'authenticate_mifare_classic_page', 131: 'authenticate_mifare_classic_page_ready', 195: 'authenticate_mifare_classic_page_error', 4: 'write_page', 132: 'write_page_ready', 196: 'write_page_error', 5: 'request_page', 133: 'request_page_ready', 197: 'request_page_error', 6: 'write_ndef', 134: 'write_ndef_ready', 198: 'write_ndef_error', 7: 'request_ndef', 135: 'request_ndef_ready', 199: 'request_ndef_error'}, {}], 'B !'),
		'reader_write_ndef_low_level': FunctionInfo(6, ['ndef_length', 'ndef_chunk_offset', 'ndef_chunk_data'], ['int', 'int', ('int', 60)], [{}, {}, {}], 'H H 60B', [], [], ''),
		'reader_write_ndef': HighLevelFunctionInfo(6, 'in', ['stream_data'], [], ['stream_length', 'stream_chunk_offset', 'stream_chunk_data'], [], ['ndef'], [('int', -65535)], [{}], 'H H 60B', [], [], '','0', 60, None,False, False, None),
		'reader_request_ndef': FunctionInfo(7, [], [], [], '', [], [], ''),
		'reader_read_ndef_low_level': FunctionInfo(8, [], [], [], '', ['ndef_length', 'ndef_chunk_offset', 'ndef_chunk_data'], [{}, {}, {}], 'H H 60B'),
		'reader_read_ndef': HighLevelFunctionInfo(8, 'out', [], ['stream_data'], [], ['stream_length', 'stream_chunk_offset', 'stream_chunk_data'], [], [], [], '', ['ndef'], [{}], 'H H 60B',None, 60, None,False, False, None),
		'reader_authenticate_mifare_classic_page': FunctionInfo(9, ['page', 'key_number', 'key'], ['int', 'int', ('int', 6)], [{}, {0: 'a', 1: 'b'}, {}], 'H B 6B', [], [], ''),
		'reader_write_page_low_level': FunctionInfo(10, ['page', 'data_length', 'data_chunk_offset', 'data_chunk_data'], ['int', 'int', 'int', ('int', 58)], [{3: 'type4_capability_container', 4: 'type4_ndef'}, {}, {}, {}], 'H H H 58B', [], [], ''),
		'reader_write_page': HighLevelFunctionInfo(10, 'in', [None, 'stream_data'], [], [None, 'stream_length', 'stream_chunk_offset', 'stream_chunk_data'], [], ['page', 'data'], ['int', ('int', -65535)], [{3: 'type4_capability_container', 4: 'type4_ndef'}, {}], 'H H H 58B', [], [], '','0', 58, None,False, False, None),
		'reader_request_page': FunctionInfo(11, ['page', 'length'], ['int', 'int'], [{3: 'type4_capability_container', 4: 'type4_ndef'}, {}], 'H H', [], [], ''),
		'reader_read_page_low_level': FunctionInfo(12, [], [], [], '', ['data_length', 'data_chunk_offset', 'data_chunk_data'], [{}, {}, {}], 'H H 60B'),
		'reader_read_page': HighLevelFunctionInfo(12, 'out', [], ['stream_data'], [], ['stream_length', 'stream_chunk_offset', 'stream_chunk_data'], [], [], [], '', ['data'], [{}], 'H H 60B',None, 60, None,False, False, None),
		'cardemu_get_state': FunctionInfo(14, [], [], [], '', ['state', 'idle'], [{0: 'initialization', 128: 'idle', 192: 'error', 2: 'discover', 130: 'discover_ready', 194: 'discover_error', 3: 'transfer_ndef', 131: 'transfer_ndef_ready', 195: 'transfer_ndef_error'}, {}], 'B !'),
		'cardemu_start_discovery': FunctionInfo(15, [], [], [], '', [], [], ''),
		'cardemu_write_ndef_low_level': FunctionInfo(16, ['ndef_length', 'ndef_chunk_offset', 'ndef_chunk_data'], ['int', 'int', ('int', 60)], [{}, {}, {}], 'H H 60B', [], [], ''),
		'cardemu_write_ndef': HighLevelFunctionInfo(16, 'in', ['stream_data'], [], ['stream_length', 'stream_chunk_offset', 'stream_chunk_data'], [], ['ndef'], [('int', -65535)], [{}], 'H H 60B', [], [], '','0', 60, None,False, False, None),
		'cardemu_start_transfer': FunctionInfo(17, ['transfer'], ['int'], [{0: 'abort', 1: 'write'}], 'B', [], [], ''),
		'p2p_get_state': FunctionInfo(19, [], [], [], '', ['state', 'idle'], [{0: 'initialization', 128: 'idle', 192: 'error', 2: 'discover', 130: 'discover_ready', 194: 'discover_error', 3: 'transfer_ndef', 131: 'transfer_ndef_ready', 195: 'transfer_ndef_error'}, {}], 'B !'),
		'p2p_start_discovery': FunctionInfo(20, [], [], [], '', [], [], ''),
		'p2p_write_ndef_low_level': FunctionInfo(21, ['ndef_length', 'ndef_chunk_offset', 'ndef_chunk_data'], ['int', 'int', ('int', 60)], [{}, {}, {}], 'H H 60B', [], [], ''),
		'p2p_write_ndef': HighLevelFunctionInfo(21, 'in', ['stream_data'], [], ['stream_length', 'stream_chunk_offset', 'stream_chunk_data'], [], ['ndef'], [('int', -65535)], [{}], 'H H 60B', [], [], '','0', 60, None,False, False, None),
		'p2p_start_transfer': FunctionInfo(22, ['transfer'], ['int'], [{0: 'abort', 1: 'write', 2: 'read'}], 'B', [], [], ''),
		'p2p_read_ndef_low_level': FunctionInfo(23, [], [], [], '', ['ndef_length', 'ndef_chunk_offset', 'ndef_chunk_data'], [{}, {}, {}], 'H H 60B'),
		'p2p_read_ndef': HighLevelFunctionInfo(23, 'out', [], ['stream_data'], [], ['stream_length', 'stream_chunk_offset', 'stream_chunk_data'], [], [], [], '', ['ndef'], [{}], 'H H 60B',None, 60, None,False, False, None),
		'set_detection_led_config': FunctionInfo(25, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_detection'}], 'B', [], [], ''),
		'get_detection_led_config': FunctionInfo(26, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_detection'}], 'B'),
		'set_maximum_timeout': FunctionInfo(27, ['timeout'], ['int'], [{}], 'H', [], [], ''),
		'get_maximum_timeout': FunctionInfo(28, [], [], [], '', ['timeout'], [{}], 'H'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'reader_state_changed': CallbackInfo(13, ['state', 'idle'], [{0: 'initialization', 128: 'idle', 192: 'error', 2: 'request_tag_id', 130: 'request_tag_id_ready', 194: 'request_tag_id_error', 3: 'authenticate_mifare_classic_page', 131: 'authenticate_mifare_classic_page_ready', 195: 'authenticate_mifare_classic_page_error', 4: 'write_page', 132: 'write_page_ready', 196: 'write_page_error', 5: 'request_page', 133: 'request_page_ready', 197: 'request_page_error', 6: 'write_ndef', 134: 'write_ndef_ready', 198: 'write_ndef_error', 7: 'request_ndef', 135: 'request_ndef_ready', 199: 'request_ndef_error'}, {}], 'B !', None),
		'cardemu_state_changed': CallbackInfo(18, ['state', 'idle'], [{0: 'initialization', 128: 'idle', 192: 'error', 2: 'discover', 130: 'discover_ready', 194: 'discover_error', 3: 'transfer_ndef', 131: 'transfer_ndef_ready', 195: 'transfer_ndef_error'}, {}], 'B !', None),
		'p2p_state_changed': CallbackInfo(24, ['state', 'idle'], [{0: 'initialization', 128: 'idle', 192: 'error', 2: 'discover', 130: 'discover_ready', 194: 'discover_error', 3: 'transfer_ndef', 131: 'transfer_ndef_ready', 195: 'transfer_ndef_error'}, {}], 'B !', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 3; re[2] = 1; re[3] = 3; re[4] = 1; re[5] = 1; re[6] = 2; re[7] = 3; re[8] = 1; re[9] = 3; re[10] = 2; re[11] = 3; re[12] = 1; re[14] = 1; re[15] = 3; re[16] = 2; re[17] = 3; re[19] = 1; re[20] = 3; re[21] = 2; re[22] = 3; re[23] = 1; re[25] = 3; re[26] = 1; re[27] = 3; re[28] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class NFCRFIDBricklet(MQTTCallbackDevice):
	functions = {
		'request_tag_id': FunctionInfo(1, ['tag_type'], ['int'], [{0: 'mifare_classic', 1: 'type1', 2: 'type2'}], 'B', [], [], ''),
		'get_tag_id': FunctionInfo(2, [], [], [], '', ['tag_type', 'tid_length', 'tid'], [{0: 'mifare_classic', 1: 'type1', 2: 'type2'}, {}, {}], 'B B 7B'),
		'get_state': FunctionInfo(3, [], [], [], '', ['state', 'idle'], [{0: 'initialization', 128: 'idle', 192: 'error', 2: 'request_tag_id', 130: 'request_tag_id_ready', 194: 'request_tag_id_error', 3: 'authenticating_mifare_classic_page', 131: 'authenticating_mifare_classic_page_ready', 195: 'authenticating_mifare_classic_page_error', 4: 'write_page', 132: 'write_page_ready', 196: 'write_page_error', 5: 'request_page', 133: 'request_page_ready', 197: 'request_page_error'}, {}], 'B !'),
		'authenticate_mifare_classic_page': FunctionInfo(4, ['page', 'key_number', 'key'], ['int', 'int', ('int', 6)], [{}, {0: 'a', 1: 'b'}, {}], 'H B 6B', [], [], ''),
		'write_page': FunctionInfo(5, ['page', 'data'], ['int', ('int', 16)], [{}, {}], 'H 16B', [], [], ''),
		'request_page': FunctionInfo(6, ['page'], ['int'], [{}], 'H', [], [], ''),
		'get_page': FunctionInfo(7, [], [], [], '', ['data'], [{}], '16B'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'state_changed': CallbackInfo(8, ['state', 'idle'], [{0: 'initialization', 128: 'idle', 192: 'error', 2: 'request_tag_id', 130: 'request_tag_id_ready', 194: 'request_tag_id_error', 3: 'authenticating_mifare_classic_page', 131: 'authenticating_mifare_classic_page_ready', 195: 'authenticating_mifare_classic_page_error', 4: 'write_page', 132: 'write_page_ready', 196: 'write_page_error', 5: 'request_page', 133: 'request_page_ready', 197: 'request_page_error'}, {}], 'B !', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 3; re[2] = 1; re[3] = 1; re[4] = 3; re[5] = 3; re[6] = 3; re[7] = 1; re[255] = 1

class OLED128x64Bricklet(MQTTCallbackDevice):
	functions = {
		'write': FunctionInfo(1, ['data'], [('int', 64)], [{}], '64B', [], [], ''),
		'new_window': FunctionInfo(2, ['column_from', 'column_to', 'row_from', 'row_to'], ['int', 'int', 'int', 'int'], [{}, {}, {}, {}], 'B B B B', [], [], ''),
		'clear_display': FunctionInfo(3, [], [], [], '', [], [], ''),
		'set_display_configuration': FunctionInfo(4, ['contrast', 'invert'], ['int', 'bool'], [{}, {}], 'B !', [], [], ''),
		'get_display_configuration': FunctionInfo(5, [], [], [], '', ['contrast', 'invert'], [{}, {}], 'B !'),
		'write_line': FunctionInfo(6, ['line', 'position', 'text'], ['int', 'int', 'string'], [{}, {}, {}], 'B B 26s', [], [], ''),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 3; re[2] = 3; re[3] = 3; re[4] = 3; re[5] = 1; re[6] = 3; re[255] = 1

class OLED128x64V2Bricklet(MQTTCallbackDevice):
	functions = {
		'write_pixels_low_level': FunctionInfo(1, ['x_start', 'y_start', 'x_end', 'y_end', 'pixels_length', 'pixels_chunk_offset', 'pixels_chunk_data'], ['int', 'int', 'int', 'int', 'int', 'int', ('bool', 448)], [{}, {}, {}, {}, {}, {}, {}], 'B B B B H H 448!', [], [], ''),
		'write_pixels': HighLevelFunctionInfo(1, 'in', [None, None, None, None, 'stream_data'], [], [None, None, None, None, 'stream_length', 'stream_chunk_offset', 'stream_chunk_data'], [], ['x_start', 'y_start', 'x_end', 'y_end', 'pixels'], ['int', 'int', 'int', 'int', ('bool', -65535)], [{}, {}, {}, {}, {}], 'B B B B H H 448!', [], [], '','0', 448, None,False, False, None),
		'read_pixels_low_level': FunctionInfo(2, ['x_start', 'y_start', 'x_end', 'y_end'], ['int', 'int', 'int', 'int'], [{}, {}, {}, {}], 'B B B B', ['pixels_length', 'pixels_chunk_offset', 'pixels_chunk_data'], [{}, {}, {}], 'H H 480!'),
		'read_pixels': HighLevelFunctionInfo(2, 'out', [None, None, None, None], ['stream_data'], [None, None, None, None], ['stream_length', 'stream_chunk_offset', 'stream_chunk_data'], ['x_start', 'y_start', 'x_end', 'y_end'], ['int', 'int', 'int', 'int'], [{}, {}, {}, {}], 'B B B B', ['pixels'], [{}], 'H H 480!',None, 480, None,False, False, None),
		'clear_display': FunctionInfo(3, [], [], [], '', [], [], ''),
		'set_display_configuration': FunctionInfo(4, ['contrast', 'invert', 'automatic_draw'], ['int', 'bool', 'bool'], [{}, {}, {}], 'B ! !', [], [], ''),
		'get_display_configuration': FunctionInfo(5, [], [], [], '', ['contrast', 'invert', 'automatic_draw'], [{}, {}, {}], 'B ! !'),
		'write_line': FunctionInfo(6, ['line', 'position', 'text'], ['int', 'int', 'string'], [{}, {}, {}], 'B B 22s', [], [], ''),
		'draw_buffered_frame': FunctionInfo(7, ['force_complete_redraw'], ['bool'], [{}], '!', [], [], ''),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 2; re[2] = 1; re[3] = 3; re[4] = 3; re[5] = 1; re[6] = 3; re[7] = 3; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class OLED64x48Bricklet(MQTTCallbackDevice):
	functions = {
		'write': FunctionInfo(1, ['data'], [('int', 64)], [{}], '64B', [], [], ''),
		'new_window': FunctionInfo(2, ['column_from', 'column_to', 'row_from', 'row_to'], ['int', 'int', 'int', 'int'], [{}, {}, {}, {}], 'B B B B', [], [], ''),
		'clear_display': FunctionInfo(3, [], [], [], '', [], [], ''),
		'set_display_configuration': FunctionInfo(4, ['contrast', 'invert'], ['int', 'bool'], [{}, {}], 'B !', [], [], ''),
		'get_display_configuration': FunctionInfo(5, [], [], [], '', ['contrast', 'invert'], [{}, {}], 'B !'),
		'write_line': FunctionInfo(6, ['line', 'position', 'text'], ['int', 'int', 'string'], [{}, {}, {}], 'B B 13s', [], [], ''),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 3; re[2] = 3; re[3] = 3; re[4] = 3; re[5] = 1; re[6] = 3; re[255] = 1

class OneWireBricklet(MQTTCallbackDevice):
	functions = {
		'search_bus_low_level': FunctionInfo(1, [], [], [], '', ['identifier_length', 'identifier_chunk_offset', 'identifier_chunk_data', 'status'], [{}, {}, {}, {0: 'ok', 1: 'busy', 2: 'no_presence', 3: 'timeout', 4: 'error'}], 'H H 7Q B'),
		'search_bus': HighLevelFunctionInfo(1, 'out', [], ['stream_data', None], [], ['stream_length', 'stream_chunk_offset', 'stream_chunk_data', None], [], [], [], '', ['identifier', 'status'], [{}, {0: 'ok', 1: 'busy', 2: 'no_presence', 3: 'timeout', 4: 'error'}], 'H H 7Q B',None, 7, None,False, False, None),
		'reset_bus': FunctionInfo(2, [], [], [], '', ['status'], [{0: 'ok', 1: 'busy', 2: 'no_presence', 3: 'timeout', 4: 'error'}], 'B'),
		'write': FunctionInfo(3, ['data'], ['int'], [{}], 'B', ['status'], [{0: 'ok', 1: 'busy', 2: 'no_presence', 3: 'timeout', 4: 'error'}], 'B'),
		'read': FunctionInfo(4, [], [], [], '', ['data', 'status'], [{}, {0: 'ok', 1: 'busy', 2: 'no_presence', 3: 'timeout', 4: 'error'}], 'B B'),
		'write_command': FunctionInfo(5, ['identifier', 'command'], ['int', 'int'], [{}, {}], 'Q B', ['status'], [{0: 'ok', 1: 'busy', 2: 'no_presence', 3: 'timeout', 4: 'error'}], 'B'),
		'set_communication_led_config': FunctionInfo(6, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_communication'}], 'B', [], [], ''),
		'get_communication_led_config': FunctionInfo(7, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_communication'}], 'B'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 1; re[3] = 1; re[4] = 1; re[5] = 1; re[6] = 3; re[7] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class OutdoorWeatherBricklet(MQTTCallbackDevice):
	functions = {
		'get_station_identifiers_low_level': FunctionInfo(1, [], [], [], '', ['identifiers_length', 'identifiers_chunk_offset', 'identifiers_chunk_data'], [{}, {}, {}], 'H H 60B'),
		'get_station_identifiers': HighLevelFunctionInfo(1, 'out', [], ['stream_data'], [], ['stream_length', 'stream_chunk_offset', 'stream_chunk_data'], [], [], [], '', ['identifiers'], [{}], 'H H 60B',None, 60, None,False, False, None),
		'get_sensor_identifiers_low_level': FunctionInfo(2, [], [], [], '', ['identifiers_length', 'identifiers_chunk_offset', 'identifiers_chunk_data'], [{}, {}, {}], 'H H 60B'),
		'get_sensor_identifiers': HighLevelFunctionInfo(2, 'out', [], ['stream_data'], [], ['stream_length', 'stream_chunk_offset', 'stream_chunk_data'], [], [], [], '', ['identifiers'], [{}], 'H H 60B',None, 60, None,False, False, None),
		'get_station_data': FunctionInfo(3, ['identifier'], ['int'], [{}], 'B', ['temperature', 'humidity', 'wind_speed', 'gust_speed', 'rain', 'wind_direction', 'battery_low', 'last_change'], [{}, {}, {}, {}, {}, {0: 'n', 1: 'nne', 2: 'ne', 3: 'ene', 4: 'e', 5: 'ese', 6: 'se', 7: 'sse', 8: 's', 9: 'ssw', 10: 'sw', 11: 'wsw', 12: 'w', 13: 'wnw', 14: 'nw', 15: 'nnw', 255: 'error'}, {}, {}], 'h B I I I B ! H'),
		'get_sensor_data': FunctionInfo(4, ['identifier'], ['int'], [{}], 'B', ['temperature', 'humidity', 'last_change'], [{}, {}, {}], 'h B H'),
		'set_station_callback_configuration': FunctionInfo(5, ['enable_callback'], ['bool'], [{}], '!', [], [], ''),
		'get_station_callback_configuration': FunctionInfo(6, [], [], [], '', ['enable_callback'], [{}], '!'),
		'set_sensor_callback_configuration': FunctionInfo(7, ['enable_callback'], ['bool'], [{}], '!', [], [], ''),
		'get_sensor_callback_configuration': FunctionInfo(8, [], [], [], '', ['enable_callback'], [{}], '!'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'station_data': CallbackInfo(9, ['identifier', 'temperature', 'humidity', 'wind_speed', 'gust_speed', 'rain', 'wind_direction', 'battery_low'], [{}, {}, {}, {}, {}, {}, {0: 'n', 1: 'nne', 2: 'ne', 3: 'ene', 4: 'e', 5: 'ese', 6: 'se', 7: 'sse', 8: 's', 9: 'ssw', 10: 'sw', 11: 'wsw', 12: 'w', 13: 'wnw', 14: 'nw', 15: 'nnw', 255: 'error'}, {}], 'B h B I I I B !', None),
		'sensor_data': CallbackInfo(10, ['identifier', 'temperature', 'humidity'], [{}, {}, {}], 'B h B', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 1; re[3] = 1; re[4] = 1; re[5] = 2; re[6] = 1; re[7] = 2; re[8] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class ParticulateMatterBricklet(MQTTCallbackDevice):
	functions = {
		'get_pm_concentration': FunctionInfo(1, [], [], [], '', ['pm10', 'pm25', 'pm100'], [{}, {}, {}], 'H H H'),
		'get_pm_count': FunctionInfo(2, [], [], [], '', ['greater03um', 'greater05um', 'greater10um', 'greater25um', 'greater50um', 'greater100um'], [{}, {}, {}, {}, {}, {}], 'H H H H H H'),
		'set_enable': FunctionInfo(3, ['enable'], ['bool'], [{}], '!', [], [], ''),
		'get_enable': FunctionInfo(4, [], [], [], '', ['enable'], [{}], '!'),
		'get_sensor_info': FunctionInfo(5, [], [], [], '', ['sensor_version', 'last_error_code', 'framing_error_count', 'checksum_error_count'], [{}, {}, {}, {}], 'B B B B'),
		'set_pm_concentration_callback_configuration': FunctionInfo(6, ['period', 'value_has_to_change'], ['int', 'bool'], [{}, {}], 'I !', [], [], ''),
		'get_pm_concentration_callback_configuration': FunctionInfo(7, [], [], [], '', ['period', 'value_has_to_change'], [{}, {}], 'I !'),
		'set_pm_count_callback_configuration': FunctionInfo(8, ['period', 'value_has_to_change'], ['int', 'bool'], [{}, {}], 'I !', [], [], ''),
		'get_pm_count_callback_configuration': FunctionInfo(9, [], [], [], '', ['period', 'value_has_to_change'], [{}, {}], 'I !'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'pm_concentration': CallbackInfo(10, ['pm10', 'pm25', 'pm100'], [{}, {}, {}], 'H H H', None),
		'pm_count': CallbackInfo(11, ['greater03um', 'greater05um', 'greater10um', 'greater25um', 'greater50um', 'greater100um'], [{}, {}, {}, {}, {}, {}], 'H H H H H H', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 1; re[3] = 3; re[4] = 1; re[5] = 1; re[6] = 2; re[7] = 1; re[8] = 2; re[9] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class PiezoBuzzerBricklet(MQTTCallbackDevice):
	functions = {
		'beep': FunctionInfo(1, ['duration'], ['int'], [{}], 'I', [], [], ''),
		'morse_code': FunctionInfo(2, ['morse'], ['string'], [{}], '60s', [], [], ''),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'beep_finished': CallbackInfo(3, [], [], '', None),
		'morse_code_finished': CallbackInfo(4, [], [], '', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 3; re[2] = 3; re[255] = 1

class PiezoSpeakerBricklet(MQTTCallbackDevice):
	functions = {
		'beep': FunctionInfo(1, ['duration', 'frequency'], ['int', 'int'], [{0: 'off', 4294967295: 'infinite'}, {}], 'I H', [], [], ''),
		'morse_code': FunctionInfo(2, ['morse', 'frequency'], ['string', 'int'], [{}, {}], '60s H', [], [], ''),
		'calibrate': FunctionInfo(3, [], [], [], '', ['calibration'], [{}], '!'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'beep_finished': CallbackInfo(4, [], [], '', None),
		'morse_code_finished': CallbackInfo(5, [], [], '', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 3; re[2] = 3; re[3] = 1; re[255] = 1

class PiezoSpeakerV2Bricklet(MQTTCallbackDevice):
	functions = {
		'set_beep': FunctionInfo(1, ['frequency', 'volume', 'duration'], ['int', 'int', 'int'], [{}, {}, {0: 'off', 4294967295: 'infinite'}], 'H B I', [], [], ''),
		'get_beep': FunctionInfo(2, [], [], [], '', ['frequency', 'volume', 'duration', 'duration_remaining'], [{}, {}, {0: 'off', 4294967295: 'infinite'}, {}], 'H B I I'),
		'set_alarm': FunctionInfo(3, ['start_frequency', 'end_frequency', 'step_size', 'step_delay', 'volume', 'duration'], ['int', 'int', 'int', 'int', 'int', 'int'], [{}, {}, {}, {}, {}, {0: 'off', 4294967295: 'infinite'}], 'H H H H B I', [], [], ''),
		'get_alarm': FunctionInfo(4, [], [], [], '', ['start_frequency', 'end_frequency', 'step_size', 'step_delay', 'volume', 'duration', 'duration_remaining', 'current_frequency'], [{}, {}, {}, {}, {}, {0: 'off', 4294967295: 'infinite'}, {}, {}], 'H H H H B I I H'),
		'update_volume': FunctionInfo(5, ['volume'], ['int'], [{}], 'B', [], [], ''),
		'update_frequency': FunctionInfo(6, ['frequency'], ['int'], [{}], 'H', [], [], ''),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'beep_finished': CallbackInfo(7, [], [], '', None),
		'alarm_finished': CallbackInfo(8, [], [], '', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 3; re[2] = 1; re[3] = 3; re[4] = 1; re[5] = 3; re[6] = 3; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class PTCBricklet(MQTTCallbackDevice):
	functions = {
		'get_temperature': FunctionInfo(1, [], [], [], '', ['temperature'], [{}], 'i'),
		'get_resistance': FunctionInfo(2, [], [], [], '', ['resistance'], [{}], 'i'),
		'set_temperature_callback_period': FunctionInfo(3, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_temperature_callback_period': FunctionInfo(4, [], [], [], '', ['period'], [{}], 'I'),
		'set_resistance_callback_period': FunctionInfo(5, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_resistance_callback_period': FunctionInfo(6, [], [], [], '', ['period'], [{}], 'I'),
		'set_temperature_callback_threshold': FunctionInfo(7, ['option', 'min', 'max'], ['char', 'int', 'int'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c i i', [], [], ''),
		'get_temperature_callback_threshold': FunctionInfo(8, [], [], [], '', ['option', 'min', 'max'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c i i'),
		'set_resistance_callback_threshold': FunctionInfo(9, ['option', 'min', 'max'], ['char', 'int', 'int'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c i i', [], [], ''),
		'get_resistance_callback_threshold': FunctionInfo(10, [], [], [], '', ['option', 'min', 'max'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c i i'),
		'set_debounce_period': FunctionInfo(11, ['debounce'], ['int'], [{}], 'I', [], [], ''),
		'get_debounce_period': FunctionInfo(12, [], [], [], '', ['debounce'], [{}], 'I'),
		'set_noise_rejection_filter': FunctionInfo(17, ['filter'], ['int'], [{0: '50hz', 1: '60hz'}], 'B', [], [], ''),
		'get_noise_rejection_filter': FunctionInfo(18, [], [], [], '', ['filter'], [{0: '50hz', 1: '60hz'}], 'B'),
		'is_sensor_connected': FunctionInfo(19, [], [], [], '', ['connected'], [{}], '!'),
		'set_wire_mode': FunctionInfo(20, ['mode'], ['int'], [{2: '2', 3: '3', 4: '4'}], 'B', [], [], ''),
		'get_wire_mode': FunctionInfo(21, [], [], [], '', ['mode'], [{2: '2', 3: '3', 4: '4'}], 'B'),
		'set_sensor_connected_callback_configuration': FunctionInfo(22, ['enabled'], ['bool'], [{}], '!', [], [], ''),
		'get_sensor_connected_callback_configuration': FunctionInfo(23, [], [], [], '', ['enabled'], [{}], '!'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'temperature': CallbackInfo(13, ['temperature'], [{}], 'i', None),
		'temperature_reached': CallbackInfo(14, ['temperature'], [{}], 'i', None),
		'resistance': CallbackInfo(15, ['resistance'], [{}], 'i', None),
		'resistance_reached': CallbackInfo(16, ['resistance'], [{}], 'i', None),
		'sensor_connected': CallbackInfo(24, ['connected'], [{}], '!', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 1; re[3] = 2; re[4] = 1; re[5] = 2; re[6] = 1; re[7] = 2; re[8] = 1; re[9] = 2; re[10] = 1; re[11] = 2; re[12] = 1; re[17] = 3; re[18] = 1; re[19] = 1; re[20] = 3; re[21] = 1; re[22] = 2; re[23] = 1; re[255] = 1

class PTCV2Bricklet(MQTTCallbackDevice):
	functions = {
		'get_temperature': FunctionInfo(1, [], [], [], '', ['temperature'], [{}], 'i'),
		'set_temperature_callback_configuration': FunctionInfo(2, ['period', 'value_has_to_change', 'option', 'min', 'max'], ['int', 'bool', 'char', 'int', 'int'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c i i', [], [], ''),
		'get_temperature_callback_configuration': FunctionInfo(3, [], [], [], '', ['period', 'value_has_to_change', 'option', 'min', 'max'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c i i'),
		'get_resistance': FunctionInfo(5, [], [], [], '', ['resistance'], [{}], 'i'),
		'set_resistance_callback_configuration': FunctionInfo(6, ['period', 'value_has_to_change', 'option', 'min', 'max'], ['int', 'bool', 'char', 'int', 'int'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c i i', [], [], ''),
		'get_resistance_callback_configuration': FunctionInfo(7, [], [], [], '', ['period', 'value_has_to_change', 'option', 'min', 'max'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c i i'),
		'set_noise_rejection_filter': FunctionInfo(9, ['filter'], ['int'], [{0: '50hz', 1: '60hz'}], 'B', [], [], ''),
		'get_noise_rejection_filter': FunctionInfo(10, [], [], [], '', ['filter'], [{0: '50hz', 1: '60hz'}], 'B'),
		'is_sensor_connected': FunctionInfo(11, [], [], [], '', ['connected'], [{}], '!'),
		'set_wire_mode': FunctionInfo(12, ['mode'], ['int'], [{2: '2', 3: '3', 4: '4'}], 'B', [], [], ''),
		'get_wire_mode': FunctionInfo(13, [], [], [], '', ['mode'], [{2: '2', 3: '3', 4: '4'}], 'B'),
		'set_moving_average_configuration': FunctionInfo(14, ['moving_average_length_resistance', 'moving_average_length_temperature'], ['int', 'int'], [{}, {}], 'H H', [], [], ''),
		'get_moving_average_configuration': FunctionInfo(15, [], [], [], '', ['moving_average_length_resistance', 'moving_average_length_temperature'], [{}, {}], 'H H'),
		'set_sensor_connected_callback_configuration': FunctionInfo(16, ['enabled'], ['bool'], [{}], '!', [], [], ''),
		'get_sensor_connected_callback_configuration': FunctionInfo(17, [], [], [], '', ['enabled'], [{}], '!'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'temperature': CallbackInfo(4, ['temperature'], [{}], 'i', None),
		'resistance': CallbackInfo(8, ['resistance'], [{}], 'i', None),
		'sensor_connected': CallbackInfo(18, ['connected'], [{}], '!', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 2; re[3] = 1; re[5] = 1; re[6] = 2; re[7] = 1; re[9] = 3; re[10] = 1; re[11] = 1; re[12] = 3; re[13] = 1; re[14] = 3; re[15] = 1; re[16] = 2; re[17] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class RealTimeClockBricklet(MQTTCallbackDevice):
	functions = {
		'set_date_time': FunctionInfo(1, ['year', 'month', 'day', 'hour', 'minute', 'second', 'centisecond', 'weekday'], ['int', 'int', 'int', 'int', 'int', 'int', 'int', 'int'], [{}, {}, {}, {}, {}, {}, {}, {1: 'monday', 2: 'tuesday', 3: 'wednesday', 4: 'thursday', 5: 'friday', 6: 'saturday', 7: 'sunday'}], 'H B B B B B B B', [], [], ''),
		'get_date_time': FunctionInfo(2, [], [], [], '', ['year', 'month', 'day', 'hour', 'minute', 'second', 'centisecond', 'weekday'], [{}, {}, {}, {}, {}, {}, {}, {1: 'monday', 2: 'tuesday', 3: 'wednesday', 4: 'thursday', 5: 'friday', 6: 'saturday', 7: 'sunday'}], 'H B B B B B B B'),
		'get_timestamp': FunctionInfo(3, [], [], [], '', ['timestamp'], [{}], 'q'),
		'set_offset': FunctionInfo(4, ['offset'], ['int'], [{}], 'b', [], [], ''),
		'get_offset': FunctionInfo(5, [], [], [], '', ['offset'], [{}], 'b'),
		'set_date_time_callback_period': FunctionInfo(6, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_date_time_callback_period': FunctionInfo(7, [], [], [], '', ['period'], [{}], 'I'),
		'set_alarm': FunctionInfo(8, ['month', 'day', 'hour', 'minute', 'second', 'weekday', 'interval'], ['int', 'int', 'int', 'int', 'int', 'int', 'int'], [{-1: 'disabled'}, {-1: 'disabled'}, {-1: 'disabled'}, {-1: 'disabled'}, {-1: 'disabled'}, {-1: 'disabled'}, {-1: 'disabled'}], 'b b b b b b i', [], [], ''),
		'get_alarm': FunctionInfo(9, [], [], [], '', ['month', 'day', 'hour', 'minute', 'second', 'weekday', 'interval'], [{-1: 'disabled'}, {-1: 'disabled'}, {-1: 'disabled'}, {-1: 'disabled'}, {-1: 'disabled'}, {-1: 'disabled'}, {-1: 'disabled'}], 'b b b b b b i'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'date_time': CallbackInfo(10, ['year', 'month', 'day', 'hour', 'minute', 'second', 'centisecond', 'weekday', 'timestamp'], [{}, {}, {}, {}, {}, {}, {}, {1: 'monday', 2: 'tuesday', 3: 'wednesday', 4: 'thursday', 5: 'friday', 6: 'saturday', 7: 'sunday'}, {}], 'H B B B B B B B q', None),
		'alarm': CallbackInfo(11, ['year', 'month', 'day', 'hour', 'minute', 'second', 'centisecond', 'weekday', 'timestamp'], [{}, {}, {}, {}, {}, {}, {}, {1: 'monday', 2: 'tuesday', 3: 'wednesday', 4: 'thursday', 5: 'friday', 6: 'saturday', 7: 'sunday'}, {}], 'H B B B B B B B q', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 3; re[2] = 1; re[3] = 1; re[4] = 3; re[5] = 1; re[6] = 2; re[7] = 1; re[8] = 2; re[9] = 1; re[255] = 1

class RealTimeClockV2Bricklet(MQTTCallbackDevice):
	functions = {
		'set_date_time': FunctionInfo(1, ['year', 'month', 'day', 'hour', 'minute', 'second', 'centisecond', 'weekday'], ['int', 'int', 'int', 'int', 'int', 'int', 'int', 'int'], [{}, {}, {}, {}, {}, {}, {}, {1: 'monday', 2: 'tuesday', 3: 'wednesday', 4: 'thursday', 5: 'friday', 6: 'saturday', 7: 'sunday'}], 'H B B B B B B B', [], [], ''),
		'get_date_time': FunctionInfo(2, [], [], [], '', ['year', 'month', 'day', 'hour', 'minute', 'second', 'centisecond', 'weekday', 'timestamp'], [{}, {}, {}, {}, {}, {}, {}, {1: 'monday', 2: 'tuesday', 3: 'wednesday', 4: 'thursday', 5: 'friday', 6: 'saturday', 7: 'sunday'}, {}], 'H B B B B B B B q'),
		'get_timestamp': FunctionInfo(3, [], [], [], '', ['timestamp'], [{}], 'q'),
		'set_offset': FunctionInfo(4, ['offset'], ['int'], [{}], 'b', [], [], ''),
		'get_offset': FunctionInfo(5, [], [], [], '', ['offset'], [{}], 'b'),
		'set_date_time_callback_configuration': FunctionInfo(6, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_date_time_callback_configuration': FunctionInfo(7, [], [], [], '', ['period'], [{}], 'I'),
		'set_alarm': FunctionInfo(8, ['month', 'day', 'hour', 'minute', 'second', 'weekday', 'interval'], ['int', 'int', 'int', 'int', 'int', 'int', 'int'], [{-1: 'disabled'}, {-1: 'disabled'}, {-1: 'disabled'}, {-1: 'disabled'}, {-1: 'disabled'}, {-1: 'disabled'}, {-1: 'disabled'}], 'b b b b b b i', [], [], ''),
		'get_alarm': FunctionInfo(9, [], [], [], '', ['month', 'day', 'hour', 'minute', 'second', 'weekday', 'interval'], [{-1: 'disabled'}, {-1: 'disabled'}, {-1: 'disabled'}, {-1: 'disabled'}, {-1: 'disabled'}, {-1: 'disabled'}, {-1: 'disabled'}], 'b b b b b b i'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'date_time': CallbackInfo(10, ['year', 'month', 'day', 'hour', 'minute', 'second', 'centisecond', 'weekday', 'timestamp'], [{}, {}, {}, {}, {}, {}, {}, {1: 'monday', 2: 'tuesday', 3: 'wednesday', 4: 'thursday', 5: 'friday', 6: 'saturday', 7: 'sunday'}, {}], 'H B B B B B B B q', None),
		'alarm': CallbackInfo(11, ['year', 'month', 'day', 'hour', 'minute', 'second', 'centisecond', 'weekday', 'timestamp'], [{}, {}, {}, {}, {}, {}, {}, {1: 'monday', 2: 'tuesday', 3: 'wednesday', 4: 'thursday', 5: 'friday', 6: 'saturday', 7: 'sunday'}, {}], 'H B B B B B B B q', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 3; re[2] = 1; re[3] = 1; re[4] = 3; re[5] = 1; re[6] = 2; re[7] = 1; re[8] = 2; re[9] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class REDBrick(MQTTCallbackDevice):
	functions = {
		'create_session': FunctionInfo(1, ['lifetime'], ['int'], [{}], 'I', ['error_code', 'session_id'], [{0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}, {}], 'B H'),
		'expire_session': FunctionInfo(2, ['session_id'], ['int'], [{}], 'H', ['error_code'], [{0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}], 'B'),
		'expire_session_unchecked': FunctionInfo(3, ['session_id'], ['int'], [{}], 'H', [], [], ''),
		'keep_session_alive': FunctionInfo(4, ['session_id', 'lifetime'], ['int', 'int'], [{}, {}], 'H I', ['error_code'], [{0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}], 'B'),
		'release_object': FunctionInfo(5, ['object_id', 'session_id'], ['int', 'int'], [{}, {}], 'H H', ['error_code'], [{0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}], 'B'),
		'release_object_unchecked': FunctionInfo(6, ['object_id', 'session_id'], ['int', 'int'], [{}, {}], 'H H', [], [], ''),
		'allocate_string': FunctionInfo(7, ['length_to_reserve', 'buffer', 'session_id'], ['int', 'string', 'int'], [{}, {}, {}], 'I 58s H', ['error_code', 'string_id'], [{0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}, {}], 'B H'),
		'truncate_string': FunctionInfo(8, ['string_id', 'length'], ['int', 'int'], [{}, {}], 'H I', ['error_code'], [{0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}], 'B'),
		'get_string_length': FunctionInfo(9, ['string_id'], ['int'], [{}], 'H', ['error_code', 'length'], [{0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}, {}], 'B I'),
		'set_string_chunk': FunctionInfo(10, ['string_id', 'offset', 'buffer'], ['int', 'int', 'string'], [{}, {}, {}], 'H I 58s', ['error_code'], [{0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}], 'B'),
		'get_string_chunk': FunctionInfo(11, ['string_id', 'offset'], ['int', 'int'], [{}, {}], 'H I', ['error_code', 'buffer'], [{0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}, {}], 'B 63s'),
		'allocate_list': FunctionInfo(12, ['length_to_reserve', 'session_id'], ['int', 'int'], [{}, {}], 'H H', ['error_code', 'list_id'], [{0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}, {}], 'B H'),
		'get_list_length': FunctionInfo(13, ['list_id'], ['int'], [{}], 'H', ['error_code', 'length'], [{0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}, {}], 'B H'),
		'get_list_item': FunctionInfo(14, ['list_id', 'index', 'session_id'], ['int', 'int', 'int'], [{}, {}, {}], 'H H H', ['error_code', 'item_object_id', 'type'], [{0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}, {}, {0: 'string', 1: 'list', 2: 'file', 3: 'directory', 4: 'process', 5: 'program'}], 'B H B'),
		'append_to_list': FunctionInfo(15, ['list_id', 'item_object_id'], ['int', 'int'], [{}, {}], 'H H', ['error_code'], [{0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}], 'B'),
		'remove_from_list': FunctionInfo(16, ['list_id', 'index'], ['int', 'int'], [{}, {}], 'H H', ['error_code'], [{0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}], 'B'),
		'open_file': FunctionInfo(17, ['name_string_id', 'flags', 'permissions', 'uid', 'gid', 'session_id'], ['int', 'int', 'int', 'int', 'int', 'int'], [{}, {1: 'read_only', 2: 'write_only', 4: 'read_write', 8: 'append', 16: 'create', 32: 'exclusive', 64: 'non_blocking', 128: 'truncate', 256: 'temporary', 512: 'replace'}, {448: 'user_all', 256: 'user_read', 128: 'user_write', 64: 'user_execute', 56: 'group_all', 32: 'group_read', 16: 'group_write', 8: 'group_execute', 7: 'others_all', 4: 'others_read', 2: 'others_write', 1: 'others_execute'}, {}, {}, {}], 'H I H I I H', ['error_code', 'file_id'], [{0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}, {}], 'B H'),
		'create_pipe': FunctionInfo(18, ['flags', 'length', 'session_id'], ['int', 'int', 'int'], [{1: 'non_blocking_read', 2: 'non_blocking_write'}, {}, {}], 'I Q H', ['error_code', 'file_id'], [{0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}, {}], 'B H'),
		'get_file_info': FunctionInfo(19, ['file_id', 'session_id'], ['int', 'int'], [{}, {}], 'H H', ['error_code', 'type', 'name_string_id', 'flags', 'permissions', 'uid', 'gid', 'length', 'access_timestamp', 'modification_timestamp', 'status_change_timestamp'], [{0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}, {0: 'unknown', 1: 'regular', 2: 'directory', 3: 'character', 4: 'block', 5: 'fifo', 6: 'symlink', 7: 'socket', 8: 'pipe'}, {}, {}, {448: 'user_all', 256: 'user_read', 128: 'user_write', 64: 'user_execute', 56: 'group_all', 32: 'group_read', 16: 'group_write', 8: 'group_execute', 7: 'others_all', 4: 'others_read', 2: 'others_write', 1: 'others_execute'}, {}, {}, {}, {}, {}, {}], 'B B H I H I I Q Q Q Q'),
		'read_file': FunctionInfo(20, ['file_id', 'length_to_read'], ['int', 'int'], [{}, {}], 'H B', ['error_code', 'buffer', 'length_read'], [{0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}, {}, {}], 'B 62B B'),
		'read_file_async': FunctionInfo(21, ['file_id', 'length_to_read'], ['int', 'int'], [{}, {}], 'H Q', [], [], ''),
		'abort_async_file_read': FunctionInfo(22, ['file_id'], ['int'], [{}], 'H', ['error_code'], [{0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}], 'B'),
		'write_file': FunctionInfo(23, ['file_id', 'buffer', 'length_to_write'], ['int', ('int', 61), 'int'], [{}, {}, {}], 'H 61B B', ['error_code', 'length_written'], [{0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}, {}], 'B B'),
		'write_file_unchecked': FunctionInfo(24, ['file_id', 'buffer', 'length_to_write'], ['int', ('int', 61), 'int'], [{}, {}, {}], 'H 61B B', [], [], ''),
		'write_file_async': FunctionInfo(25, ['file_id', 'buffer', 'length_to_write'], ['int', ('int', 61), 'int'], [{}, {}, {}], 'H 61B B', [], [], ''),
		'set_file_position': FunctionInfo(26, ['file_id', 'offset', 'origin'], ['int', 'int', 'int'], [{}, {}, {0: 'beginning', 1: 'current', 2: 'end'}], 'H q B', ['error_code', 'position'], [{0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}, {}], 'B Q'),
		'get_file_position': FunctionInfo(27, ['file_id'], ['int'], [{}], 'H', ['error_code', 'position'], [{0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}, {}], 'B Q'),
		'set_file_events': FunctionInfo(28, ['file_id', 'events'], ['int', 'int'], [{}, {1: 'readable', 2: 'writable'}], 'H H', ['error_code'], [{0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}], 'B'),
		'get_file_events': FunctionInfo(29, ['file_id'], ['int'], [{}], 'H', ['error_code', 'events'], [{0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}, {1: 'readable', 2: 'writable'}], 'B H'),
		'open_directory': FunctionInfo(33, ['name_string_id', 'session_id'], ['int', 'int'], [{}, {}], 'H H', ['error_code', 'directory_id'], [{0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}, {}], 'B H'),
		'get_directory_name': FunctionInfo(34, ['directory_id', 'session_id'], ['int', 'int'], [{}, {}], 'H H', ['error_code', 'name_string_id'], [{0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}, {}], 'B H'),
		'get_next_directory_entry': FunctionInfo(35, ['directory_id', 'session_id'], ['int', 'int'], [{}, {}], 'H H', ['error_code', 'name_string_id', 'type'], [{0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}, {}, {0: 'unknown', 1: 'regular', 2: 'directory', 3: 'character', 4: 'block', 5: 'fifo', 6: 'symlink', 7: 'socket'}], 'B H B'),
		'rewind_directory': FunctionInfo(36, ['directory_id'], ['int'], [{}], 'H', ['error_code'], [{0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}], 'B'),
		'create_directory': FunctionInfo(37, ['name_string_id', 'flags', 'permissions', 'uid', 'gid'], ['int', 'int', 'int', 'int', 'int'], [{}, {1: 'recursive', 2: 'exclusive'}, {448: 'user_all', 256: 'user_read', 128: 'user_write', 64: 'user_execute', 56: 'group_all', 32: 'group_read', 16: 'group_write', 8: 'group_execute', 7: 'others_all', 4: 'others_read', 2: 'others_write', 1: 'others_execute'}, {}, {}], 'H I H I I', ['error_code'], [{0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}], 'B'),
		'get_processes': FunctionInfo(38, ['session_id'], ['int'], [{}], 'H', ['error_code', 'processes_list_id'], [{0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}, {}], 'B H'),
		'spawn_process': FunctionInfo(39, ['executable_string_id', 'arguments_list_id', 'environment_list_id', 'working_directory_string_id', 'uid', 'gid', 'stdin_file_id', 'stdout_file_id', 'stderr_file_id', 'session_id'], ['int', 'int', 'int', 'int', 'int', 'int', 'int', 'int', 'int', 'int'], [{}, {}, {}, {}, {}, {}, {}, {}, {}, {}], 'H H H H I I H H H H', ['error_code', 'process_id'], [{0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}, {}], 'B H'),
		'kill_process': FunctionInfo(40, ['process_id', 'signal'], ['int', 'int'], [{}, {2: 'interrupt', 3: 'quit', 6: 'abort', 9: 'kill', 10: 'user1', 12: 'user2', 15: 'terminate', 18: 'continue', 19: 'stop'}], 'H B', ['error_code'], [{0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}], 'B'),
		'get_process_command': FunctionInfo(41, ['process_id', 'session_id'], ['int', 'int'], [{}, {}], 'H H', ['error_code', 'executable_string_id', 'arguments_list_id', 'environment_list_id', 'working_directory_string_id'], [{0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}, {}, {}, {}, {}], 'B H H H H'),
		'get_process_identity': FunctionInfo(42, ['process_id'], ['int'], [{}], 'H', ['error_code', 'pid', 'uid', 'gid'], [{0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}, {}, {}, {}], 'B I I I'),
		'get_process_stdio': FunctionInfo(43, ['process_id', 'session_id'], ['int', 'int'], [{}, {}], 'H H', ['error_code', 'stdin_file_id', 'stdout_file_id', 'stderr_file_id'], [{0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}, {}, {}, {}], 'B H H H'),
		'get_process_state': FunctionInfo(44, ['process_id'], ['int'], [{}], 'H', ['error_code', 'state', 'timestamp', 'exit_code'], [{0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}, {0: 'unknown', 1: 'running', 2: 'error', 3: 'exited', 4: 'killed', 5: 'stopped'}, {}, {}], 'B B Q B'),
		'get_programs': FunctionInfo(46, ['session_id'], ['int'], [{}], 'H', ['error_code', 'programs_list_id'], [{0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}, {}], 'B H'),
		'define_program': FunctionInfo(47, ['identifier_string_id', 'session_id'], ['int', 'int'], [{}, {}], 'H H', ['error_code', 'program_id'], [{0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}, {}], 'B H'),
		'purge_program': FunctionInfo(48, ['program_id', 'cookie'], ['int', 'int'], [{}, {}], 'H I', ['error_code'], [{0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}], 'B'),
		'get_program_identifier': FunctionInfo(49, ['program_id', 'session_id'], ['int', 'int'], [{}, {}], 'H H', ['error_code', 'identifier_string_id'], [{0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}, {}], 'B H'),
		'get_program_root_directory': FunctionInfo(50, ['program_id', 'session_id'], ['int', 'int'], [{}, {}], 'H H', ['error_code', 'root_directory_string_id'], [{0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}, {}], 'B H'),
		'set_program_command': FunctionInfo(51, ['program_id', 'executable_string_id', 'arguments_list_id', 'environment_list_id', 'working_directory_string_id'], ['int', 'int', 'int', 'int', 'int'], [{}, {}, {}, {}, {}], 'H H H H H', ['error_code'], [{0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}], 'B'),
		'get_program_command': FunctionInfo(52, ['program_id', 'session_id'], ['int', 'int'], [{}, {}], 'H H', ['error_code', 'executable_string_id', 'arguments_list_id', 'environment_list_id', 'working_directory_string_id'], [{0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}, {}, {}, {}, {}], 'B H H H H'),
		'set_program_stdio_redirection': FunctionInfo(53, ['program_id', 'stdin_redirection', 'stdin_file_name_string_id', 'stdout_redirection', 'stdout_file_name_string_id', 'stderr_redirection', 'stderr_file_name_string_id'], ['int', 'int', 'int', 'int', 'int', 'int', 'int'], [{}, {0: 'dev_null', 1: 'pipe', 2: 'file', 3: 'individual_log', 4: 'continuous_log', 5: 'stdout'}, {}, {0: 'dev_null', 1: 'pipe', 2: 'file', 3: 'individual_log', 4: 'continuous_log', 5: 'stdout'}, {}, {0: 'dev_null', 1: 'pipe', 2: 'file', 3: 'individual_log', 4: 'continuous_log', 5: 'stdout'}, {}], 'H B H B H B H', ['error_code'], [{0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}], 'B'),
		'get_program_stdio_redirection': FunctionInfo(54, ['program_id', 'session_id'], ['int', 'int'], [{}, {}], 'H H', ['error_code', 'stdin_redirection', 'stdin_file_name_string_id', 'stdout_redirection', 'stdout_file_name_string_id', 'stderr_redirection', 'stderr_file_name_string_id'], [{0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}, {0: 'dev_null', 1: 'pipe', 2: 'file', 3: 'individual_log', 4: 'continuous_log', 5: 'stdout'}, {}, {0: 'dev_null', 1: 'pipe', 2: 'file', 3: 'individual_log', 4: 'continuous_log', 5: 'stdout'}, {}, {0: 'dev_null', 1: 'pipe', 2: 'file', 3: 'individual_log', 4: 'continuous_log', 5: 'stdout'}, {}], 'B B H B H B H'),
		'set_program_schedule': FunctionInfo(55, ['program_id', 'start_mode', 'continue_after_error', 'start_interval', 'start_fields_string_id'], ['int', 'int', 'bool', 'int', 'int'], [{}, {0: 'never', 1: 'always', 2: 'interval', 3: 'cron'}, {}, {}, {}], 'H B ! I H', ['error_code'], [{0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}], 'B'),
		'get_program_schedule': FunctionInfo(56, ['program_id', 'session_id'], ['int', 'int'], [{}, {}], 'H H', ['error_code', 'start_mode', 'continue_after_error', 'start_interval', 'start_fields_string_id'], [{0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}, {0: 'never', 1: 'always', 2: 'interval', 3: 'cron'}, {}, {}, {}], 'B B ! I H'),
		'get_program_scheduler_state': FunctionInfo(57, ['program_id', 'session_id'], ['int', 'int'], [{}, {}], 'H H', ['error_code', 'state', 'timestamp', 'message_string_id'], [{0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}, {0: 'stopped', 1: 'running'}, {}, {}], 'B B Q H'),
		'continue_program_schedule': FunctionInfo(58, ['program_id'], ['int'], [{}], 'H', ['error_code'], [{0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}], 'B'),
		'start_program': FunctionInfo(59, ['program_id'], ['int'], [{}], 'H', ['error_code'], [{0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}], 'B'),
		'get_last_spawned_program_process': FunctionInfo(60, ['program_id', 'session_id'], ['int', 'int'], [{}, {}], 'H H', ['error_code', 'process_id', 'timestamp'], [{0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}, {}, {}], 'B H Q'),
		'get_custom_program_option_names': FunctionInfo(61, ['program_id', 'session_id'], ['int', 'int'], [{}, {}], 'H H', ['error_code', 'names_list_id'], [{0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}, {}], 'B H'),
		'set_custom_program_option_value': FunctionInfo(62, ['program_id', 'name_string_id', 'value_string_id'], ['int', 'int', 'int'], [{}, {}, {}], 'H H H', ['error_code'], [{0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}], 'B'),
		'get_custom_program_option_value': FunctionInfo(63, ['program_id', 'name_string_id', 'session_id'], ['int', 'int', 'int'], [{}, {}, {}], 'H H H', ['error_code', 'value_string_id'], [{0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}, {}], 'B H'),
		'remove_custom_program_option': FunctionInfo(64, ['program_id', 'name_string_id'], ['int', 'int'], [{}, {}], 'H H', ['error_code'], [{0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}], 'B'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'async_file_read': CallbackInfo(30, ['file_id', 'error_code', 'buffer', 'length_read'], [{}, {0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}, {}, {}], 'H B 60B B', None),
		'async_file_write': CallbackInfo(31, ['file_id', 'error_code', 'length_written'], [{}, {0: 'success', 1: 'unknown_error', 2: 'invalid_operation', 3: 'operation_aborted', 4: 'internal_error', 5: 'unknown_session_id', 6: 'no_free_session_id', 7: 'unknown_object_id', 8: 'no_free_object_id', 9: 'object_is_locked', 10: 'no_more_data', 11: 'wrong_list_item_type', 12: 'program_is_purged', 128: 'invalid_parameter', 129: 'no_free_memory', 130: 'no_free_space', 121: 'access_denied', 132: 'already_exists', 133: 'does_not_exist', 134: 'interrupted', 135: 'is_directory', 136: 'not_a_directory', 137: 'would_block', 138: 'overflow', 139: 'bad_file_descriptor', 140: 'out_of_range', 141: 'name_too_long', 142: 'invalid_seek', 143: 'not_supported', 144: 'too_many_open_files'}, {}], 'H B B', None),
		'file_events_occurred': CallbackInfo(32, ['file_id', 'events'], [{}, {1: 'readable', 2: 'writable'}], 'H H', None),
		'process_state_changed': CallbackInfo(45, ['process_id', 'state', 'timestamp', 'exit_code'], [{}, {0: 'unknown', 1: 'running', 2: 'error', 3: 'exited', 4: 'killed', 5: 'stopped'}, {}, {}], 'H B Q B', None),
		'program_scheduler_state_changed': CallbackInfo(65, ['program_id'], [{}], 'H', None),
		'program_process_spawned': CallbackInfo(66, ['program_id'], [{}], 'H', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 1; re[3] = 3; re[4] = 1; re[5] = 1; re[6] = 3; re[7] = 1; re[8] = 1; re[9] = 1; re[10] = 1; re[11] = 1; re[12] = 1; re[13] = 1; re[14] = 1; re[15] = 1; re[16] = 1; re[17] = 1; re[18] = 1; re[19] = 1; re[20] = 1; re[21] = 3; re[22] = 1; re[23] = 1; re[24] = 3; re[25] = 3; re[26] = 1; re[27] = 1; re[28] = 1; re[29] = 1; re[33] = 1; re[34] = 1; re[35] = 1; re[36] = 1; re[37] = 1; re[38] = 1; re[39] = 1; re[40] = 1; re[41] = 1; re[42] = 1; re[43] = 1; re[44] = 1; re[46] = 1; re[47] = 1; re[48] = 1; re[49] = 1; re[50] = 1; re[51] = 1; re[52] = 1; re[53] = 1; re[54] = 1; re[55] = 1; re[56] = 1; re[57] = 1; re[58] = 1; re[59] = 1; re[60] = 1; re[61] = 1; re[62] = 1; re[63] = 1; re[64] = 1; re[255] = 1

class RemoteSwitchBricklet(MQTTCallbackDevice):
	functions = {
		'switch_socket': FunctionInfo(1, ['house_code', 'receiver_code', 'switch_to'], ['int', 'int', 'int'], [{}, {}, {0: 'off', 1: 'on'}], 'B B B', [], [], ''),
		'get_switching_state': FunctionInfo(2, [], [], [], '', ['state'], [{0: 'ready', 1: 'busy'}], 'B'),
		'set_repeats': FunctionInfo(4, ['repeats'], ['int'], [{}], 'B', [], [], ''),
		'get_repeats': FunctionInfo(5, [], [], [], '', ['repeats'], [{}], 'B'),
		'switch_socket_a': FunctionInfo(6, ['house_code', 'receiver_code', 'switch_to'], ['int', 'int', 'int'], [{}, {}, {0: 'off', 1: 'on'}], 'B B B', [], [], ''),
		'switch_socket_b': FunctionInfo(7, ['address', 'unit', 'switch_to'], ['int', 'int', 'int'], [{}, {}, {0: 'off', 1: 'on'}], 'I B B', [], [], ''),
		'dim_socket_b': FunctionInfo(8, ['address', 'unit', 'dim_value'], ['int', 'int', 'int'], [{}, {}, {}], 'I B B', [], [], ''),
		'switch_socket_c': FunctionInfo(9, ['system_code', 'device_code', 'switch_to'], ['char', 'int', 'int'], [{}, {}, {0: 'off', 1: 'on'}], 'c B B', [], [], ''),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'switching_done': CallbackInfo(3, [], [], '', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 3; re[2] = 1; re[4] = 3; re[5] = 1; re[6] = 3; re[7] = 3; re[8] = 3; re[9] = 3; re[255] = 1

class RemoteSwitchV2Bricklet(MQTTCallbackDevice):
	functions = {
		'get_switching_state': FunctionInfo(1, [], [], [], '', ['state'], [{0: 'ready', 1: 'busy'}], 'B'),
		'set_repeats': FunctionInfo(3, ['repeats'], ['int'], [{}], 'B', [], [], ''),
		'get_repeats': FunctionInfo(4, [], [], [], '', ['repeats'], [{}], 'B'),
		'switch_socket_a': FunctionInfo(5, ['house_code', 'receiver_code', 'switch_to'], ['int', 'int', 'int'], [{}, {}, {0: 'off', 1: 'on'}], 'B B B', [], [], ''),
		'switch_socket_b': FunctionInfo(6, ['address', 'unit', 'switch_to'], ['int', 'int', 'int'], [{}, {}, {0: 'off', 1: 'on'}], 'I B B', [], [], ''),
		'dim_socket_b': FunctionInfo(7, ['address', 'unit', 'dim_value'], ['int', 'int', 'int'], [{}, {}, {}], 'I B B', [], [], ''),
		'switch_socket_c': FunctionInfo(8, ['system_code', 'device_code', 'switch_to'], ['char', 'int', 'int'], [{}, {}, {0: 'off', 1: 'on'}], 'c B B', [], [], ''),
		'set_remote_configuration': FunctionInfo(9, ['remote_type', 'minimum_repeats', 'callback_enabled'], ['int', 'int', 'bool'], [{0: 'a', 1: 'b', 2: 'c'}, {}, {}], 'B H !', [], [], ''),
		'get_remote_configuration': FunctionInfo(10, [], [], [], '', ['remote_type', 'minimum_repeats', 'callback_enabled'], [{0: 'a', 1: 'b', 2: 'c'}, {}, {}], 'B H !'),
		'get_remote_status_a': FunctionInfo(11, [], [], [], '', ['house_code', 'receiver_code', 'switch_to', 'repeats'], [{}, {}, {0: 'off', 1: 'on'}, {}], 'B B B H'),
		'get_remote_status_b': FunctionInfo(12, [], [], [], '', ['address', 'unit', 'switch_to', 'dim_value', 'repeats'], [{}, {}, {0: 'off', 1: 'on'}, {}, {}], 'I B B B H'),
		'get_remote_status_c': FunctionInfo(13, [], [], [], '', ['system_code', 'device_code', 'switch_to', 'repeats'], [{}, {}, {0: 'off', 1: 'on'}, {}], 'c B B H'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'switching_done': CallbackInfo(2, [], [], '', None),
		'remote_status_a': CallbackInfo(14, ['house_code', 'receiver_code', 'switch_to', 'repeats'], [{}, {}, {0: 'off', 1: 'on'}, {}], 'B B B H', None),
		'remote_status_b': CallbackInfo(15, ['address', 'unit', 'switch_to', 'dim_value', 'repeats'], [{}, {}, {0: 'off', 1: 'on'}, {}, {}], 'I B B B H', None),
		'remote_status_c': CallbackInfo(16, ['system_code', 'device_code', 'switch_to', 'repeats'], [{}, {}, {0: 'off', 1: 'on'}, {}], 'c B B H', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[3] = 3; re[4] = 1; re[5] = 3; re[6] = 3; re[7] = 3; re[8] = 3; re[9] = 3; re[10] = 1; re[11] = 1; re[12] = 1; re[13] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class RGBLEDBricklet(MQTTCallbackDevice):
	functions = {
		'set_rgb_value': FunctionInfo(1, ['r', 'g', 'b'], ['int', 'int', 'int'], [{}, {}, {}], 'B B B', [], [], ''),
		'get_rgb_value': FunctionInfo(2, [], [], [], '', ['r', 'g', 'b'], [{}, {}, {}], 'B B B'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 3; re[2] = 1; re[255] = 1

class RGBLEDButtonBricklet(MQTTCallbackDevice):
	functions = {
		'set_color': FunctionInfo(1, ['red', 'green', 'blue'], ['int', 'int', 'int'], [{}, {}, {}], 'B B B', [], [], ''),
		'get_color': FunctionInfo(2, [], [], [], '', ['red', 'green', 'blue'], [{}, {}, {}], 'B B B'),
		'get_button_state': FunctionInfo(3, [], [], [], '', ['state'], [{0: 'pressed', 1: 'released'}], 'B'),
		'set_color_calibration': FunctionInfo(5, ['red', 'green', 'blue'], ['int', 'int', 'int'], [{}, {}, {}], 'B B B', [], [], ''),
		'get_color_calibration': FunctionInfo(6, [], [], [], '', ['red', 'green', 'blue'], [{}, {}, {}], 'B B B'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'button_state_changed': CallbackInfo(4, ['state'], [{0: 'pressed', 1: 'released'}], 'B', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 3; re[2] = 1; re[3] = 1; re[5] = 3; re[6] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class RGBLEDMatrixBricklet(MQTTCallbackDevice):
	functions = {
		'set_red': FunctionInfo(1, ['red'], [('int', 64)], [{}], '64B', [], [], ''),
		'get_red': FunctionInfo(2, [], [], [], '', ['red'], [{}], '64B'),
		'set_green': FunctionInfo(3, ['green'], [('int', 64)], [{}], '64B', [], [], ''),
		'get_green': FunctionInfo(4, [], [], [], '', ['green'], [{}], '64B'),
		'set_blue': FunctionInfo(5, ['blue'], [('int', 64)], [{}], '64B', [], [], ''),
		'get_blue': FunctionInfo(6, [], [], [], '', ['blue'], [{}], '64B'),
		'set_frame_duration': FunctionInfo(7, ['frame_duration'], ['int'], [{}], 'H', [], [], ''),
		'get_frame_duration': FunctionInfo(8, [], [], [], '', ['frame_duration'], [{}], 'H'),
		'draw_frame': FunctionInfo(9, [], [], [], '', [], [], ''),
		'get_supply_voltage': FunctionInfo(10, [], [], [], '', ['voltage'], [{}], 'H'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'frame_started': CallbackInfo(11, ['frame_number'], [{}], 'I', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 3; re[2] = 1; re[3] = 3; re[4] = 1; re[5] = 3; re[6] = 1; re[7] = 3; re[8] = 1; re[9] = 3; re[10] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class RGBLEDV2Bricklet(MQTTCallbackDevice):
	functions = {
		'set_rgb_value': FunctionInfo(1, ['r', 'g', 'b'], ['int', 'int', 'int'], [{}, {}, {}], 'B B B', [], [], ''),
		'get_rgb_value': FunctionInfo(2, [], [], [], '', ['r', 'g', 'b'], [{}, {}, {}], 'B B B'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 3; re[2] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class RotaryEncoderBricklet(MQTTCallbackDevice):
	functions = {
		'get_count': FunctionInfo(1, ['reset'], ['bool'], [{}], '!', ['count'], [{}], 'i'),
		'set_count_callback_period': FunctionInfo(2, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_count_callback_period': FunctionInfo(3, [], [], [], '', ['period'], [{}], 'I'),
		'set_count_callback_threshold': FunctionInfo(4, ['option', 'min', 'max'], ['char', 'int', 'int'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c i i', [], [], ''),
		'get_count_callback_threshold': FunctionInfo(5, [], [], [], '', ['option', 'min', 'max'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c i i'),
		'set_debounce_period': FunctionInfo(6, ['debounce'], ['int'], [{}], 'I', [], [], ''),
		'get_debounce_period': FunctionInfo(7, [], [], [], '', ['debounce'], [{}], 'I'),
		'is_pressed': FunctionInfo(10, [], [], [], '', ['pressed'], [{}], '!'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'count': CallbackInfo(8, ['count'], [{}], 'i', None),
		'count_reached': CallbackInfo(9, ['count'], [{}], 'i', None),
		'pressed': CallbackInfo(11, [], [], '', None),
		'released': CallbackInfo(12, [], [], '', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 2; re[3] = 1; re[4] = 2; re[5] = 1; re[6] = 2; re[7] = 1; re[10] = 1; re[255] = 1

class RotaryEncoderV2Bricklet(MQTTCallbackDevice):
	functions = {
		'get_count': FunctionInfo(1, ['reset'], ['bool'], [{}], '!', ['count'], [{}], 'i'),
		'set_count_callback_configuration': FunctionInfo(2, ['period', 'value_has_to_change', 'option', 'min', 'max'], ['int', 'bool', 'char', 'int', 'int'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c i i', [], [], ''),
		'get_count_callback_configuration': FunctionInfo(3, [], [], [], '', ['period', 'value_has_to_change', 'option', 'min', 'max'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c i i'),
		'is_pressed': FunctionInfo(5, [], [], [], '', ['pressed'], [{}], '!'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'count': CallbackInfo(4, ['count'], [{}], 'i', None),
		'pressed': CallbackInfo(6, [], [], '', None),
		'released': CallbackInfo(7, [], [], '', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 2; re[3] = 1; re[5] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class RotaryPotiBricklet(MQTTCallbackDevice):
	functions = {
		'get_position': FunctionInfo(1, [], [], [], '', ['position'], [{}], 'h'),
		'get_analog_value': FunctionInfo(2, [], [], [], '', ['value'], [{}], 'H'),
		'set_position_callback_period': FunctionInfo(3, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_position_callback_period': FunctionInfo(4, [], [], [], '', ['period'], [{}], 'I'),
		'set_analog_value_callback_period': FunctionInfo(5, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_analog_value_callback_period': FunctionInfo(6, [], [], [], '', ['period'], [{}], 'I'),
		'set_position_callback_threshold': FunctionInfo(7, ['option', 'min', 'max'], ['char', 'int', 'int'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c h h', [], [], ''),
		'get_position_callback_threshold': FunctionInfo(8, [], [], [], '', ['option', 'min', 'max'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c h h'),
		'set_analog_value_callback_threshold': FunctionInfo(9, ['option', 'min', 'max'], ['char', 'int', 'int'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c H H', [], [], ''),
		'get_analog_value_callback_threshold': FunctionInfo(10, [], [], [], '', ['option', 'min', 'max'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c H H'),
		'set_debounce_period': FunctionInfo(11, ['debounce'], ['int'], [{}], 'I', [], [], ''),
		'get_debounce_period': FunctionInfo(12, [], [], [], '', ['debounce'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'position': CallbackInfo(13, ['position'], [{}], 'h', None),
		'analog_value': CallbackInfo(14, ['value'], [{}], 'H', None),
		'position_reached': CallbackInfo(15, ['position'], [{}], 'h', None),
		'analog_value_reached': CallbackInfo(16, ['value'], [{}], 'H', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 1; re[3] = 2; re[4] = 1; re[5] = 2; re[6] = 1; re[7] = 2; re[8] = 1; re[9] = 2; re[10] = 1; re[11] = 2; re[12] = 1; re[255] = 1

class RotaryPotiV2Bricklet(MQTTCallbackDevice):
	functions = {
		'get_position': FunctionInfo(1, [], [], [], '', ['position'], [{}], 'h'),
		'set_position_callback_configuration': FunctionInfo(2, ['period', 'value_has_to_change', 'option', 'min', 'max'], ['int', 'bool', 'char', 'int', 'int'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c h h', [], [], ''),
		'get_position_callback_configuration': FunctionInfo(3, [], [], [], '', ['period', 'value_has_to_change', 'option', 'min', 'max'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c h h'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'position': CallbackInfo(4, ['position'], [{}], 'h', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 2; re[3] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class RS232Bricklet(MQTTCallbackDevice):
	functions = {
		'write': FunctionInfo(1, ['message', 'length'], [('char', 60), 'int'], [{}, {}], '60c B', ['written'], [{}], 'B'),
		'read': FunctionInfo(2, [], [], [], '', ['message', 'length'], [{}, {}], '60c B'),
		'enable_read_callback': FunctionInfo(3, [], [], [], '', [], [], ''),
		'disable_read_callback': FunctionInfo(4, [], [], [], '', [], [], ''),
		'is_read_callback_enabled': FunctionInfo(5, [], [], [], '', ['enabled'], [{}], '!'),
		'set_configuration': FunctionInfo(6, ['baudrate', 'parity', 'stopbits', 'wordlength', 'hardware_flowcontrol', 'software_flowcontrol'], ['int', 'int', 'int', 'int', 'int', 'int'], [{0: '300', 1: '600', 2: '1200', 3: '2400', 4: '4800', 5: '9600', 6: '14400', 7: '19200', 8: '28800', 9: '38400', 10: '57600', 11: '115200', 12: '230400'}, {0: 'none', 1: 'odd', 2: 'even', 3: 'forced_parity_1', 4: 'forced_parity_0'}, {1: '1', 2: '2'}, {5: '5', 6: '6', 7: '7', 8: '8'}, {0: 'off', 1: 'on'}, {0: 'off', 1: 'on'}], 'B B B B B B', [], [], ''),
		'get_configuration': FunctionInfo(7, [], [], [], '', ['baudrate', 'parity', 'stopbits', 'wordlength', 'hardware_flowcontrol', 'software_flowcontrol'], [{0: '300', 1: '600', 2: '1200', 3: '2400', 4: '4800', 5: '9600', 6: '14400', 7: '19200', 8: '28800', 9: '38400', 10: '57600', 11: '115200', 12: '230400'}, {0: 'none', 1: 'odd', 2: 'even', 3: 'forced_parity_1', 4: 'forced_parity_0'}, {1: '1', 2: '2'}, {5: '5', 6: '6', 7: '7', 8: '8'}, {0: 'off', 1: 'on'}, {0: 'off', 1: 'on'}], 'B B B B B B'),
		'set_break_condition': FunctionInfo(10, ['break_time'], ['int'], [{}], 'H', [], [], ''),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'read': CallbackInfo(8, ['message', 'length'], [{}, {}], '60c B', None),
		'error': CallbackInfo(9, ['error'], [{1: 'overrun', 2: 'parity', 4: 'framing'}], 'B', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 1; re[3] = 2; re[4] = 2; re[5] = 1; re[6] = 3; re[7] = 1; re[10] = 3; re[255] = 1

class RS232V2Bricklet(MQTTCallbackDevice):
	functions = {
		'write_low_level': FunctionInfo(1, ['message_length', 'message_chunk_offset', 'message_chunk_data'], ['int', 'int', ('char', 60)], [{}, {}, {}], 'H H 60c', ['message_chunk_written'], [{}], 'B'),
		'write': HighLevelFunctionInfo(1, 'in', ['stream_data'], ['stream_written'], ['stream_length', 'stream_chunk_offset', 'stream_chunk_data'], ['stream_chunk_written'], ['message'], [('char', -65535)], [{}], 'H H 60c', ['message-written'], [{}], 'B','0', 60, None,True, False, None),
		'read_low_level': FunctionInfo(2, ['length'], ['int'], [{}], 'H', ['message_length', 'message_chunk_offset', 'message_chunk_data'], [{}, {}, {}], 'H H 60c'),
		'read': HighLevelFunctionInfo(2, 'out', [None], ['stream_data'], [None], ['stream_length', 'stream_chunk_offset', 'stream_chunk_data'], ['length'], ['int'], [{}], 'H', ['message'], [{}], 'H H 60c',None, 60, None,False, False, None),
		'enable_read_callback': FunctionInfo(3, [], [], [], '', [], [], ''),
		'disable_read_callback': FunctionInfo(4, [], [], [], '', [], [], ''),
		'is_read_callback_enabled': FunctionInfo(5, [], [], [], '', ['enabled'], [{}], '!'),
		'set_configuration': FunctionInfo(6, ['baudrate', 'parity', 'stopbits', 'wordlength', 'flowcontrol'], ['int', 'int', 'int', 'int', 'int'], [{}, {0: 'none', 1: 'odd', 2: 'even'}, {1: '1', 2: '2'}, {5: '5', 6: '6', 7: '7', 8: '8'}, {0: 'off', 1: 'software', 2: 'hardware'}], 'I B B B B', [], [], ''),
		'get_configuration': FunctionInfo(7, [], [], [], '', ['baudrate', 'parity', 'stopbits', 'wordlength', 'flowcontrol'], [{}, {0: 'none', 1: 'odd', 2: 'even'}, {1: '1', 2: '2'}, {5: '5', 6: '6', 7: '7', 8: '8'}, {0: 'off', 1: 'software', 2: 'hardware'}], 'I B B B B'),
		'set_buffer_config': FunctionInfo(8, ['send_buffer_size', 'receive_buffer_size'], ['int', 'int'], [{}, {}], 'H H', [], [], ''),
		'get_buffer_config': FunctionInfo(9, [], [], [], '', ['send_buffer_size', 'receive_buffer_size'], [{}, {}], 'H H'),
		'get_buffer_status': FunctionInfo(10, [], [], [], '', ['send_buffer_used', 'receive_buffer_used'], [{}, {}], 'H H'),
		'get_error_count': FunctionInfo(11, [], [], [], '', ['error_count_overrun', 'error_count_parity'], [{}, {}], 'I I'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'read': CallbackInfo(12, ['message'], [{}], 'H H 60c', [('stream_length', 'stream_chunk_offset', 'stream_chunk_data'), {'fixed_length': None, 'single_chunk': False}, None]),
		'error_count': CallbackInfo(13, ['error_count_overrun', 'error_count_parity'], [{}, {}], 'I I', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 1; re[3] = 2; re[4] = 2; re[5] = 1; re[6] = 3; re[7] = 1; re[8] = 3; re[9] = 1; re[10] = 1; re[11] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class RS485Bricklet(MQTTCallbackDevice):
	functions = {
		'write_low_level': FunctionInfo(1, ['message_length', 'message_chunk_offset', 'message_chunk_data'], ['int', 'int', ('char', 60)], [{}, {}, {}], 'H H 60c', ['message_chunk_written'], [{}], 'B'),
		'write': HighLevelFunctionInfo(1, 'in', ['stream_data'], ['stream_written'], ['stream_length', 'stream_chunk_offset', 'stream_chunk_data'], ['stream_chunk_written'], ['message'], [('char', -65535)], [{}], 'H H 60c', ['message-written'], [{}], 'B','0', 60, None,True, False, None),
		'read_low_level': FunctionInfo(2, ['length'], ['int'], [{}], 'H', ['message_length', 'message_chunk_offset', 'message_chunk_data'], [{}, {}, {}], 'H H 60c'),
		'read': HighLevelFunctionInfo(2, 'out', [None], ['stream_data'], [None], ['stream_length', 'stream_chunk_offset', 'stream_chunk_data'], ['length'], ['int'], [{}], 'H', ['message'], [{}], 'H H 60c',None, 60, None,False, False, None),
		'enable_read_callback': FunctionInfo(3, [], [], [], '', [], [], ''),
		'disable_read_callback': FunctionInfo(4, [], [], [], '', [], [], ''),
		'is_read_callback_enabled': FunctionInfo(5, [], [], [], '', ['enabled'], [{}], '!'),
		'set_rs485_configuration': FunctionInfo(6, ['baudrate', 'parity', 'stopbits', 'wordlength', 'duplex'], ['int', 'int', 'int', 'int', 'int'], [{}, {0: 'none', 1: 'odd', 2: 'even'}, {1: '1', 2: '2'}, {5: '5', 6: '6', 7: '7', 8: '8'}, {0: 'half', 1: 'full'}], 'I B B B B', [], [], ''),
		'get_rs485_configuration': FunctionInfo(7, [], [], [], '', ['baudrate', 'parity', 'stopbits', 'wordlength', 'duplex'], [{}, {0: 'none', 1: 'odd', 2: 'even'}, {1: '1', 2: '2'}, {5: '5', 6: '6', 7: '7', 8: '8'}, {0: 'half', 1: 'full'}], 'I B B B B'),
		'set_modbus_configuration': FunctionInfo(8, ['slave_address', 'master_request_timeout'], ['int', 'int'], [{}, {}], 'B I', [], [], ''),
		'get_modbus_configuration': FunctionInfo(9, [], [], [], '', ['slave_address', 'master_request_timeout'], [{}, {}], 'B I'),
		'set_mode': FunctionInfo(10, ['mode'], ['int'], [{0: 'rs485', 1: 'modbus_master_rtu', 2: 'modbus_slave_rtu'}], 'B', [], [], ''),
		'get_mode': FunctionInfo(11, [], [], [], '', ['mode'], [{0: 'rs485', 1: 'modbus_master_rtu', 2: 'modbus_slave_rtu'}], 'B'),
		'set_communication_led_config': FunctionInfo(12, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_communication'}], 'B', [], [], ''),
		'get_communication_led_config': FunctionInfo(13, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_communication'}], 'B'),
		'set_error_led_config': FunctionInfo(14, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_error'}], 'B', [], [], ''),
		'get_error_led_config': FunctionInfo(15, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_error'}], 'B'),
		'set_buffer_config': FunctionInfo(16, ['send_buffer_size', 'receive_buffer_size'], ['int', 'int'], [{}, {}], 'H H', [], [], ''),
		'get_buffer_config': FunctionInfo(17, [], [], [], '', ['send_buffer_size', 'receive_buffer_size'], [{}, {}], 'H H'),
		'get_buffer_status': FunctionInfo(18, [], [], [], '', ['send_buffer_used', 'receive_buffer_used'], [{}, {}], 'H H'),
		'enable_error_count_callback': FunctionInfo(19, [], [], [], '', [], [], ''),
		'disable_error_count_callback': FunctionInfo(20, [], [], [], '', [], [], ''),
		'is_error_count_callback_enabled': FunctionInfo(21, [], [], [], '', ['enabled'], [{}], '!'),
		'get_error_count': FunctionInfo(22, [], [], [], '', ['overrun_error_count', 'parity_error_count'], [{}, {}], 'I I'),
		'get_modbus_common_error_count': FunctionInfo(23, [], [], [], '', ['timeout_error_count', 'checksum_error_count', 'frame_too_big_error_count', 'illegal_function_error_count', 'illegal_data_address_error_count', 'illegal_data_value_error_count', 'slave_device_failure_error_count'], [{}, {}, {}, {}, {}, {}, {}], 'I I I I I I I'),
		'modbus_slave_report_exception': FunctionInfo(24, ['request_id', 'exception_code'], ['int', 'int'], [{}, {-1: 'timeout', 0: 'success', 1: 'illegal_function', 2: 'illegal_data_address', 3: 'illegal_data_value', 4: 'slave_device_failure', 5: 'acknowledge', 6: 'slave_device_busy', 8: 'memory_parity_error', 10: 'gateway_path_unavailable', 11: 'gateway_target_device_failed_to_respond'}], 'B b', [], [], ''),
		'modbus_slave_answer_read_coils_request_low_level': FunctionInfo(25, ['request_id', 'coils_length', 'coils_chunk_offset', 'coils_chunk_data'], ['int', 'int', 'int', ('bool', 472)], [{}, {}, {}, {}], 'B H H 472!', [], [], ''),
		'modbus_slave_answer_read_coils_request': HighLevelFunctionInfo(25, 'in', [None, 'stream_data'], [], [None, 'stream_length', 'stream_chunk_offset', 'stream_chunk_data'], [], ['request_id', 'coils'], ['int', ('bool', -65535)], [{}, {}], 'B H H 472!', [], [], '','0', 472, None,False, False, None),
		'modbus_master_read_coils': FunctionInfo(26, ['slave_address', 'starting_address', 'count'], ['int', 'int', 'int'], [{}, {}, {}], 'B I H', ['request_id'], [{}], 'B'),
		'modbus_slave_answer_read_holding_registers_request_low_level': FunctionInfo(27, ['request_id', 'holding_registers_length', 'holding_registers_chunk_offset', 'holding_registers_chunk_data'], ['int', 'int', 'int', ('int', 29)], [{}, {}, {}, {}], 'B H H 29H', [], [], ''),
		'modbus_slave_answer_read_holding_registers_request': HighLevelFunctionInfo(27, 'in', [None, 'stream_data'], [], [None, 'stream_length', 'stream_chunk_offset', 'stream_chunk_data'], [], ['request_id', 'holding_registers'], ['int', ('int', -65535)], [{}, {}], 'B H H 29H', [], [], '','0', 29, None,False, False, None),
		'modbus_master_read_holding_registers': FunctionInfo(28, ['slave_address', 'starting_address', 'count'], ['int', 'int', 'int'], [{}, {}, {}], 'B I H', ['request_id'], [{}], 'B'),
		'modbus_slave_answer_write_single_coil_request': FunctionInfo(29, ['request_id'], ['int'], [{}], 'B', [], [], ''),
		'modbus_master_write_single_coil': FunctionInfo(30, ['slave_address', 'coil_address', 'coil_value'], ['int', 'int', 'bool'], [{}, {}, {}], 'B I !', ['request_id'], [{}], 'B'),
		'modbus_slave_answer_write_single_register_request': FunctionInfo(31, ['request_id'], ['int'], [{}], 'B', [], [], ''),
		'modbus_master_write_single_register': FunctionInfo(32, ['slave_address', 'register_address', 'register_value'], ['int', 'int', 'int'], [{}, {}, {}], 'B I H', ['request_id'], [{}], 'B'),
		'modbus_slave_answer_write_multiple_coils_request': FunctionInfo(33, ['request_id'], ['int'], [{}], 'B', [], [], ''),
		'modbus_master_write_multiple_coils_low_level': FunctionInfo(34, ['slave_address', 'starting_address', 'coils_length', 'coils_chunk_offset', 'coils_chunk_data'], ['int', 'int', 'int', 'int', ('bool', 440)], [{}, {}, {}, {}, {}], 'B I H H 440!', ['request_id'], [{}], 'B'),
		'modbus_master_write_multiple_coils': HighLevelFunctionInfo(34, 'in', [None, None, 'stream_data'], [None], [None, None, 'stream_length', 'stream_chunk_offset', 'stream_chunk_data'], [None], ['slave_address', 'starting_address', 'coils'], ['int', 'int', ('bool', -65535)], [{}, {}, {}], 'B I H H 440!', ['request-id'], [{}], 'B','0', 440, None,False, False, None),
		'modbus_slave_answer_write_multiple_registers_request': FunctionInfo(35, ['request_id'], ['int'], [{}], 'B', [], [], ''),
		'modbus_master_write_multiple_registers_low_level': FunctionInfo(36, ['slave_address', 'starting_address', 'registers_length', 'registers_chunk_offset', 'registers_chunk_data'], ['int', 'int', 'int', 'int', ('int', 27)], [{}, {}, {}, {}, {}], 'B I H H 27H', ['request_id'], [{}], 'B'),
		'modbus_master_write_multiple_registers': HighLevelFunctionInfo(36, 'in', [None, None, 'stream_data'], [None], [None, None, 'stream_length', 'stream_chunk_offset', 'stream_chunk_data'], [None], ['slave_address', 'starting_address', 'registers'], ['int', 'int', ('int', -65535)], [{}, {}, {}], 'B I H H 27H', ['request-id'], [{}], 'B','0', 27, None,False, False, None),
		'modbus_slave_answer_read_discrete_inputs_request_low_level': FunctionInfo(37, ['request_id', 'discrete_inputs_length', 'discrete_inputs_chunk_offset', 'discrete_inputs_chunk_data'], ['int', 'int', 'int', ('bool', 472)], [{}, {}, {}, {}], 'B H H 472!', [], [], ''),
		'modbus_slave_answer_read_discrete_inputs_request': HighLevelFunctionInfo(37, 'in', [None, 'stream_data'], [], [None, 'stream_length', 'stream_chunk_offset', 'stream_chunk_data'], [], ['request_id', 'discrete_inputs'], ['int', ('bool', -65535)], [{}, {}], 'B H H 472!', [], [], '','0', 472, None,False, False, None),
		'modbus_master_read_discrete_inputs': FunctionInfo(38, ['slave_address', 'starting_address', 'count'], ['int', 'int', 'int'], [{}, {}, {}], 'B I H', ['request_id'], [{}], 'B'),
		'modbus_slave_answer_read_input_registers_request_low_level': FunctionInfo(39, ['request_id', 'input_registers_length', 'input_registers_chunk_offset', 'input_registers_chunk_data'], ['int', 'int', 'int', ('int', 29)], [{}, {}, {}, {}], 'B H H 29H', [], [], ''),
		'modbus_slave_answer_read_input_registers_request': HighLevelFunctionInfo(39, 'in', [None, 'stream_data'], [], [None, 'stream_length', 'stream_chunk_offset', 'stream_chunk_data'], [], ['request_id', 'input_registers'], ['int', ('int', -65535)], [{}, {}], 'B H H 29H', [], [], '','0', 29, None,False, False, None),
		'modbus_master_read_input_registers': FunctionInfo(40, ['slave_address', 'starting_address', 'count'], ['int', 'int', 'int'], [{}, {}, {}], 'B I H', ['request_id'], [{}], 'B'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'read': CallbackInfo(41, ['message'], [{}], 'H H 60c', [('stream_length', 'stream_chunk_offset', 'stream_chunk_data'), {'fixed_length': None, 'single_chunk': False}, None]),
		'error_count': CallbackInfo(42, ['overrun_error_count', 'parity_error_count'], [{}, {}], 'I I', None),
		'modbus_slave_read_coils_request': CallbackInfo(43, ['request_id', 'starting_address', 'count'], [{}, {}, {}], 'B I H', None),
		'modbus_master_read_coils_response': CallbackInfo(44, ['request_id', 'exception_code', 'coils'], [{}, {-1: 'timeout', 0: 'success', 1: 'illegal_function', 2: 'illegal_data_address', 3: 'illegal_data_value', 4: 'slave_device_failure', 5: 'acknowledge', 6: 'slave_device_busy', 8: 'memory_parity_error', 10: 'gateway_path_unavailable', 11: 'gateway_target_device_failed_to_respond'}, {}], 'B b H H 464!', [(None, None, 'stream_length', 'stream_chunk_offset', 'stream_chunk_data'), {'fixed_length': None, 'single_chunk': False}, None]),
		'modbus_slave_read_holding_registers_request': CallbackInfo(45, ['request_id', 'starting_address', 'count'], [{}, {}, {}], 'B I H', None),
		'modbus_master_read_holding_registers_response': CallbackInfo(46, ['request_id', 'exception_code', 'holding_registers'], [{}, {-1: 'timeout', 0: 'success', 1: 'illegal_function', 2: 'illegal_data_address', 3: 'illegal_data_value', 4: 'slave_device_failure', 5: 'acknowledge', 6: 'slave_device_busy', 8: 'memory_parity_error', 10: 'gateway_path_unavailable', 11: 'gateway_target_device_failed_to_respond'}, {}], 'B b H H 29H', [(None, None, 'stream_length', 'stream_chunk_offset', 'stream_chunk_data'), {'fixed_length': None, 'single_chunk': False}, None]),
		'modbus_slave_write_single_coil_request': CallbackInfo(47, ['request_id', 'coil_address', 'coil_value'], [{}, {}, {}], 'B I !', None),
		'modbus_master_write_single_coil_response': CallbackInfo(48, ['request_id', 'exception_code'], [{}, {-1: 'timeout', 0: 'success', 1: 'illegal_function', 2: 'illegal_data_address', 3: 'illegal_data_value', 4: 'slave_device_failure', 5: 'acknowledge', 6: 'slave_device_busy', 8: 'memory_parity_error', 10: 'gateway_path_unavailable', 11: 'gateway_target_device_failed_to_respond'}], 'B b', None),
		'modbus_slave_write_single_register_request': CallbackInfo(49, ['request_id', 'register_address', 'register_value'], [{}, {}, {}], 'B I H', None),
		'modbus_master_write_single_register_response': CallbackInfo(50, ['request_id', 'exception_code'], [{}, {-1: 'timeout', 0: 'success', 1: 'illegal_function', 2: 'illegal_data_address', 3: 'illegal_data_value', 4: 'slave_device_failure', 5: 'acknowledge', 6: 'slave_device_busy', 8: 'memory_parity_error', 10: 'gateway_path_unavailable', 11: 'gateway_target_device_failed_to_respond'}], 'B b', None),
		'modbus_slave_write_multiple_coils_request': CallbackInfo(51, ['request_id', 'starting_address', 'coils'], [{}, {}, {}], 'B I H H 440!', [(None, None, 'stream_length', 'stream_chunk_offset', 'stream_chunk_data'), {'fixed_length': None, 'single_chunk': False}, None]),
		'modbus_master_write_multiple_coils_response': CallbackInfo(52, ['request_id', 'exception_code'], [{}, {-1: 'timeout', 0: 'success', 1: 'illegal_function', 2: 'illegal_data_address', 3: 'illegal_data_value', 4: 'slave_device_failure', 5: 'acknowledge', 6: 'slave_device_busy', 8: 'memory_parity_error', 10: 'gateway_path_unavailable', 11: 'gateway_target_device_failed_to_respond'}], 'B b', None),
		'modbus_slave_write_multiple_registers_request': CallbackInfo(53, ['request_id', 'starting_address', 'registers'], [{}, {}, {}], 'B I H H 27H', [(None, None, 'stream_length', 'stream_chunk_offset', 'stream_chunk_data'), {'fixed_length': None, 'single_chunk': False}, None]),
		'modbus_master_write_multiple_registers_response': CallbackInfo(54, ['request_id', 'exception_code'], [{}, {-1: 'timeout', 0: 'success', 1: 'illegal_function', 2: 'illegal_data_address', 3: 'illegal_data_value', 4: 'slave_device_failure', 5: 'acknowledge', 6: 'slave_device_busy', 8: 'memory_parity_error', 10: 'gateway_path_unavailable', 11: 'gateway_target_device_failed_to_respond'}], 'B b', None),
		'modbus_slave_read_discrete_inputs_request': CallbackInfo(55, ['request_id', 'starting_address', 'count'], [{}, {}, {}], 'B I H', None),
		'modbus_master_read_discrete_inputs_response': CallbackInfo(56, ['request_id', 'exception_code', 'discrete_inputs'], [{}, {-1: 'timeout', 0: 'success', 1: 'illegal_function', 2: 'illegal_data_address', 3: 'illegal_data_value', 4: 'slave_device_failure', 5: 'acknowledge', 6: 'slave_device_busy', 8: 'memory_parity_error', 10: 'gateway_path_unavailable', 11: 'gateway_target_device_failed_to_respond'}, {}], 'B b H H 464!', [(None, None, 'stream_length', 'stream_chunk_offset', 'stream_chunk_data'), {'fixed_length': None, 'single_chunk': False}, None]),
		'modbus_slave_read_input_registers_request': CallbackInfo(57, ['request_id', 'starting_address', 'count'], [{}, {}, {}], 'B I H', None),
		'modbus_master_read_input_registers_response': CallbackInfo(58, ['request_id', 'exception_code', 'input_registers'], [{}, {-1: 'timeout', 0: 'success', 1: 'illegal_function', 2: 'illegal_data_address', 3: 'illegal_data_value', 4: 'slave_device_failure', 5: 'acknowledge', 6: 'slave_device_busy', 8: 'memory_parity_error', 10: 'gateway_path_unavailable', 11: 'gateway_target_device_failed_to_respond'}, {}], 'B b H H 29H', [(None, None, 'stream_length', 'stream_chunk_offset', 'stream_chunk_data'), {'fixed_length': None, 'single_chunk': False}, None])
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 1; re[3] = 2; re[4] = 2; re[5] = 1; re[6] = 3; re[7] = 1; re[8] = 3; re[9] = 1; re[10] = 3; re[11] = 1; re[12] = 3; re[13] = 1; re[14] = 3; re[15] = 1; re[16] = 3; re[17] = 1; re[18] = 1; re[19] = 2; re[20] = 2; re[21] = 1; re[22] = 1; re[23] = 1; re[24] = 3; re[25] = 2; re[26] = 1; re[27] = 2; re[28] = 1; re[29] = 3; re[30] = 1; re[31] = 3; re[32] = 1; re[33] = 3; re[34] = 1; re[35] = 3; re[36] = 1; re[37] = 2; re[38] = 1; re[39] = 2; re[40] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class SegmentDisplay4x7Bricklet(MQTTCallbackDevice):
	functions = {
		'set_segments': FunctionInfo(1, ['segments', 'brightness', 'colon'], [('int', 4), 'int', 'bool'], [{}, {}, {}], '4B B !', [], [], ''),
		'get_segments': FunctionInfo(2, [], [], [], '', ['segments', 'brightness', 'colon'], [{}, {}, {}], '4B B !'),
		'start_counter': FunctionInfo(3, ['value_from', 'value_to', 'increment', 'length'], ['int', 'int', 'int', 'int'], [{}, {}, {}, {}], 'h h h I', [], [], ''),
		'get_counter_value': FunctionInfo(4, [], [], [], '', ['value'], [{}], 'H'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'counter_finished': CallbackInfo(5, [], [], '', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 3; re[2] = 1; re[3] = 3; re[4] = 1; re[255] = 1

class SegmentDisplay4x7V2Bricklet(MQTTCallbackDevice):
	functions = {
		'set_segments': FunctionInfo(1, ['digit0', 'digit1', 'digit2', 'digit3', 'colon', 'tick'], [('bool', 8), ('bool', 8), ('bool', 8), ('bool', 8), ('bool', 2), 'bool'], [{}, {}, {}, {}, {}, {}], '8! 8! 8! 8! 2! !', [], [], ''),
		'get_segments': FunctionInfo(2, [], [], [], '', ['digit0', 'digit1', 'digit2', 'digit3', 'colon', 'tick'], [{}, {}, {}, {}, {}, {}], '8! 8! 8! 8! 2! !'),
		'set_brightness': FunctionInfo(3, ['brightness'], ['int'], [{}], 'B', [], [], ''),
		'get_brightness': FunctionInfo(4, [], [], [], '', ['brightness'], [{}], 'B'),
		'set_numeric_value': FunctionInfo(5, ['value'], [('int', 4)], [{}], '4b', [], [], ''),
		'set_selected_segment': FunctionInfo(6, ['segment', 'value'], ['int', 'bool'], [{}, {}], 'B !', [], [], ''),
		'get_selected_segment': FunctionInfo(7, ['segment'], ['int'], [{}], 'B', ['value'], [{}], '!'),
		'start_counter': FunctionInfo(8, ['value_from', 'value_to', 'increment', 'length'], ['int', 'int', 'int', 'int'], [{}, {}, {}, {}], 'h h h I', [], [], ''),
		'get_counter_value': FunctionInfo(9, [], [], [], '', ['value'], [{}], 'H'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'counter_finished': CallbackInfo(10, [], [], '', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 3; re[2] = 1; re[3] = 3; re[4] = 1; re[5] = 3; re[6] = 3; re[7] = 1; re[8] = 3; re[9] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class ServoBrick(MQTTCallbackDevice):
	functions = {
		'enable': FunctionInfo(1, ['servo_num'], ['int'], [{}], 'B', [], [], ''),
		'disable': FunctionInfo(2, ['servo_num'], ['int'], [{}], 'B', [], [], ''),
		'is_enabled': FunctionInfo(3, ['servo_num'], ['int'], [{}], 'B', ['enabled'], [{}], '!'),
		'set_position': FunctionInfo(4, ['servo_num', 'position'], ['int', 'int'], [{}, {}], 'B h', [], [], ''),
		'get_position': FunctionInfo(5, ['servo_num'], ['int'], [{}], 'B', ['position'], [{}], 'h'),
		'get_current_position': FunctionInfo(6, ['servo_num'], ['int'], [{}], 'B', ['position'], [{}], 'h'),
		'set_velocity': FunctionInfo(7, ['servo_num', 'velocity'], ['int', 'int'], [{}, {}], 'B H', [], [], ''),
		'get_velocity': FunctionInfo(8, ['servo_num'], ['int'], [{}], 'B', ['velocity'], [{}], 'H'),
		'get_current_velocity': FunctionInfo(9, ['servo_num'], ['int'], [{}], 'B', ['velocity'], [{}], 'H'),
		'set_acceleration': FunctionInfo(10, ['servo_num', 'acceleration'], ['int', 'int'], [{}, {}], 'B H', [], [], ''),
		'get_acceleration': FunctionInfo(11, ['servo_num'], ['int'], [{}], 'B', ['acceleration'], [{}], 'H'),
		'set_output_voltage': FunctionInfo(12, ['voltage'], ['int'], [{}], 'H', [], [], ''),
		'get_output_voltage': FunctionInfo(13, [], [], [], '', ['voltage'], [{}], 'H'),
		'set_pulse_width': FunctionInfo(14, ['servo_num', 'min', 'max'], ['int', 'int', 'int'], [{}, {}, {}], 'B H H', [], [], ''),
		'get_pulse_width': FunctionInfo(15, ['servo_num'], ['int'], [{}], 'B', ['min', 'max'], [{}, {}], 'H H'),
		'set_degree': FunctionInfo(16, ['servo_num', 'min', 'max'], ['int', 'int', 'int'], [{}, {}, {}], 'B h h', [], [], ''),
		'get_degree': FunctionInfo(17, ['servo_num'], ['int'], [{}], 'B', ['min', 'max'], [{}, {}], 'h h'),
		'set_period': FunctionInfo(18, ['servo_num', 'period'], ['int', 'int'], [{}, {}], 'B H', [], [], ''),
		'get_period': FunctionInfo(19, ['servo_num'], ['int'], [{}], 'B', ['period'], [{}], 'H'),
		'get_servo_current': FunctionInfo(20, ['servo_num'], ['int'], [{}], 'B', ['current'], [{}], 'H'),
		'get_overall_current': FunctionInfo(21, [], [], [], '', ['current'], [{}], 'H'),
		'get_stack_input_voltage': FunctionInfo(22, [], [], [], '', ['voltage'], [{}], 'H'),
		'get_external_input_voltage': FunctionInfo(23, [], [], [], '', ['voltage'], [{}], 'H'),
		'set_minimum_voltage': FunctionInfo(24, ['voltage'], ['int'], [{}], 'H', [], [], ''),
		'get_minimum_voltage': FunctionInfo(25, [], [], [], '', ['voltage'], [{}], 'H'),
		'enable_position_reached_callback': FunctionInfo(29, [], [], [], '', [], [], ''),
		'disable_position_reached_callback': FunctionInfo(30, [], [], [], '', [], [], ''),
		'is_position_reached_callback_enabled': FunctionInfo(31, [], [], [], '', ['enabled'], [{}], '!'),
		'enable_velocity_reached_callback': FunctionInfo(32, [], [], [], '', [], [], ''),
		'disable_velocity_reached_callback': FunctionInfo(33, [], [], [], '', [], [], ''),
		'is_velocity_reached_callback_enabled': FunctionInfo(34, [], [], [], '', ['enabled'], [{}], '!'),
		'set_spitfp_baudrate_config': FunctionInfo(231, ['enable_dynamic_baudrate', 'minimum_dynamic_baudrate'], ['bool', 'int'], [{}, {}], '! I', [], [], ''),
		'get_spitfp_baudrate_config': FunctionInfo(232, [], [], [], '', ['enable_dynamic_baudrate', 'minimum_dynamic_baudrate'], [{}, {}], '! I'),
		'get_send_timeout_count': FunctionInfo(233, ['communication_method'], ['int'], [{0: 'none', 1: 'usb', 2: 'spi_stack', 3: 'chibi', 4: 'rs485', 5: 'wifi', 6: 'ethernet', 7: 'wifi_v2'}], 'B', ['timeout_count'], [{}], 'I'),
		'set_spitfp_baudrate': FunctionInfo(234, ['bricklet_port', 'baudrate'], ['char', 'int'], [{}, {}], 'c I', [], [], ''),
		'get_spitfp_baudrate': FunctionInfo(235, ['bricklet_port'], ['char'], [{}], 'c', ['baudrate'], [{}], 'I'),
		'get_spitfp_error_count': FunctionInfo(237, ['bricklet_port'], ['char'], [{}], 'c', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'enable_status_led': FunctionInfo(238, [], [], [], '', [], [], ''),
		'disable_status_led': FunctionInfo(239, [], [], [], '', [], [], ''),
		'is_status_led_enabled': FunctionInfo(240, [], [], [], '', ['enabled'], [{}], '!'),
		'get_protocol1_bricklet_name': FunctionInfo(241, ['port'], ['char'], [{}], 'c', ['protocol_version', 'firmware_version', 'name'], [{}, {}, {}], 'B 3B 40s'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'under_voltage': CallbackInfo(26, ['voltage'], [{}], 'H', None),
		'position_reached': CallbackInfo(27, ['servo_num', 'position'], [{}, {}], 'B h', None),
		'velocity_reached': CallbackInfo(28, ['servo_num', 'velocity'], [{}, {}], 'B h', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 3; re[2] = 3; re[3] = 1; re[4] = 3; re[5] = 1; re[6] = 1; re[7] = 3; re[8] = 1; re[9] = 1; re[10] = 3; re[11] = 1; re[12] = 3; re[13] = 1; re[14] = 3; re[15] = 1; re[16] = 3; re[17] = 1; re[18] = 3; re[19] = 1; re[20] = 1; re[21] = 1; re[22] = 1; re[23] = 1; re[24] = 2; re[25] = 1; re[29] = 2; re[30] = 2; re[31] = 1; re[32] = 2; re[33] = 2; re[34] = 1; re[231] = 3; re[232] = 1; re[233] = 1; re[234] = 3; re[235] = 1; re[237] = 1; re[238] = 3; re[239] = 3; re[240] = 1; re[241] = 1; re[242] = 1; re[243] = 3; re[255] = 1

class SilentStepperBrick(MQTTCallbackDevice):
	functions = {
		'set_max_velocity': FunctionInfo(1, ['velocity'], ['int'], [{}], 'H', [], [], ''),
		'get_max_velocity': FunctionInfo(2, [], [], [], '', ['velocity'], [{}], 'H'),
		'get_current_velocity': FunctionInfo(3, [], [], [], '', ['velocity'], [{}], 'H'),
		'set_speed_ramping': FunctionInfo(4, ['acceleration', 'deacceleration'], ['int', 'int'], [{}, {}], 'H H', [], [], ''),
		'get_speed_ramping': FunctionInfo(5, [], [], [], '', ['acceleration', 'deacceleration'], [{}, {}], 'H H'),
		'full_brake': FunctionInfo(6, [], [], [], '', [], [], ''),
		'set_current_position': FunctionInfo(7, ['position'], ['int'], [{}], 'i', [], [], ''),
		'get_current_position': FunctionInfo(8, [], [], [], '', ['position'], [{}], 'i'),
		'set_target_position': FunctionInfo(9, ['position'], ['int'], [{}], 'i', [], [], ''),
		'get_target_position': FunctionInfo(10, [], [], [], '', ['position'], [{}], 'i'),
		'set_steps': FunctionInfo(11, ['steps'], ['int'], [{}], 'i', [], [], ''),
		'get_steps': FunctionInfo(12, [], [], [], '', ['steps'], [{}], 'i'),
		'get_remaining_steps': FunctionInfo(13, [], [], [], '', ['steps'], [{}], 'i'),
		'set_step_configuration': FunctionInfo(14, ['step_resolution', 'interpolation'], ['int', 'bool'], [{8: '1', 7: '2', 6: '4', 5: '8', 4: '16', 3: '32', 2: '64', 1: '128', 0: '256'}, {}], 'B !', [], [], ''),
		'get_step_configuration': FunctionInfo(15, [], [], [], '', ['step_resolution', 'interpolation'], [{8: '1', 7: '2', 6: '4', 5: '8', 4: '16', 3: '32', 2: '64', 1: '128', 0: '256'}, {}], 'B !'),
		'drive_forward': FunctionInfo(16, [], [], [], '', [], [], ''),
		'drive_backward': FunctionInfo(17, [], [], [], '', [], [], ''),
		'stop': FunctionInfo(18, [], [], [], '', [], [], ''),
		'get_stack_input_voltage': FunctionInfo(19, [], [], [], '', ['voltage'], [{}], 'H'),
		'get_external_input_voltage': FunctionInfo(20, [], [], [], '', ['voltage'], [{}], 'H'),
		'set_motor_current': FunctionInfo(22, ['current'], ['int'], [{}], 'H', [], [], ''),
		'get_motor_current': FunctionInfo(23, [], [], [], '', ['current'], [{}], 'H'),
		'enable': FunctionInfo(24, [], [], [], '', [], [], ''),
		'disable': FunctionInfo(25, [], [], [], '', [], [], ''),
		'is_enabled': FunctionInfo(26, [], [], [], '', ['enabled'], [{}], '!'),
		'set_basic_configuration': FunctionInfo(27, ['standstill_current', 'motor_run_current', 'standstill_delay_time', 'power_down_time', 'stealth_threshold', 'coolstep_threshold', 'classic_threshold', 'high_velocity_chopper_mode'], ['int', 'int', 'int', 'int', 'int', 'int', 'int', 'bool'], [{}, {}, {}, {}, {}, {}, {}, {}], 'H H H H H H H !', [], [], ''),
		'get_basic_configuration': FunctionInfo(28, [], [], [], '', ['standstill_current', 'motor_run_current', 'standstill_delay_time', 'power_down_time', 'stealth_threshold', 'coolstep_threshold', 'classic_threshold', 'high_velocity_chopper_mode'], [{}, {}, {}, {}, {}, {}, {}, {}], 'H H H H H H H !'),
		'set_spreadcycle_configuration': FunctionInfo(29, ['slow_decay_duration', 'enable_random_slow_decay', 'fast_decay_duration', 'hysteresis_start_value', 'hysteresis_end_value', 'sine_wave_offset', 'chopper_mode', 'comparator_blank_time', 'fast_decay_without_comparator'], ['int', 'bool', 'int', 'int', 'int', 'int', 'int', 'int', 'bool'], [{}, {}, {}, {}, {}, {}, {0: 'spread_cycle', 1: 'fast_decay'}, {}, {}], 'B ! B B b b B B !', [], [], ''),
		'get_spreadcycle_configuration': FunctionInfo(30, [], [], [], '', ['slow_decay_duration', 'enable_random_slow_decay', 'fast_decay_duration', 'hysteresis_start_value', 'hysteresis_end_value', 'sine_wave_offset', 'chopper_mode', 'comparator_blank_time', 'fast_decay_without_comparator'], [{}, {}, {}, {}, {}, {}, {0: 'spread_cycle', 1: 'fast_decay'}, {}, {}], 'B ! B B b b B B !'),
		'set_stealth_configuration': FunctionInfo(31, ['enable_stealth', 'amplitude', 'gradient', 'enable_autoscale', 'force_symmetric', 'freewheel_mode'], ['bool', 'int', 'int', 'bool', 'bool', 'int'], [{}, {}, {}, {}, {}, {0: 'normal', 1: 'freewheeling', 2: 'coil_short_ls', 3: 'coil_short_hs'}], '! B B ! ! B', [], [], ''),
		'get_stealth_configuration': FunctionInfo(32, [], [], [], '', ['enable_stealth', 'amplitude', 'gradient', 'enable_autoscale', 'force_symmetric', 'freewheel_mode'], [{}, {}, {}, {}, {}, {0: 'normal', 1: 'freewheeling', 2: 'coil_short_ls', 3: 'coil_short_hs'}], '! B B ! ! B'),
		'set_coolstep_configuration': FunctionInfo(33, ['minimum_stallguard_value', 'maximum_stallguard_value', 'current_up_step_width', 'current_down_step_width', 'minimum_current', 'stallguard_threshold_value', 'stallguard_mode'], ['int', 'int', 'int', 'int', 'int', 'int', 'int'], [{}, {}, {0: '1', 1: '2', 2: '4', 3: '8'}, {0: '1', 1: '2', 2: '8', 3: '32'}, {0: 'half', 1: 'quarter'}, {}, {0: 'standard', 1: 'filtered'}], 'B B B B B b B', [], [], ''),
		'get_coolstep_configuration': FunctionInfo(34, [], [], [], '', ['minimum_stallguard_value', 'maximum_stallguard_value', 'current_up_step_width', 'current_down_step_width', 'minimum_current', 'stallguard_threshold_value', 'stallguard_mode'], [{}, {}, {0: '1', 1: '2', 2: '4', 3: '8'}, {0: '1', 1: '2', 2: '8', 3: '32'}, {0: 'half', 1: 'quarter'}, {}, {0: 'standard', 1: 'filtered'}], 'B B B B B b B'),
		'set_misc_configuration': FunctionInfo(35, ['disable_short_to_ground_protection', 'synchronize_phase_frequency'], ['bool', 'int'], [{}, {}], '! B', [], [], ''),
		'get_misc_configuration': FunctionInfo(36, [], [], [], '', ['disable_short_to_ground_protection', 'synchronize_phase_frequency'], [{}, {}], '! B'),
		'get_driver_status': FunctionInfo(37, [], [], [], '', ['open_load', 'short_to_ground', 'over_temperature', 'motor_stalled', 'actual_motor_current', 'full_step_active', 'stallguard_result', 'stealth_voltage_amplitude'], [{0: 'none', 1: 'phase_a', 2: 'phase_b', 3: 'phase_ab'}, {0: 'none', 1: 'phase_a', 2: 'phase_b', 3: 'phase_ab'}, {0: 'none', 1: 'warning', 2: 'limit'}, {}, {}, {}, {}, {}], 'B B B ! B ! B B'),
		'set_minimum_voltage': FunctionInfo(38, ['voltage'], ['int'], [{}], 'H', [], [], ''),
		'get_minimum_voltage': FunctionInfo(39, [], [], [], '', ['voltage'], [{}], 'H'),
		'set_time_base': FunctionInfo(42, ['time_base'], ['int'], [{}], 'I', [], [], ''),
		'get_time_base': FunctionInfo(43, [], [], [], '', ['time_base'], [{}], 'I'),
		'get_all_data': FunctionInfo(44, [], [], [], '', ['current_velocity', 'current_position', 'remaining_steps', 'stack_voltage', 'external_voltage', 'current_consumption'], [{}, {}, {}, {}, {}, {}], 'H i i H H H'),
		'set_all_data_period': FunctionInfo(45, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_all_data_period': FunctionInfo(46, [], [], [], '', ['period'], [{}], 'I'),
		'set_spitfp_baudrate_config': FunctionInfo(231, ['enable_dynamic_baudrate', 'minimum_dynamic_baudrate'], ['bool', 'int'], [{}, {}], '! I', [], [], ''),
		'get_spitfp_baudrate_config': FunctionInfo(232, [], [], [], '', ['enable_dynamic_baudrate', 'minimum_dynamic_baudrate'], [{}, {}], '! I'),
		'get_send_timeout_count': FunctionInfo(233, ['communication_method'], ['int'], [{0: 'none', 1: 'usb', 2: 'spi_stack', 3: 'chibi', 4: 'rs485', 5: 'wifi', 6: 'ethernet', 7: 'wifi_v2'}], 'B', ['timeout_count'], [{}], 'I'),
		'set_spitfp_baudrate': FunctionInfo(234, ['bricklet_port', 'baudrate'], ['char', 'int'], [{}, {}], 'c I', [], [], ''),
		'get_spitfp_baudrate': FunctionInfo(235, ['bricklet_port'], ['char'], [{}], 'c', ['baudrate'], [{}], 'I'),
		'get_spitfp_error_count': FunctionInfo(237, ['bricklet_port'], ['char'], [{}], 'c', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'enable_status_led': FunctionInfo(238, [], [], [], '', [], [], ''),
		'disable_status_led': FunctionInfo(239, [], [], [], '', [], [], ''),
		'is_status_led_enabled': FunctionInfo(240, [], [], [], '', ['enabled'], [{}], '!'),
		'get_protocol1_bricklet_name': FunctionInfo(241, ['port'], ['char'], [{}], 'c', ['protocol_version', 'firmware_version', 'name'], [{}, {}, {}], 'B 3B 40s'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'under_voltage': CallbackInfo(40, ['voltage'], [{}], 'H', None),
		'position_reached': CallbackInfo(41, ['position'], [{}], 'i', None),
		'all_data': CallbackInfo(47, ['current_velocity', 'current_position', 'remaining_steps', 'stack_voltage', 'external_voltage', 'current_consumption'], [{}, {}, {}, {}, {}, {}], 'H i i H H H', None),
		'new_state': CallbackInfo(48, ['state_new', 'state_previous'], [{1: 'stop', 2: 'acceleration', 3: 'run', 4: 'deacceleration', 5: 'direction_change_to_forward', 6: 'direction_change_to_backward'}, {1: 'stop', 2: 'acceleration', 3: 'run', 4: 'deacceleration', 5: 'direction_change_to_forward', 6: 'direction_change_to_backward'}], 'B B', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 3; re[2] = 1; re[3] = 1; re[4] = 3; re[5] = 1; re[6] = 3; re[7] = 3; re[8] = 1; re[9] = 3; re[10] = 1; re[11] = 3; re[12] = 1; re[13] = 1; re[14] = 3; re[15] = 1; re[16] = 3; re[17] = 3; re[18] = 3; re[19] = 1; re[20] = 1; re[22] = 3; re[23] = 1; re[24] = 3; re[25] = 3; re[26] = 1; re[27] = 3; re[28] = 1; re[29] = 3; re[30] = 1; re[31] = 3; re[32] = 1; re[33] = 3; re[34] = 1; re[35] = 3; re[36] = 1; re[37] = 1; re[38] = 2; re[39] = 1; re[42] = 3; re[43] = 1; re[44] = 1; re[45] = 2; re[46] = 1; re[231] = 3; re[232] = 1; re[233] = 1; re[234] = 3; re[235] = 1; re[237] = 1; re[238] = 3; re[239] = 3; re[240] = 1; re[241] = 1; re[242] = 1; re[243] = 3; re[255] = 1

class SolidStateRelayBricklet(MQTTCallbackDevice):
	functions = {
		'set_state': FunctionInfo(1, ['state'], ['bool'], [{}], '!', [], [], ''),
		'get_state': FunctionInfo(2, [], [], [], '', ['state'], [{}], '!'),
		'set_monoflop': FunctionInfo(3, ['state', 'time'], ['bool', 'int'], [{}, {}], '! I', [], [], ''),
		'get_monoflop': FunctionInfo(4, [], [], [], '', ['state', 'time', 'time_remaining'], [{}, {}, {}], '! I I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'monoflop_done': CallbackInfo(5, ['state'], [{}], '!', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 3; re[2] = 1; re[3] = 3; re[4] = 1; re[255] = 1

class SolidStateRelayV2Bricklet(MQTTCallbackDevice):
	functions = {
		'set_state': FunctionInfo(1, ['state'], ['bool'], [{}], '!', [], [], ''),
		'get_state': FunctionInfo(2, [], [], [], '', ['state'], [{}], '!'),
		'set_monoflop': FunctionInfo(3, ['state', 'time'], ['bool', 'int'], [{}, {}], '! I', [], [], ''),
		'get_monoflop': FunctionInfo(4, [], [], [], '', ['state', 'time', 'time_remaining'], [{}, {}, {}], '! I I'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'monoflop_done': CallbackInfo(5, ['state'], [{}], '!', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 3; re[2] = 1; re[3] = 3; re[4] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class SoundIntensityBricklet(MQTTCallbackDevice):
	functions = {
		'get_intensity': FunctionInfo(1, [], [], [], '', ['intensity'], [{}], 'H'),
		'set_intensity_callback_period': FunctionInfo(2, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_intensity_callback_period': FunctionInfo(3, [], [], [], '', ['period'], [{}], 'I'),
		'set_intensity_callback_threshold': FunctionInfo(4, ['option', 'min', 'max'], ['char', 'int', 'int'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c H H', [], [], ''),
		'get_intensity_callback_threshold': FunctionInfo(5, [], [], [], '', ['option', 'min', 'max'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c H H'),
		'set_debounce_period': FunctionInfo(6, ['debounce'], ['int'], [{}], 'I', [], [], ''),
		'get_debounce_period': FunctionInfo(7, [], [], [], '', ['debounce'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'intensity': CallbackInfo(8, ['intensity'], [{}], 'H', None),
		'intensity_reached': CallbackInfo(9, ['intensity'], [{}], 'H', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 2; re[3] = 1; re[4] = 2; re[5] = 1; re[6] = 2; re[7] = 1; re[255] = 1

class SoundPressureLevelBricklet(MQTTCallbackDevice):
	functions = {
		'get_decibel': FunctionInfo(1, [], [], [], '', ['decibel'], [{}], 'H'),
		'set_decibel_callback_configuration': FunctionInfo(2, ['period', 'value_has_to_change', 'option', 'min', 'max'], ['int', 'bool', 'char', 'int', 'int'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c H H', [], [], ''),
		'get_decibel_callback_configuration': FunctionInfo(3, [], [], [], '', ['period', 'value_has_to_change', 'option', 'min', 'max'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c H H'),
		'get_spectrum_low_level': FunctionInfo(5, [], [], [], '', ['spectrum_length', 'spectrum_chunk_offset', 'spectrum_chunk_data'], [{}, {}, {}], 'H H 30H'),
		'get_spectrum': HighLevelFunctionInfo(5, 'out', [], ['stream_data'], [], ['stream_length', 'stream_chunk_offset', 'stream_chunk_data'], [], [], [], '', ['spectrum'], [{}], 'H H 30H',None, 30, None,False, False, None),
		'set_spectrum_callback_configuration': FunctionInfo(6, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_spectrum_callback_configuration': FunctionInfo(7, [], [], [], '', ['period'], [{}], 'I'),
		'set_configuration': FunctionInfo(9, ['fft_size', 'weighting'], ['int', 'int'], [{0: '128', 1: '256', 2: '512', 3: '1024'}, {0: 'a', 1: 'b', 2: 'c', 3: 'd', 4: 'z', 5: 'itu_r_468'}], 'B B', [], [], ''),
		'get_configuration': FunctionInfo(10, [], [], [], '', ['fft_size', 'weighting'], [{0: '128', 1: '256', 2: '512', 3: '1024'}, {0: 'a', 1: 'b', 2: 'c', 3: 'd', 4: 'z', 5: 'itu_r_468'}], 'B B'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'decibel': CallbackInfo(4, ['decibel'], [{}], 'H', None),
		'spectrum': CallbackInfo(8, ['spectrum'], [{}], 'H H 30H', [('stream_length', 'stream_chunk_offset', 'stream_chunk_data'), {'fixed_length': None, 'single_chunk': False}, None])
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 2; re[3] = 1; re[5] = 1; re[6] = 2; re[7] = 1; re[9] = 3; re[10] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class StepperBrick(MQTTCallbackDevice):
	functions = {
		'set_max_velocity': FunctionInfo(1, ['velocity'], ['int'], [{}], 'H', [], [], ''),
		'get_max_velocity': FunctionInfo(2, [], [], [], '', ['velocity'], [{}], 'H'),
		'get_current_velocity': FunctionInfo(3, [], [], [], '', ['velocity'], [{}], 'H'),
		'set_speed_ramping': FunctionInfo(4, ['acceleration', 'deacceleration'], ['int', 'int'], [{}, {}], 'H H', [], [], ''),
		'get_speed_ramping': FunctionInfo(5, [], [], [], '', ['acceleration', 'deacceleration'], [{}, {}], 'H H'),
		'full_brake': FunctionInfo(6, [], [], [], '', [], [], ''),
		'set_current_position': FunctionInfo(7, ['position'], ['int'], [{}], 'i', [], [], ''),
		'get_current_position': FunctionInfo(8, [], [], [], '', ['position'], [{}], 'i'),
		'set_target_position': FunctionInfo(9, ['position'], ['int'], [{}], 'i', [], [], ''),
		'get_target_position': FunctionInfo(10, [], [], [], '', ['position'], [{}], 'i'),
		'set_steps': FunctionInfo(11, ['steps'], ['int'], [{}], 'i', [], [], ''),
		'get_steps': FunctionInfo(12, [], [], [], '', ['steps'], [{}], 'i'),
		'get_remaining_steps': FunctionInfo(13, [], [], [], '', ['steps'], [{}], 'i'),
		'set_step_mode': FunctionInfo(14, ['mode'], ['int'], [{1: 'full_step', 2: 'half_step', 4: 'quarter_step', 8: 'eighth_step'}], 'B', [], [], ''),
		'get_step_mode': FunctionInfo(15, [], [], [], '', ['mode'], [{1: 'full_step', 2: 'half_step', 4: 'quarter_step', 8: 'eighth_step'}], 'B'),
		'drive_forward': FunctionInfo(16, [], [], [], '', [], [], ''),
		'drive_backward': FunctionInfo(17, [], [], [], '', [], [], ''),
		'stop': FunctionInfo(18, [], [], [], '', [], [], ''),
		'get_stack_input_voltage': FunctionInfo(19, [], [], [], '', ['voltage'], [{}], 'H'),
		'get_external_input_voltage': FunctionInfo(20, [], [], [], '', ['voltage'], [{}], 'H'),
		'get_current_consumption': FunctionInfo(21, [], [], [], '', ['current'], [{}], 'H'),
		'set_motor_current': FunctionInfo(22, ['current'], ['int'], [{}], 'H', [], [], ''),
		'get_motor_current': FunctionInfo(23, [], [], [], '', ['current'], [{}], 'H'),
		'enable': FunctionInfo(24, [], [], [], '', [], [], ''),
		'disable': FunctionInfo(25, [], [], [], '', [], [], ''),
		'is_enabled': FunctionInfo(26, [], [], [], '', ['enabled'], [{}], '!'),
		'set_decay': FunctionInfo(27, ['decay'], ['int'], [{}], 'H', [], [], ''),
		'get_decay': FunctionInfo(28, [], [], [], '', ['decay'], [{}], 'H'),
		'set_minimum_voltage': FunctionInfo(29, ['voltage'], ['int'], [{}], 'H', [], [], ''),
		'get_minimum_voltage': FunctionInfo(30, [], [], [], '', ['voltage'], [{}], 'H'),
		'set_sync_rect': FunctionInfo(33, ['sync_rect'], ['bool'], [{}], '!', [], [], ''),
		'is_sync_rect': FunctionInfo(34, [], [], [], '', ['sync_rect'], [{}], '!'),
		'set_time_base': FunctionInfo(35, ['time_base'], ['int'], [{}], 'I', [], [], ''),
		'get_time_base': FunctionInfo(36, [], [], [], '', ['time_base'], [{}], 'I'),
		'get_all_data': FunctionInfo(37, [], [], [], '', ['current_velocity', 'current_position', 'remaining_steps', 'stack_voltage', 'external_voltage', 'current_consumption'], [{}, {}, {}, {}, {}, {}], 'H i i H H H'),
		'set_all_data_period': FunctionInfo(38, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_all_data_period': FunctionInfo(39, [], [], [], '', ['period'], [{}], 'I'),
		'set_spitfp_baudrate_config': FunctionInfo(231, ['enable_dynamic_baudrate', 'minimum_dynamic_baudrate'], ['bool', 'int'], [{}, {}], '! I', [], [], ''),
		'get_spitfp_baudrate_config': FunctionInfo(232, [], [], [], '', ['enable_dynamic_baudrate', 'minimum_dynamic_baudrate'], [{}, {}], '! I'),
		'get_send_timeout_count': FunctionInfo(233, ['communication_method'], ['int'], [{0: 'none', 1: 'usb', 2: 'spi_stack', 3: 'chibi', 4: 'rs485', 5: 'wifi', 6: 'ethernet', 7: 'wifi_v2'}], 'B', ['timeout_count'], [{}], 'I'),
		'set_spitfp_baudrate': FunctionInfo(234, ['bricklet_port', 'baudrate'], ['char', 'int'], [{}, {}], 'c I', [], [], ''),
		'get_spitfp_baudrate': FunctionInfo(235, ['bricklet_port'], ['char'], [{}], 'c', ['baudrate'], [{}], 'I'),
		'get_spitfp_error_count': FunctionInfo(237, ['bricklet_port'], ['char'], [{}], 'c', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'enable_status_led': FunctionInfo(238, [], [], [], '', [], [], ''),
		'disable_status_led': FunctionInfo(239, [], [], [], '', [], [], ''),
		'is_status_led_enabled': FunctionInfo(240, [], [], [], '', ['enabled'], [{}], '!'),
		'get_protocol1_bricklet_name': FunctionInfo(241, ['port'], ['char'], [{}], 'c', ['protocol_version', 'firmware_version', 'name'], [{}, {}, {}], 'B 3B 40s'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'under_voltage': CallbackInfo(31, ['voltage'], [{}], 'H', None),
		'position_reached': CallbackInfo(32, ['position'], [{}], 'i', None),
		'all_data': CallbackInfo(40, ['current_velocity', 'current_position', 'remaining_steps', 'stack_voltage', 'external_voltage', 'current_consumption'], [{}, {}, {}, {}, {}, {}], 'H i i H H H', None),
		'new_state': CallbackInfo(41, ['state_new', 'state_previous'], [{1: 'stop', 2: 'acceleration', 3: 'run', 4: 'deacceleration', 5: 'direction_change_to_forward', 6: 'direction_change_to_backward'}, {1: 'stop', 2: 'acceleration', 3: 'run', 4: 'deacceleration', 5: 'direction_change_to_forward', 6: 'direction_change_to_backward'}], 'B B', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 3; re[2] = 1; re[3] = 1; re[4] = 3; re[5] = 1; re[6] = 3; re[7] = 3; re[8] = 1; re[9] = 3; re[10] = 1; re[11] = 3; re[12] = 1; re[13] = 1; re[14] = 3; re[15] = 1; re[16] = 3; re[17] = 3; re[18] = 3; re[19] = 1; re[20] = 1; re[21] = 1; re[22] = 3; re[23] = 1; re[24] = 3; re[25] = 3; re[26] = 1; re[27] = 3; re[28] = 1; re[29] = 2; re[30] = 1; re[33] = 3; re[34] = 1; re[35] = 3; re[36] = 1; re[37] = 1; re[38] = 2; re[39] = 1; re[231] = 3; re[232] = 1; re[233] = 1; re[234] = 3; re[235] = 1; re[237] = 1; re[238] = 3; re[239] = 3; re[240] = 1; re[241] = 1; re[242] = 1; re[243] = 3; re[255] = 1

class TemperatureBricklet(MQTTCallbackDevice):
	functions = {
		'get_temperature': FunctionInfo(1, [], [], [], '', ['temperature'], [{}], 'h'),
		'set_temperature_callback_period': FunctionInfo(2, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_temperature_callback_period': FunctionInfo(3, [], [], [], '', ['period'], [{}], 'I'),
		'set_temperature_callback_threshold': FunctionInfo(4, ['option', 'min', 'max'], ['char', 'int', 'int'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c h h', [], [], ''),
		'get_temperature_callback_threshold': FunctionInfo(5, [], [], [], '', ['option', 'min', 'max'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c h h'),
		'set_debounce_period': FunctionInfo(6, ['debounce'], ['int'], [{}], 'I', [], [], ''),
		'get_debounce_period': FunctionInfo(7, [], [], [], '', ['debounce'], [{}], 'I'),
		'set_i2c_mode': FunctionInfo(10, ['mode'], ['int'], [{0: 'fast', 1: 'slow'}], 'B', [], [], ''),
		'get_i2c_mode': FunctionInfo(11, [], [], [], '', ['mode'], [{0: 'fast', 1: 'slow'}], 'B'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'temperature': CallbackInfo(8, ['temperature'], [{}], 'h', None),
		'temperature_reached': CallbackInfo(9, ['temperature'], [{}], 'h', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 2; re[3] = 1; re[4] = 2; re[5] = 1; re[6] = 2; re[7] = 1; re[10] = 3; re[11] = 1; re[255] = 1

class TemperatureIRBricklet(MQTTCallbackDevice):
	functions = {
		'get_ambient_temperature': FunctionInfo(1, [], [], [], '', ['temperature'], [{}], 'h'),
		'get_object_temperature': FunctionInfo(2, [], [], [], '', ['temperature'], [{}], 'h'),
		'set_emissivity': FunctionInfo(3, ['emissivity'], ['int'], [{}], 'H', [], [], ''),
		'get_emissivity': FunctionInfo(4, [], [], [], '', ['emissivity'], [{}], 'H'),
		'set_ambient_temperature_callback_period': FunctionInfo(5, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_ambient_temperature_callback_period': FunctionInfo(6, [], [], [], '', ['period'], [{}], 'I'),
		'set_object_temperature_callback_period': FunctionInfo(7, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_object_temperature_callback_period': FunctionInfo(8, [], [], [], '', ['period'], [{}], 'I'),
		'set_ambient_temperature_callback_threshold': FunctionInfo(9, ['option', 'min', 'max'], ['char', 'int', 'int'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c h h', [], [], ''),
		'get_ambient_temperature_callback_threshold': FunctionInfo(10, [], [], [], '', ['option', 'min', 'max'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c h h'),
		'set_object_temperature_callback_threshold': FunctionInfo(11, ['option', 'min', 'max'], ['char', 'int', 'int'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c h h', [], [], ''),
		'get_object_temperature_callback_threshold': FunctionInfo(12, [], [], [], '', ['option', 'min', 'max'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c h h'),
		'set_debounce_period': FunctionInfo(13, ['debounce'], ['int'], [{}], 'I', [], [], ''),
		'get_debounce_period': FunctionInfo(14, [], [], [], '', ['debounce'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'ambient_temperature': CallbackInfo(15, ['temperature'], [{}], 'h', None),
		'object_temperature': CallbackInfo(16, ['temperature'], [{}], 'h', None),
		'ambient_temperature_reached': CallbackInfo(17, ['temperature'], [{}], 'h', None),
		'object_temperature_reached': CallbackInfo(18, ['temperature'], [{}], 'h', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 1; re[3] = 3; re[4] = 1; re[5] = 2; re[6] = 1; re[7] = 2; re[8] = 1; re[9] = 2; re[10] = 1; re[11] = 2; re[12] = 1; re[13] = 2; re[14] = 1; re[255] = 1

class TemperatureIRV2Bricklet(MQTTCallbackDevice):
	functions = {
		'get_ambient_temperature': FunctionInfo(1, [], [], [], '', ['temperature'], [{}], 'h'),
		'set_ambient_temperature_callback_configuration': FunctionInfo(2, ['period', 'value_has_to_change', 'option', 'min', 'max'], ['int', 'bool', 'char', 'int', 'int'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c h h', [], [], ''),
		'get_ambient_temperature_callback_configuration': FunctionInfo(3, [], [], [], '', ['period', 'value_has_to_change', 'option', 'min', 'max'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c h h'),
		'get_object_temperature': FunctionInfo(5, [], [], [], '', ['temperature'], [{}], 'h'),
		'set_object_temperature_callback_configuration': FunctionInfo(6, ['period', 'value_has_to_change', 'option', 'min', 'max'], ['int', 'bool', 'char', 'int', 'int'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c h h', [], [], ''),
		'get_object_temperature_callback_configuration': FunctionInfo(7, [], [], [], '', ['period', 'value_has_to_change', 'option', 'min', 'max'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c h h'),
		'set_emissivity': FunctionInfo(9, ['emissivity'], ['int'], [{}], 'H', [], [], ''),
		'get_emissivity': FunctionInfo(10, [], [], [], '', ['emissivity'], [{}], 'H'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'ambient_temperature': CallbackInfo(4, ['temperature'], [{}], 'h', None),
		'object_temperature': CallbackInfo(8, ['temperature'], [{}], 'h', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 2; re[3] = 1; re[5] = 1; re[6] = 2; re[7] = 1; re[9] = 3; re[10] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class TemperatureV2Bricklet(MQTTCallbackDevice):
	functions = {
		'get_temperature': FunctionInfo(1, [], [], [], '', ['temperature'], [{}], 'h'),
		'set_temperature_callback_configuration': FunctionInfo(2, ['period', 'value_has_to_change', 'option', 'min', 'max'], ['int', 'bool', 'char', 'int', 'int'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c h h', [], [], ''),
		'get_temperature_callback_configuration': FunctionInfo(3, [], [], [], '', ['period', 'value_has_to_change', 'option', 'min', 'max'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c h h'),
		'set_heater_configuration': FunctionInfo(5, ['heater_config'], ['int'], [{0: 'disabled', 1: 'enabled'}], 'B', [], [], ''),
		'get_heater_configuration': FunctionInfo(6, [], [], [], '', ['heater_config'], [{0: 'disabled', 1: 'enabled'}], 'B'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'temperature': CallbackInfo(4, ['temperature'], [{}], 'h', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 2; re[3] = 1; re[5] = 3; re[6] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class ThermalImagingBricklet(MQTTCallbackDevice):
	functions = {
		'get_high_contrast_image_low_level': FunctionInfo(1, [], [], [], '', ['image_chunk_offset', 'image_chunk_data'], [{}, {}], 'H 62B'),
		'get_high_contrast_image': HighLevelFunctionInfo(1, 'out', [], ['stream_data'], [], ['stream_chunk_offset', 'stream_chunk_data'], [], [], [], '', ['image'], [{}], 'H 62B',None, 62, 65535,False, False, 4800),
		'get_temperature_image_low_level': FunctionInfo(2, [], [], [], '', ['image_chunk_offset', 'image_chunk_data'], [{}, {}], 'H 31H'),
		'get_temperature_image': HighLevelFunctionInfo(2, 'out', [], ['stream_data'], [], ['stream_chunk_offset', 'stream_chunk_data'], [], [], [], '', ['image'], [{}], 'H 31H',None, 31, 65535,False, False, 4800),
		'get_statistics': FunctionInfo(3, [], [], [], '', ['spotmeter_statistics', 'temperatures', 'resolution', 'ffc_status', 'temperature_warning'], [{}, {}, {0: '0_to_6553_kelvin', 1: '0_to_655_kelvin'}, {0: 'never_commanded', 1: 'imminent', 2: 'in_progress', 3: 'complete'}, {}], '4H 4H B B 2!'),
		'set_resolution': FunctionInfo(4, ['resolution'], ['int'], [{0: '0_to_6553_kelvin', 1: '0_to_655_kelvin'}], 'B', [], [], ''),
		'get_resolution': FunctionInfo(5, [], [], [], '', ['resolution'], [{0: '0_to_6553_kelvin', 1: '0_to_655_kelvin'}], 'B'),
		'set_spotmeter_config': FunctionInfo(6, ['region_of_interest'], [('int', 4)], [{}], '4B', [], [], ''),
		'get_spotmeter_config': FunctionInfo(7, [], [], [], '', ['region_of_interest'], [{}], '4B'),
		'set_high_contrast_config': FunctionInfo(8, ['region_of_interest', 'dampening_factor', 'clip_limit', 'empty_counts'], [('int', 4), 'int', ('int', 2), 'int'], [{}, {}, {}, {}], '4B H 2H H', [], [], ''),
		'get_high_contrast_config': FunctionInfo(9, [], [], [], '', ['region_of_interest', 'dampening_factor', 'clip_limit', 'empty_counts'], [{}, {}, {}, {}], '4B H 2H H'),
		'set_image_transfer_config': FunctionInfo(10, ['config'], ['int'], [{0: 'manual_high_contrast_image', 1: 'manual_temperature_image', 2: 'callback_high_contrast_image', 3: 'callback_temperature_image'}], 'B', [], [], ''),
		'get_image_transfer_config': FunctionInfo(11, [], [], [], '', ['config'], [{0: 'manual_high_contrast_image', 1: 'manual_temperature_image', 2: 'callback_high_contrast_image', 3: 'callback_temperature_image'}], 'B'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'high_contrast_image': CallbackInfo(12, ['image'], [{}], 'H 62B', [('stream_chunk_offset', 'stream_chunk_data'), {'fixed_length': 4800, 'single_chunk': False}, None]),
		'temperature_image': CallbackInfo(13, ['image'], [{}], 'H 31H', [('stream_chunk_offset', 'stream_chunk_data'), {'fixed_length': 4800, 'single_chunk': False}, None])
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 1; re[3] = 1; re[4] = 3; re[5] = 1; re[6] = 3; re[7] = 1; re[8] = 3; re[9] = 1; re[10] = 2; re[11] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class ThermocoupleBricklet(MQTTCallbackDevice):
	functions = {
		'get_temperature': FunctionInfo(1, [], [], [], '', ['temperature'], [{}], 'i'),
		'set_temperature_callback_period': FunctionInfo(2, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_temperature_callback_period': FunctionInfo(3, [], [], [], '', ['period'], [{}], 'I'),
		'set_temperature_callback_threshold': FunctionInfo(4, ['option', 'min', 'max'], ['char', 'int', 'int'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c i i', [], [], ''),
		'get_temperature_callback_threshold': FunctionInfo(5, [], [], [], '', ['option', 'min', 'max'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c i i'),
		'set_debounce_period': FunctionInfo(6, ['debounce'], ['int'], [{}], 'I', [], [], ''),
		'get_debounce_period': FunctionInfo(7, [], [], [], '', ['debounce'], [{}], 'I'),
		'set_configuration': FunctionInfo(10, ['averaging', 'thermocouple_type', 'filter'], ['int', 'int', 'int'], [{1: '1', 2: '2', 4: '4', 8: '8', 16: '16'}, {0: 'b', 1: 'e', 2: 'j', 3: 'k', 4: 'n', 5: 'r', 6: 's', 7: 't', 8: 'g8', 9: 'g32'}, {0: '50hz', 1: '60hz'}], 'B B B', [], [], ''),
		'get_configuration': FunctionInfo(11, [], [], [], '', ['averaging', 'thermocouple_type', 'filter'], [{1: '1', 2: '2', 4: '4', 8: '8', 16: '16'}, {0: 'b', 1: 'e', 2: 'j', 3: 'k', 4: 'n', 5: 'r', 6: 's', 7: 't', 8: 'g8', 9: 'g32'}, {0: '50hz', 1: '60hz'}], 'B B B'),
		'get_error_state': FunctionInfo(12, [], [], [], '', ['over_under', 'open_circuit'], [{}, {}], '! !'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'temperature': CallbackInfo(8, ['temperature'], [{}], 'i', None),
		'temperature_reached': CallbackInfo(9, ['temperature'], [{}], 'i', None),
		'error_state': CallbackInfo(13, ['over_under', 'open_circuit'], [{}, {}], '! !', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 2; re[3] = 1; re[4] = 2; re[5] = 1; re[6] = 2; re[7] = 1; re[10] = 3; re[11] = 1; re[12] = 1; re[255] = 1

class ThermocoupleV2Bricklet(MQTTCallbackDevice):
	functions = {
		'get_temperature': FunctionInfo(1, [], [], [], '', ['temperature'], [{}], 'i'),
		'set_temperature_callback_configuration': FunctionInfo(2, ['period', 'value_has_to_change', 'option', 'min', 'max'], ['int', 'bool', 'char', 'int', 'int'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c i i', [], [], ''),
		'get_temperature_callback_configuration': FunctionInfo(3, [], [], [], '', ['period', 'value_has_to_change', 'option', 'min', 'max'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c i i'),
		'set_configuration': FunctionInfo(5, ['averaging', 'thermocouple_type', 'filter'], ['int', 'int', 'int'], [{1: '1', 2: '2', 4: '4', 8: '8', 16: '16'}, {0: 'b', 1: 'e', 2: 'j', 3: 'k', 4: 'n', 5: 'r', 6: 's', 7: 't', 8: 'g8', 9: 'g32'}, {0: '50hz', 1: '60hz'}], 'B B B', [], [], ''),
		'get_configuration': FunctionInfo(6, [], [], [], '', ['averaging', 'thermocouple_type', 'filter'], [{1: '1', 2: '2', 4: '4', 8: '8', 16: '16'}, {0: 'b', 1: 'e', 2: 'j', 3: 'k', 4: 'n', 5: 'r', 6: 's', 7: 't', 8: 'g8', 9: 'g32'}, {0: '50hz', 1: '60hz'}], 'B B B'),
		'get_error_state': FunctionInfo(7, [], [], [], '', ['over_under', 'open_circuit'], [{}, {}], '! !'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'temperature': CallbackInfo(4, ['temperature'], [{}], 'i', None),
		'error_state': CallbackInfo(8, ['over_under', 'open_circuit'], [{}, {}], '! !', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 2; re[3] = 1; re[5] = 3; re[6] = 1; re[7] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class TiltBricklet(MQTTCallbackDevice):
	functions = {
		'get_tilt_state': FunctionInfo(1, [], [], [], '', ['state'], [{0: 'closed', 1: 'open', 2: 'closed_vibrating'}], 'B'),
		'enable_tilt_state_callback': FunctionInfo(2, [], [], [], '', [], [], ''),
		'disable_tilt_state_callback': FunctionInfo(3, [], [], [], '', [], [], ''),
		'is_tilt_state_callback_enabled': FunctionInfo(4, [], [], [], '', ['enabled'], [{}], '!'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'tilt_state': CallbackInfo(5, ['state'], [{0: 'closed', 1: 'open', 2: 'closed_vibrating'}], 'B', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 2; re[3] = 2; re[4] = 1; re[255] = 1

class UVLightBricklet(MQTTCallbackDevice):
	functions = {
		'get_uv_light': FunctionInfo(1, [], [], [], '', ['uv_light'], [{}], 'I'),
		'set_uv_light_callback_period': FunctionInfo(2, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_uv_light_callback_period': FunctionInfo(3, [], [], [], '', ['period'], [{}], 'I'),
		'set_uv_light_callback_threshold': FunctionInfo(4, ['option', 'min', 'max'], ['char', 'int', 'int'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c I I', [], [], ''),
		'get_uv_light_callback_threshold': FunctionInfo(5, [], [], [], '', ['option', 'min', 'max'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c I I'),
		'set_debounce_period': FunctionInfo(6, ['debounce'], ['int'], [{}], 'I', [], [], ''),
		'get_debounce_period': FunctionInfo(7, [], [], [], '', ['debounce'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'uv_light': CallbackInfo(8, ['uv_light'], [{}], 'I', None),
		'uv_light_reached': CallbackInfo(9, ['uv_light'], [{}], 'I', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 2; re[3] = 1; re[4] = 2; re[5] = 1; re[6] = 2; re[7] = 1; re[255] = 1

class UVLightV2Bricklet(MQTTCallbackDevice):
	functions = {
		'get_uva': FunctionInfo(1, [], [], [], '', ['uva'], [{}], 'i'),
		'set_uva_callback_configuration': FunctionInfo(2, ['period', 'value_has_to_change', 'option', 'min', 'max'], ['int', 'bool', 'char', 'int', 'int'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c i i', [], [], ''),
		'get_uva_callback_configuration': FunctionInfo(3, [], [], [], '', ['period', 'value_has_to_change', 'option', 'min', 'max'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c i i'),
		'get_uvb': FunctionInfo(5, [], [], [], '', ['uvb'], [{}], 'i'),
		'set_uvb_callback_configuration': FunctionInfo(6, ['period', 'value_has_to_change', 'option', 'min', 'max'], ['int', 'bool', 'char', 'int', 'int'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c i i', [], [], ''),
		'get_uvb_callback_configuration': FunctionInfo(7, [], [], [], '', ['period', 'value_has_to_change', 'option', 'min', 'max'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c i i'),
		'get_uvi': FunctionInfo(9, [], [], [], '', ['uvi'], [{}], 'i'),
		'set_uvi_callback_configuration': FunctionInfo(10, ['period', 'value_has_to_change', 'option', 'min', 'max'], ['int', 'bool', 'char', 'int', 'int'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c i i', [], [], ''),
		'get_uvi_callback_configuration': FunctionInfo(11, [], [], [], '', ['period', 'value_has_to_change', 'option', 'min', 'max'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c i i'),
		'set_configuration': FunctionInfo(13, ['integration_time'], ['int'], [{0: '50ms', 1: '100ms', 2: '200ms', 3: '400ms', 4: '800ms'}], 'B', [], [], ''),
		'get_configuration': FunctionInfo(14, [], [], [], '', ['integration_time'], [{0: '50ms', 1: '100ms', 2: '200ms', 3: '400ms', 4: '800ms'}], 'B'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'uva': CallbackInfo(4, ['uva'], [{}], 'i', None),
		'uvb': CallbackInfo(8, ['uvb'], [{}], 'i', None),
		'uvi': CallbackInfo(12, ['uvi'], [{}], 'i', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 2; re[3] = 1; re[5] = 1; re[6] = 2; re[7] = 1; re[9] = 1; re[10] = 2; re[11] = 1; re[13] = 3; re[14] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class VoltageBricklet(MQTTCallbackDevice):
	functions = {
		'get_voltage': FunctionInfo(1, [], [], [], '', ['voltage'], [{}], 'H'),
		'get_analog_value': FunctionInfo(2, [], [], [], '', ['value'], [{}], 'H'),
		'set_voltage_callback_period': FunctionInfo(3, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_voltage_callback_period': FunctionInfo(4, [], [], [], '', ['period'], [{}], 'I'),
		'set_analog_value_callback_period': FunctionInfo(5, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_analog_value_callback_period': FunctionInfo(6, [], [], [], '', ['period'], [{}], 'I'),
		'set_voltage_callback_threshold': FunctionInfo(7, ['option', 'min', 'max'], ['char', 'int', 'int'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c H H', [], [], ''),
		'get_voltage_callback_threshold': FunctionInfo(8, [], [], [], '', ['option', 'min', 'max'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c H H'),
		'set_analog_value_callback_threshold': FunctionInfo(9, ['option', 'min', 'max'], ['char', 'int', 'int'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c H H', [], [], ''),
		'get_analog_value_callback_threshold': FunctionInfo(10, [], [], [], '', ['option', 'min', 'max'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c H H'),
		'set_debounce_period': FunctionInfo(11, ['debounce'], ['int'], [{}], 'I', [], [], ''),
		'get_debounce_period': FunctionInfo(12, [], [], [], '', ['debounce'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'voltage': CallbackInfo(13, ['voltage'], [{}], 'H', None),
		'analog_value': CallbackInfo(14, ['value'], [{}], 'H', None),
		'voltage_reached': CallbackInfo(15, ['voltage'], [{}], 'H', None),
		'analog_value_reached': CallbackInfo(16, ['value'], [{}], 'H', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 1; re[3] = 2; re[4] = 1; re[5] = 2; re[6] = 1; re[7] = 2; re[8] = 1; re[9] = 2; re[10] = 1; re[11] = 2; re[12] = 1; re[255] = 1

class VoltageCurrentBricklet(MQTTCallbackDevice):
	functions = {
		'get_current': FunctionInfo(1, [], [], [], '', ['current'], [{}], 'i'),
		'get_voltage': FunctionInfo(2, [], [], [], '', ['voltage'], [{}], 'i'),
		'get_power': FunctionInfo(3, [], [], [], '', ['power'], [{}], 'i'),
		'set_configuration': FunctionInfo(4, ['averaging', 'voltage_conversion_time', 'current_conversion_time'], ['int', 'int', 'int'], [{0: '1', 1: '4', 2: '16', 3: '64', 4: '128', 5: '256', 6: '512', 7: '1024'}, {}, {}], 'B B B', [], [], ''),
		'get_configuration': FunctionInfo(5, [], [], [], '', ['averaging', 'voltage_conversion_time', 'current_conversion_time'], [{0: '1', 1: '4', 2: '16', 3: '64', 4: '128', 5: '256', 6: '512', 7: '1024'}, {}, {}], 'B B B'),
		'set_calibration': FunctionInfo(6, ['gain_multiplier', 'gain_divisor'], ['int', 'int'], [{}, {}], 'H H', [], [], ''),
		'get_calibration': FunctionInfo(7, [], [], [], '', ['gain_multiplier', 'gain_divisor'], [{}, {}], 'H H'),
		'set_current_callback_period': FunctionInfo(8, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_current_callback_period': FunctionInfo(9, [], [], [], '', ['period'], [{}], 'I'),
		'set_voltage_callback_period': FunctionInfo(10, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_voltage_callback_period': FunctionInfo(11, [], [], [], '', ['period'], [{}], 'I'),
		'set_power_callback_period': FunctionInfo(12, ['period'], ['int'], [{}], 'I', [], [], ''),
		'get_power_callback_period': FunctionInfo(13, [], [], [], '', ['period'], [{}], 'I'),
		'set_current_callback_threshold': FunctionInfo(14, ['option', 'min', 'max'], ['char', 'int', 'int'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c i i', [], [], ''),
		'get_current_callback_threshold': FunctionInfo(15, [], [], [], '', ['option', 'min', 'max'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c i i'),
		'set_voltage_callback_threshold': FunctionInfo(16, ['option', 'min', 'max'], ['char', 'int', 'int'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c i i', [], [], ''),
		'get_voltage_callback_threshold': FunctionInfo(17, [], [], [], '', ['option', 'min', 'max'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c i i'),
		'set_power_callback_threshold': FunctionInfo(18, ['option', 'min', 'max'], ['char', 'int', 'int'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c i i', [], [], ''),
		'get_power_callback_threshold': FunctionInfo(19, [], [], [], '', ['option', 'min', 'max'], [{'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'c i i'),
		'set_debounce_period': FunctionInfo(20, ['debounce'], ['int'], [{}], 'I', [], [], ''),
		'get_debounce_period': FunctionInfo(21, [], [], [], '', ['debounce'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'current': CallbackInfo(22, ['current'], [{}], 'i', None),
		'voltage': CallbackInfo(23, ['voltage'], [{}], 'i', None),
		'power': CallbackInfo(24, ['power'], [{}], 'i', None),
		'current_reached': CallbackInfo(25, ['current'], [{}], 'i', None),
		'voltage_reached': CallbackInfo(26, ['voltage'], [{}], 'i', None),
		'power_reached': CallbackInfo(27, ['power'], [{}], 'i', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 1; re[3] = 1; re[4] = 3; re[5] = 1; re[6] = 3; re[7] = 1; re[8] = 2; re[9] = 1; re[10] = 2; re[11] = 1; re[12] = 2; re[13] = 1; re[14] = 2; re[15] = 1; re[16] = 2; re[17] = 1; re[18] = 2; re[19] = 1; re[20] = 2; re[21] = 1; re[255] = 1

class VoltageCurrentV2Bricklet(MQTTCallbackDevice):
	functions = {
		'get_current': FunctionInfo(1, [], [], [], '', ['current'], [{}], 'i'),
		'set_current_callback_configuration': FunctionInfo(2, ['period', 'value_has_to_change', 'option', 'min', 'max'], ['int', 'bool', 'char', 'int', 'int'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c i i', [], [], ''),
		'get_current_callback_configuration': FunctionInfo(3, [], [], [], '', ['period', 'value_has_to_change', 'option', 'min', 'max'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c i i'),
		'get_voltage': FunctionInfo(5, [], [], [], '', ['voltage'], [{}], 'i'),
		'set_voltage_callback_configuration': FunctionInfo(6, ['period', 'value_has_to_change', 'option', 'min', 'max'], ['int', 'bool', 'char', 'int', 'int'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c i i', [], [], ''),
		'get_voltage_callback_configuration': FunctionInfo(7, [], [], [], '', ['period', 'value_has_to_change', 'option', 'min', 'max'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c i i'),
		'get_power': FunctionInfo(9, [], [], [], '', ['power'], [{}], 'i'),
		'set_power_callback_configuration': FunctionInfo(10, ['period', 'value_has_to_change', 'option', 'min', 'max'], ['int', 'bool', 'char', 'int', 'int'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c i i', [], [], ''),
		'get_power_callback_configuration': FunctionInfo(11, [], [], [], '', ['period', 'value_has_to_change', 'option', 'min', 'max'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c i i'),
		'set_configuration': FunctionInfo(13, ['averaging', 'voltage_conversion_time', 'current_conversion_time'], ['int', 'int', 'int'], [{0: '1', 1: '4', 2: '16', 3: '64', 4: '128', 5: '256', 6: '512', 7: '1024'}, {0: '140us', 1: '204us', 2: '332us', 3: '588us', 4: '1_1ms', 5: '2_116ms', 6: '4_156ms', 7: '8_244ms'}, {0: '140us', 1: '204us', 2: '332us', 3: '588us', 4: '1_1ms', 5: '2_116ms', 6: '4_156ms', 7: '8_244ms'}], 'B B B', [], [], ''),
		'get_configuration': FunctionInfo(14, [], [], [], '', ['averaging', 'voltage_conversion_time', 'current_conversion_time'], [{0: '1', 1: '4', 2: '16', 3: '64', 4: '128', 5: '256', 6: '512', 7: '1024'}, {}, {}], 'B B B'),
		'set_calibration': FunctionInfo(15, ['voltage_multiplier', 'voltage_divisor', 'current_multiplier', 'current_divisor'], ['int', 'int', 'int', 'int'], [{}, {}, {}, {}], 'H H H H', [], [], ''),
		'get_calibration': FunctionInfo(16, [], [], [], '', ['voltage_multiplier', 'voltage_divisor', 'current_multiplier', 'current_divisor'], [{}, {}, {}, {}], 'H H H H'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'current': CallbackInfo(4, ['current'], [{}], 'i', None),
		'voltage': CallbackInfo(8, ['voltage'], [{}], 'i', None),
		'power': CallbackInfo(12, ['power'], [{}], 'i', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 1; re[2] = 2; re[3] = 1; re[5] = 1; re[6] = 2; re[7] = 1; re[9] = 1; re[10] = 2; re[11] = 1; re[13] = 3; re[14] = 1; re[15] = 3; re[16] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1

class XMC1400BreakoutBricklet(MQTTCallbackDevice):
	functions = {
		'set_gpio_config': FunctionInfo(1, ['port', 'pin', 'mode', 'input_hysteresis', 'output_level'], ['int', 'int', 'int', 'int', 'bool'], [{}, {}, {0: 'input_tristate', 1: 'input_pull_down', 2: 'input_pull_up', 3: 'input_sampling', 4: 'input_inverted_tristate', 5: 'input_inverted_pull_down', 6: 'input_inverted_pull_up', 7: 'input_inverted_sampling', 8: 'output_push_pull', 9: 'output_open_drain'}, {0: 'standard', 4: 'large'}, {}], 'B B B B !', [], [], ''),
		'get_gpio_input': FunctionInfo(2, ['port', 'pin'], ['int', 'int'], [{}, {}], 'B B', ['value'], [{}], '!'),
		'set_adc_channel_config': FunctionInfo(3, ['channel', 'enable'], ['int', 'bool'], [{}, {}], 'B !', [], [], ''),
		'get_adc_channel_config': FunctionInfo(4, ['channel'], ['int'], [{}], 'B', ['enable'], [{}], '!'),
		'get_adc_channel_value': FunctionInfo(5, ['channel'], ['int'], [{}], 'B', ['value'], [{}], 'H'),
		'get_adc_values': FunctionInfo(6, [], [], [], '', ['values'], [{}], '8H'),
		'set_adc_values_callback_configuration': FunctionInfo(7, ['period', 'value_has_to_change'], ['int', 'bool'], [{}, {}], 'I !', [], [], ''),
		'get_adc_values_callback_configuration': FunctionInfo(8, [], [], [], '', ['period', 'value_has_to_change'], [{}, {}], 'I !'),
		'get_count': FunctionInfo(10, [], [], [], '', ['count'], [{}], 'I'),
		'set_count_callback_configuration': FunctionInfo(11, ['period', 'value_has_to_change', 'option', 'min', 'max'], ['int', 'bool', 'char', 'int', 'int'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c I I', [], [], ''),
		'get_count_callback_configuration': FunctionInfo(12, [], [], [], '', ['period', 'value_has_to_change', 'option', 'min', 'max'], [{}, {}, {'x': 'off', 'o': 'outside', 'i': 'inside', '<': 'smaller', '>': 'greater'}, {}, {}], 'I ! c I I'),
		'get_spitfp_error_count': FunctionInfo(234, [], [], [], '', ['error_count_ack_checksum', 'error_count_message_checksum', 'error_count_frame', 'error_count_overflow'], [{}, {}, {}, {}], 'I I I I'),
		'set_bootloader_mode': FunctionInfo(235, ['mode'], ['int'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B', ['status'], [{0: 'ok', 1: 'invalid_mode', 2: 'no_change', 3: 'entry_function_not_present', 4: 'device_identifier_incorrect', 5: 'crc_mismatch'}], 'B'),
		'get_bootloader_mode': FunctionInfo(236, [], [], [], '', ['mode'], [{0: 'bootloader', 1: 'firmware', 2: 'bootloader_wait_for_reboot', 3: 'firmware_wait_for_reboot', 4: 'firmware_wait_for_erase_and_reboot'}], 'B'),
		'set_write_firmware_pointer': FunctionInfo(237, ['pointer'], ['int'], [{}], 'I', [], [], ''),
		'write_firmware': FunctionInfo(238, ['data'], [('int', 64)], [{}], '64B', ['status'], [{}], 'B'),
		'set_status_led_config': FunctionInfo(239, ['config'], ['int'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B', [], [], ''),
		'get_status_led_config': FunctionInfo(240, [], [], [], '', ['config'], [{0: 'off', 1: 'on', 2: 'show_heartbeat', 3: 'show_status'}], 'B'),
		'get_chip_temperature': FunctionInfo(242, [], [], [], '', ['temperature'], [{}], 'h'),
		'reset': FunctionInfo(243, [], [], [], '', [], [], ''),
		'write_uid': FunctionInfo(248, ['uid'], ['int'], [{}], 'I', [], [], ''),
		'read_uid': FunctionInfo(249, [], [], [], '', ['uid'], [{}], 'I'),
		'get_identity': FunctionInfo(255, [], [], [], '', ['uid', 'connected_uid', 'position', 'hardware_version', 'firmware_version', 'device_identifier'], [{}, {}, {}, {}, {}, {}], '8s 8s c 3B 3B H')
	}
	callbacks = {
		'adc_values': CallbackInfo(9, ['values'], [{}], '8H', None),
		'count': CallbackInfo(13, ['count'], [{}], 'I', None)
	}

	def __init__(self, uid, ipcon, device_class, mqttc):
		MQTTCallbackDevice.__init__(self, uid, ipcon, device_class, mqttc)

		re = self.response_expected
		re[1] = 3; re[2] = 1; re[3] = 3; re[4] = 1; re[5] = 1; re[6] = 1; re[7] = 2; re[8] = 1; re[10] = 1; re[11] = 2; re[12] = 1; re[234] = 1; re[235] = 1; re[236] = 1; re[237] = 3; re[238] = 1; re[239] = 3; re[240] = 1; re[242] = 1; re[243] = 3; re[248] = 3; re[249] = 1; re[255] = 1



devices = {
	'dc_brick': DCBrick,
	'hat_brick': HATBrick,
	'hat_zero_brick': HATZeroBrick,
	'imu_brick': IMUBrick,
	'imu_v2_brick': IMUV2Brick,
	'master_brick': MasterBrick,
	'red_brick': REDBrick,
	'servo_brick': ServoBrick,
	'silent_stepper_brick': SilentStepperBrick,
	'stepper_brick': StepperBrick,
	'accelerometer_bricklet': AccelerometerBricklet,
	'accelerometer_v2_bricklet': AccelerometerV2Bricklet,
	'air_quality_bricklet': AirQualityBricklet,
	'ambient_light_bricklet': AmbientLightBricklet,
	'ambient_light_v2_bricklet': AmbientLightV2Bricklet,
	'ambient_light_v3_bricklet': AmbientLightV3Bricklet,
	'analog_in_bricklet': AnalogInBricklet,
	'analog_in_v2_bricklet': AnalogInV2Bricklet,
	'analog_in_v3_bricklet': AnalogInV3Bricklet,
	'analog_out_bricklet': AnalogOutBricklet,
	'analog_out_v2_bricklet': AnalogOutV2Bricklet,
	'analog_out_v3_bricklet': AnalogOutV3Bricklet,
	'barometer_bricklet': BarometerBricklet,
	'barometer_v2_bricklet': BarometerV2Bricklet,
	'can_bricklet': CANBricklet,
	'can_v2_bricklet': CANV2Bricklet,
	'co2_bricklet': CO2Bricklet,
	'co2_v2_bricklet': CO2V2Bricklet,
	'color_bricklet': ColorBricklet,
	'color_v2_bricklet': ColorV2Bricklet,
	'compass_bricklet': CompassBricklet,
	'current12_bricklet': Current12Bricklet,
	'current25_bricklet': Current25Bricklet,
	'distance_ir_bricklet': DistanceIRBricklet,
	'distance_ir_v2_bricklet': DistanceIRV2Bricklet,
	'distance_us_bricklet': DistanceUSBricklet,
	'distance_us_v2_bricklet': DistanceUSV2Bricklet,
	'dmx_bricklet': DMXBricklet,
	'dual_button_bricklet': DualButtonBricklet,
	'dual_button_v2_bricklet': DualButtonV2Bricklet,
	'dual_relay_bricklet': DualRelayBricklet,
	'dust_detector_bricklet': DustDetectorBricklet,
	'e_paper_296x128_bricklet': EPaper296x128Bricklet,
	'energy_monitor_bricklet': EnergyMonitorBricklet,
	'gps_bricklet': GPSBricklet,
	'gps_v2_bricklet': GPSV2Bricklet,
	'hall_effect_bricklet': HallEffectBricklet,
	'hall_effect_v2_bricklet': HallEffectV2Bricklet,
	'humidity_bricklet': HumidityBricklet,
	'humidity_v2_bricklet': HumidityV2Bricklet,
	'industrial_analog_out_bricklet': IndustrialAnalogOutBricklet,
	'industrial_analog_out_v2_bricklet': IndustrialAnalogOutV2Bricklet,
	'industrial_counter_bricklet': IndustrialCounterBricklet,
	'industrial_digital_in_4_bricklet': IndustrialDigitalIn4Bricklet,
	'industrial_digital_in_4_v2_bricklet': IndustrialDigitalIn4V2Bricklet,
	'industrial_digital_out_4_bricklet': IndustrialDigitalOut4Bricklet,
	'industrial_digital_out_4_v2_bricklet': IndustrialDigitalOut4V2Bricklet,
	'industrial_dual_0_20ma_bricklet': IndustrialDual020mABricklet,
	'industrial_dual_0_20ma_v2_bricklet': IndustrialDual020mAV2Bricklet,
	'industrial_dual_analog_in_bricklet': IndustrialDualAnalogInBricklet,
	'industrial_dual_analog_in_v2_bricklet': IndustrialDualAnalogInV2Bricklet,
	'industrial_dual_relay_bricklet': IndustrialDualRelayBricklet,
	'industrial_quad_relay_bricklet': IndustrialQuadRelayBricklet,
	'industrial_quad_relay_v2_bricklet': IndustrialQuadRelayV2Bricklet,
	'io16_bricklet': IO16Bricklet,
	'io16_v2_bricklet': IO16V2Bricklet,
	'io4_bricklet': IO4Bricklet,
	'io4_v2_bricklet': IO4V2Bricklet,
	'isolator_bricklet': IsolatorBricklet,
	'joystick_bricklet': JoystickBricklet,
	'joystick_v2_bricklet': JoystickV2Bricklet,
	'laser_range_finder_bricklet': LaserRangeFinderBricklet,
	'laser_range_finder_v2_bricklet': LaserRangeFinderV2Bricklet,
	'lcd_128x64_bricklet': LCD128x64Bricklet,
	'lcd_16x2_bricklet': LCD16x2Bricklet,
	'lcd_20x4_bricklet': LCD20x4Bricklet,
	'led_strip_bricklet': LEDStripBricklet,
	'led_strip_v2_bricklet': LEDStripV2Bricklet,
	'line_bricklet': LineBricklet,
	'linear_poti_bricklet': LinearPotiBricklet,
	'linear_poti_v2_bricklet': LinearPotiV2Bricklet,
	'load_cell_bricklet': LoadCellBricklet,
	'load_cell_v2_bricklet': LoadCellV2Bricklet,
	'moisture_bricklet': MoistureBricklet,
	'motion_detector_bricklet': MotionDetectorBricklet,
	'motion_detector_v2_bricklet': MotionDetectorV2Bricklet,
	'motorized_linear_poti_bricklet': MotorizedLinearPotiBricklet,
	'multi_touch_bricklet': MultiTouchBricklet,
	'multi_touch_v2_bricklet': MultiTouchV2Bricklet,
	'nfc_bricklet': NFCBricklet,
	'nfc_rfid_bricklet': NFCRFIDBricklet,
	'oled_128x64_bricklet': OLED128x64Bricklet,
	'oled_128x64_v2_bricklet': OLED128x64V2Bricklet,
	'oled_64x48_bricklet': OLED64x48Bricklet,
	'one_wire_bricklet': OneWireBricklet,
	'outdoor_weather_bricklet': OutdoorWeatherBricklet,
	'particulate_matter_bricklet': ParticulateMatterBricklet,
	'piezo_buzzer_bricklet': PiezoBuzzerBricklet,
	'piezo_speaker_bricklet': PiezoSpeakerBricklet,
	'piezo_speaker_v2_bricklet': PiezoSpeakerV2Bricklet,
	'ptc_bricklet': PTCBricklet,
	'ptc_v2_bricklet': PTCV2Bricklet,
	'real_time_clock_bricklet': RealTimeClockBricklet,
	'real_time_clock_v2_bricklet': RealTimeClockV2Bricklet,
	'remote_switch_bricklet': RemoteSwitchBricklet,
	'remote_switch_v2_bricklet': RemoteSwitchV2Bricklet,
	'rgb_led_button_bricklet': RGBLEDButtonBricklet,
	'rgb_led_bricklet': RGBLEDBricklet,
	'rgb_led_matrix_bricklet': RGBLEDMatrixBricklet,
	'rgb_led_v2_bricklet': RGBLEDV2Bricklet,
	'rotary_encoder_bricklet': RotaryEncoderBricklet,
	'rotary_encoder_v2_bricklet': RotaryEncoderV2Bricklet,
	'rotary_poti_bricklet': RotaryPotiBricklet,
	'rotary_poti_v2_bricklet': RotaryPotiV2Bricklet,
	'rs232_bricklet': RS232Bricklet,
	'rs232_v2_bricklet': RS232V2Bricklet,
	'rs485_bricklet': RS485Bricklet,
	'segment_display_4x7_bricklet': SegmentDisplay4x7Bricklet,
	'segment_display_4x7_v2_bricklet': SegmentDisplay4x7V2Bricklet,
	'solid_state_relay_bricklet': SolidStateRelayBricklet,
	'solid_state_relay_v2_bricklet': SolidStateRelayV2Bricklet,
	'sound_intensity_bricklet': SoundIntensityBricklet,
	'sound_pressure_level_bricklet': SoundPressureLevelBricklet,
	'temperature_bricklet': TemperatureBricklet,
	'temperature_ir_bricklet': TemperatureIRBricklet,
	'temperature_ir_v2_bricklet': TemperatureIRV2Bricklet,
	'temperature_v2_bricklet': TemperatureV2Bricklet,
	'thermal_imaging_bricklet': ThermalImagingBricklet,
	'thermocouple_bricklet': ThermocoupleBricklet,
	'thermocouple_v2_bricklet': ThermocoupleV2Bricklet,
	'tilt_bricklet': TiltBricklet,
	'uv_light_bricklet': UVLightBricklet,
	'uv_light_v2_bricklet': UVLightV2Bricklet,
	'voltage_bricklet': VoltageBricklet,
	'voltage_current_bricklet': VoltageCurrentBricklet,
	'voltage_current_v2_bricklet': VoltageCurrentV2Bricklet,
	'xmc1400_breakout_bricklet': XMC1400BreakoutBricklet
}





mqtt_names = {
	11 : 'dc_brick',
	111 : 'hat_brick',
	112 : 'hat_zero_brick',
	16 : 'imu_brick',
	18 : 'imu_v2_brick',
	13 : 'master_brick',
	17 : 'red_brick',
	14 : 'servo_brick',
	19 : 'silent_stepper_brick',
	15 : 'stepper_brick',
	250 : 'accelerometer_bricklet',
	2130 : 'accelerometer_v2_bricklet',
	297 : 'air_quality_bricklet',
	21 : 'ambient_light_bricklet',
	259 : 'ambient_light_v2_bricklet',
	2131 : 'ambient_light_v3_bricklet',
	219 : 'analog_in_bricklet',
	251 : 'analog_in_v2_bricklet',
	295 : 'analog_in_v3_bricklet',
	220 : 'analog_out_bricklet',
	256 : 'analog_out_v2_bricklet',
	2115 : 'analog_out_v3_bricklet',
	221 : 'barometer_bricklet',
	2117 : 'barometer_v2_bricklet',
	270 : 'can_bricklet',
	2107 : 'can_v2_bricklet',
	262 : 'co2_bricklet',
	2147 : 'co2_v2_bricklet',
	243 : 'color_bricklet',
	2128 : 'color_v2_bricklet',
	2153 : 'compass_bricklet',
	23 : 'current12_bricklet',
	24 : 'current25_bricklet',
	25 : 'distance_ir_bricklet',
	2125 : 'distance_ir_v2_bricklet',
	229 : 'distance_us_bricklet',
	299 : 'distance_us_v2_bricklet',
	285 : 'dmx_bricklet',
	230 : 'dual_button_bricklet',
	2119 : 'dual_button_v2_bricklet',
	26 : 'dual_relay_bricklet',
	260 : 'dust_detector_bricklet',
	2146 : 'e_paper_296x128_bricklet',
	2152 : 'energy_monitor_bricklet',
	222 : 'gps_bricklet',
	276 : 'gps_v2_bricklet',
	240 : 'hall_effect_bricklet',
	2132 : 'hall_effect_v2_bricklet',
	27 : 'humidity_bricklet',
	283 : 'humidity_v2_bricklet',
	258 : 'industrial_analog_out_bricklet',
	2116 : 'industrial_analog_out_v2_bricklet',
	293 : 'industrial_counter_bricklet',
	223 : 'industrial_digital_in_4_bricklet',
	2100 : 'industrial_digital_in_4_v2_bricklet',
	224 : 'industrial_digital_out_4_bricklet',
	2124 : 'industrial_digital_out_4_v2_bricklet',
	228 : 'industrial_dual_0_20ma_bricklet',
	2120 : 'industrial_dual_0_20ma_v2_bricklet',
	249 : 'industrial_dual_analog_in_bricklet',
	2121 : 'industrial_dual_analog_in_v2_bricklet',
	284 : 'industrial_dual_relay_bricklet',
	225 : 'industrial_quad_relay_bricklet',
	2102 : 'industrial_quad_relay_v2_bricklet',
	28 : 'io16_bricklet',
	2114 : 'io16_v2_bricklet',
	29 : 'io4_bricklet',
	2111 : 'io4_v2_bricklet',
	2122 : 'isolator_bricklet',
	210 : 'joystick_bricklet',
	2138 : 'joystick_v2_bricklet',
	255 : 'laser_range_finder_bricklet',
	2144 : 'laser_range_finder_v2_bricklet',
	298 : 'lcd_128x64_bricklet',
	211 : 'lcd_16x2_bricklet',
	212 : 'lcd_20x4_bricklet',
	231 : 'led_strip_bricklet',
	2103 : 'led_strip_v2_bricklet',
	241 : 'line_bricklet',
	213 : 'linear_poti_bricklet',
	2139 : 'linear_poti_v2_bricklet',
	253 : 'load_cell_bricklet',
	2104 : 'load_cell_v2_bricklet',
	232 : 'moisture_bricklet',
	233 : 'motion_detector_bricklet',
	292 : 'motion_detector_v2_bricklet',
	267 : 'motorized_linear_poti_bricklet',
	234 : 'multi_touch_bricklet',
	2129 : 'multi_touch_v2_bricklet',
	286 : 'nfc_bricklet',
	246 : 'nfc_rfid_bricklet',
	263 : 'oled_128x64_bricklet',
	2112 : 'oled_128x64_v2_bricklet',
	264 : 'oled_64x48_bricklet',
	2123 : 'one_wire_bricklet',
	288 : 'outdoor_weather_bricklet',
	2110 : 'particulate_matter_bricklet',
	214 : 'piezo_buzzer_bricklet',
	242 : 'piezo_speaker_bricklet',
	2145 : 'piezo_speaker_v2_bricklet',
	226 : 'ptc_bricklet',
	2101 : 'ptc_v2_bricklet',
	268 : 'real_time_clock_bricklet',
	2106 : 'real_time_clock_v2_bricklet',
	235 : 'remote_switch_bricklet',
	289 : 'remote_switch_v2_bricklet',
	282 : 'rgb_led_button_bricklet',
	271 : 'rgb_led_bricklet',
	272 : 'rgb_led_matrix_bricklet',
	2127 : 'rgb_led_v2_bricklet',
	236 : 'rotary_encoder_bricklet',
	294 : 'rotary_encoder_v2_bricklet',
	215 : 'rotary_poti_bricklet',
	2140 : 'rotary_poti_v2_bricklet',
	254 : 'rs232_bricklet',
	2108 : 'rs232_v2_bricklet',
	277 : 'rs485_bricklet',
	237 : 'segment_display_4x7_bricklet',
	2137 : 'segment_display_4x7_v2_bricklet',
	244 : 'solid_state_relay_bricklet',
	296 : 'solid_state_relay_v2_bricklet',
	238 : 'sound_intensity_bricklet',
	290 : 'sound_pressure_level_bricklet',
	216 : 'temperature_bricklet',
	217 : 'temperature_ir_bricklet',
	291 : 'temperature_ir_v2_bricklet',
	2113 : 'temperature_v2_bricklet',
	278 : 'thermal_imaging_bricklet',
	266 : 'thermocouple_bricklet',
	2109 : 'thermocouple_v2_bricklet',
	239 : 'tilt_bricklet',
	265 : 'uv_light_bricklet',
	2118 : 'uv_light_v2_bricklet',
	218 : 'voltage_bricklet',
	227 : 'voltage_current_bricklet',
	2105 : 'voltage_current_v2_bricklet',
	279 : 'xmc1400_breakout_bricklet'
}





display_names = {
	11 : 'DC Brick',
	111 : 'HAT Brick',
	112 : 'HAT Zero Brick',
	16 : 'IMU Brick',
	18 : 'IMU Brick 2.0',
	13 : 'Master Brick',
	17 : 'RED Brick',
	14 : 'Servo Brick',
	19 : 'Silent Stepper Brick',
	15 : 'Stepper Brick',
	250 : 'Accelerometer Bricklet',
	2130 : 'Accelerometer Bricklet 2.0',
	297 : 'Air Quality Bricklet',
	21 : 'Ambient Light Bricklet',
	259 : 'Ambient Light Bricklet 2.0',
	2131 : 'Ambient Light Bricklet 3.0',
	219 : 'Analog In Bricklet',
	251 : 'Analog In Bricklet 2.0',
	295 : 'Analog In Bricklet 3.0',
	220 : 'Analog Out Bricklet',
	256 : 'Analog Out Bricklet 2.0',
	2115 : 'Analog Out Bricklet 3.0',
	221 : 'Barometer Bricklet',
	2117 : 'Barometer Bricklet 2.0',
	270 : 'CAN Bricklet',
	2107 : 'CAN Bricklet 2.0',
	262 : 'CO2 Bricklet',
	2147 : 'CO2 Bricklet 2.0',
	243 : 'Color Bricklet',
	2128 : 'Color Bricklet 2.0',
	2153 : 'Compass Bricklet',
	23 : 'Current12 Bricklet',
	24 : 'Current25 Bricklet',
	25 : 'Distance IR Bricklet',
	2125 : 'Distance IR Bricklet 2.0',
	229 : 'Distance US Bricklet',
	299 : 'Distance US Bricklet 2.0',
	285 : 'DMX Bricklet',
	230 : 'Dual Button Bricklet',
	2119 : 'Dual Button Bricklet 2.0',
	26 : 'Dual Relay Bricklet',
	260 : 'Dust Detector Bricklet',
	2146 : 'E-Paper 296x128 Bricklet',
	2152 : 'Energy Monitor Bricklet',
	222 : 'GPS Bricklet',
	276 : 'GPS Bricklet 2.0',
	240 : 'Hall Effect Bricklet',
	2132 : 'Hall Effect Bricklet 2.0',
	27 : 'Humidity Bricklet',
	283 : 'Humidity Bricklet 2.0',
	258 : 'Industrial Analog Out Bricklet',
	2116 : 'Industrial Analog Out Bricklet 2.0',
	293 : 'Industrial Counter Bricklet',
	223 : 'Industrial Digital In 4 Bricklet',
	2100 : 'Industrial Digital In 4 Bricklet 2.0',
	224 : 'Industrial Digital Out 4 Bricklet',
	2124 : 'Industrial Digital Out 4 Bricklet 2.0',
	228 : 'Industrial Dual 0-20mA Bricklet',
	2120 : 'Industrial Dual 0-20mA Bricklet 2.0',
	249 : 'Industrial Dual Analog In Bricklet',
	2121 : 'Industrial Dual Analog In Bricklet 2.0',
	284 : 'Industrial Dual Relay Bricklet',
	225 : 'Industrial Quad Relay Bricklet',
	2102 : 'Industrial Quad Relay Bricklet 2.0',
	28 : 'IO-16 Bricklet',
	2114 : 'IO-16 Bricklet 2.0',
	29 : 'IO-4 Bricklet',
	2111 : 'IO-4 Bricklet 2.0',
	2122 : 'Isolator Bricklet',
	210 : 'Joystick Bricklet',
	2138 : 'Joystick Bricklet 2.0',
	255 : 'Laser Range Finder Bricklet',
	2144 : 'Laser Range Finder Bricklet 2.0',
	298 : 'LCD 128x64 Bricklet',
	211 : 'LCD 16x2 Bricklet',
	212 : 'LCD 20x4 Bricklet',
	231 : 'LED Strip Bricklet',
	2103 : 'LED Strip Bricklet 2.0',
	241 : 'Line Bricklet',
	213 : 'Linear Poti Bricklet',
	2139 : 'Linear Poti Bricklet 2.0',
	253 : 'Load Cell Bricklet',
	2104 : 'Load Cell Bricklet 2.0',
	232 : 'Moisture Bricklet',
	233 : 'Motion Detector Bricklet',
	292 : 'Motion Detector Bricklet 2.0',
	267 : 'Motorized Linear Poti Bricklet',
	234 : 'Multi Touch Bricklet',
	2129 : 'Multi Touch Bricklet 2.0',
	286 : 'NFC Bricklet',
	246 : 'NFC/RFID Bricklet',
	263 : 'OLED 128x64 Bricklet',
	2112 : 'OLED 128x64 Bricklet 2.0',
	264 : 'OLED 64x48 Bricklet',
	2123 : 'One Wire Bricklet',
	288 : 'Outdoor Weather Bricklet',
	2110 : 'Particulate Matter Bricklet',
	214 : 'Piezo Buzzer Bricklet',
	242 : 'Piezo Speaker Bricklet',
	2145 : 'Piezo Speaker Bricklet 2.0',
	226 : 'PTC Bricklet',
	2101 : 'PTC Bricklet 2.0',
	268 : 'Real-Time Clock Bricklet',
	2106 : 'Real-Time Clock Bricklet 2.0',
	235 : 'Remote Switch Bricklet',
	289 : 'Remote Switch Bricklet 2.0',
	282 : 'RGB LED Button Bricklet',
	271 : 'RGB LED Bricklet',
	272 : 'RGB LED Matrix Bricklet',
	2127 : 'RGB LED Bricklet 2.0',
	236 : 'Rotary Encoder Bricklet',
	294 : 'Rotary Encoder Bricklet 2.0',
	215 : 'Rotary Poti Bricklet',
	2140 : 'Rotary Poti Bricklet 2.0',
	254 : 'RS232 Bricklet',
	2108 : 'RS232 Bricklet 2.0',
	277 : 'RS485 Bricklet',
	237 : 'Segment Display 4x7 Bricklet',
	2137 : 'Segment Display 4x7 Bricklet 2.0',
	244 : 'Solid State Relay Bricklet',
	296 : 'Solid State Relay Bricklet 2.0',
	238 : 'Sound Intensity Bricklet',
	290 : 'Sound Pressure Level Bricklet',
	216 : 'Temperature Bricklet',
	217 : 'Temperature IR Bricklet',
	291 : 'Temperature IR Bricklet 2.0',
	2113 : 'Temperature Bricklet 2.0',
	278 : 'Thermal Imaging Bricklet',
	266 : 'Thermocouple Bricklet',
	2109 : 'Thermocouple Bricklet 2.0',
	239 : 'Tilt Bricklet',
	265 : 'UV Light Bricklet',
	2118 : 'UV Light Bricklet 2.0',
	218 : 'Voltage Bricklet',
	227 : 'Voltage/Current Bricklet',
	2105 : 'Voltage/Current Bricklet 2.0',
	279 : 'XMC1400 Breakout Bricklet'
}


#!/usr/bin/env python
# -*- coding: utf-8 -*-


def json_error(message, resultDict=None):
    logging.error(message)
    if resultDict is not None:
        resultDict['_ERROR'] = message
        return json.dumps(resultDict)
    return json.dumps({'_ERROR': message})

message_tup = namedtuple('message_tup', ['topic', 'payload'])

class MQTTBindings:
    def __init__(self, debug, no_symbolic_response, show_payload, global_prefix, ipcon_timeout, broker_username, broker_password, broker_certificate, broker_tls_insecure):
        self.no_symbolic_response = no_symbolic_response
        self.show_payload = show_payload

        self.broker_connected_event = threading.Event()
        self.ipcon_connected_event = threading.Event()

        self.ipcon = IPConnection()
        self.ipcon.set_auto_reconnect_internal(True, lambda e: logging.info("Could not connect to Brick Daemon: {}. Will retry.".format(str(e))))
        self.handle_ipcon_exceptions(lambda i: i.set_timeout(ipcon_timeout))

        self.mqttc = mqtt.Client(userdata=len(global_prefix))
        logging.basicConfig(format='%(asctime)s <%(levelname)s> %(name)s: %(message)s', level=logging.DEBUG if debug else logging.INFO)
        if debug:
            self.mqttc.enable_logger()

        try:
            logging.root.name = 'MQTT bindings'
        except:
            pass

        if broker_username is not None:
            self.mqttc.username_pw_set(broker_username, broker_password)

        if broker_certificate is not None:
            self.mqttc.tls_set(broker_certificate)

        if broker_tls_insecure:
            self.mqttc.tls_insecure_set(True)

        self.mqttc.on_message = self.on_message

        self.was_connected = False
        self.mqttc.on_connect = self.on_connect
        self.mqttc.on_log = self.on_log

        self.callback_devices = {}
        self.enumerate_response_paths = set()

        self.ip_connection_callbacks = {
            "enumerate": IPConnection.CALLBACK_ENUMERATE,
            "connected": IPConnection.CALLBACK_CONNECTED,
            "disconnected": IPConnection.CALLBACK_DISCONNECTED
        }

        self.ip_connection_callback_names = {
            IPConnection.CALLBACK_ENUMERATE: ["uid", "connected_uid", "position", "hardware_version", "firmware_version", "device_identifier", "enumeration_type"],
            IPConnection.CALLBACK_CONNECTED: ["connect_reason"],
            IPConnection.CALLBACK_DISCONNECTED: ["disconnect_reason"]
        }

        self.ip_connection_response_paths = {
            IPConnection.CALLBACK_ENUMERATE: set(),
            IPConnection.CALLBACK_CONNECTED: set(),
            IPConnection.CALLBACK_DISCONNECTED: set()
        }

        self.global_prefix = global_prefix

    def on_log(self, client, userdata, level, buf):
        if 'Connection failed, retrying' in buf:
            logging.info("Could not connect to MQTT Broker. Will retry.")

    def ipcon_connect_unblocker(self, reason):
        self.ipcon_connected_event.set()
        self.ip_connection_callback_fn(self.ipcon.CALLBACK_CONNECTED, reason)

    def connect_to_brickd(self, ipcon_host, ipcon_port, ipcon_auth_secret):
        logging.debug("Connecting to brickd at {}:{}".format(ipcon_host, ipcon_port))

        self.ipcon.register_callback(self.ipcon.CALLBACK_CONNECTED, self.ipcon_connect_unblocker)
        try:
            self.ipcon.connect(ipcon_host, ipcon_port)
        except:
            pass

        self.ipcon_connected_event.wait()
        self.ipcon.register_callback(IPConnection.CALLBACK_CONNECTED, lambda *args: self.ip_connection_callback_fn(IPConnection.CALLBACK_CONNECTED, *args))
        self.ipcon.register_callback(IPConnection.CALLBACK_DISCONNECTED, lambda *args: self.ip_connection_callback_fn(IPConnection.CALLBACK_DISCONNECTED, *args))
        self.ipcon.register_callback(IPConnection.CALLBACK_ENUMERATE, lambda *args: self.ip_connection_callback_fn(IPConnection.CALLBACK_ENUMERATE, *args))
        logging.debug("Connected to brickd at {}:{}".format(ipcon_host, ipcon_port))
        if ipcon_auth_secret != "":
            self.authenticate(ipcon_auth_secret, "Could not authenticate.")

    def connect_to_broker(self, broker_host, broker_port):
        logging.debug("Configuring connection to MQTT broker at {}:{}".format(broker_host, broker_port))
        try:
            self.mqttc.will_set(self.global_prefix + 'callback/bindings/last_will', 'null')
            # Don't use connect: connect_async + loop_start support retrying to connect.
            self.mqttc.connect_async(broker_host, broker_port)
        except Exception as e:
            fatal_error("Connecting to MQTT broker failed: " + str(e), ERROR_NO_CONNECTION_TO_BROKER)
        logging.debug("Connected to MQTT broker at {}:{}".format(broker_host, broker_port))
        self.mqttc.loop_start()
        self.broker_connected_event.wait()

    def run_config(self, config):
        for topic, payload in config.items():
            self.on_message(self.mqttc, len(self.global_prefix), message_tup(topic, json.dumps(payload)))

    def run(self):
        while(True):
            time.sleep(1)

    def ip_connection_callback_log(self, callback_id, *args):
        d_dis = {
                IPConnection.DISCONNECT_REASON_REQUEST: 'Disconnect was requested by user.',
                IPConnection.DISCONNECT_REASON_ERROR: 'Disconnect because of an unresolvable error.',
                IPConnection.DISCONNECT_REASON_SHUTDOWN: 'Disconnect initiated by Brick Daemon or WIFI/Ethernet Extension.'
            }
        d_con = {
                IPConnection.CONNECT_REASON_REQUEST: 'Connection established after request from user.',
                IPConnection.CONNECT_REASON_AUTO_RECONNECT: 'Connection after auto-reconnect.'
        }

        d_enum = {
            IPConnection.ENUMERATION_TYPE_AVAILABLE: 'Device available',
            IPConnection.ENUMERATION_TYPE_CONNECTED: 'Device connected',
            IPConnection.ENUMERATION_TYPE_DISCONNECTED: 'Device disconnected'
        }

        message = ''
        if callback_id == IPConnection.CALLBACK_CONNECTED:
            message = 'Connected to Brick Daemon: {}'.format(d_con[args[0]])
        elif callback_id == IPConnection.CALLBACK_DISCONNECTED:
            message = 'Disconnected from Brick Daemon: {}'.format(d_dis[args[0]])
        elif callback_id == IPConnection.CALLBACK_ENUMERATE:
            uid, conn_uid, pos, hw_ver, fw_ver, dev_id, reason = args
            if reason == IPConnection.ENUMERATION_TYPE_DISCONNECTED:
                message = '{}: UID: {}'.format(d_enum[reason], uid)
            else:
                message = '{}: {} at {} (Pos {}), Hardware: {}.{}.{}, Firmware: {}.{}.{}, Dev ID: {}'
                message = message.format(d_enum[reason], uid, conn_uid, pos, hw_ver[0], hw_ver[1], hw_ver[2], fw_ver[0], fw_ver[1], fw_ver[2], dev_id)
        else:
            logging.warning("Received unknown IPConnection callback with id {}".format(callback_id))
            return

        logging.debug(message)

    def ip_connection_callback_fn(self, callback_id, *args):
        self.ip_connection_callback_log(callback_id, *args)

        if callback_id == self.ipcon.CALLBACK_ENUMERATE:
            symbols = [{}, {}, {}, {}, {}, mqtt_names,
                       {self.ipcon.ENUMERATION_TYPE_AVAILABLE: "available",
                        self.ipcon.ENUMERATION_TYPE_CONNECTED: "connected",
                        self.ipcon.ENUMERATION_TYPE_DISCONNECTED: "disconnected"}]
            dev_id = args[5]
        elif callback_id == self.ipcon.CALLBACK_CONNECTED:
            symbols = [{self.ipcon.CONNECT_REASON_REQUEST: "request",
                        self.ipcon.CONNECT_REASON_AUTO_RECONNECT: "auto-reconnect"}]
        elif callback_id == self.ipcon.CALLBACK_DISCONNECTED:
            symbols = [{self.ipcon.DISCONNECT_REASON_REQUEST: "request",
                        self.ipcon.DISCONNECT_REASON_ERROR: "error",
                        self.ipcon.DISCONNECT_REASON_SHUTDOWN: "shutdown"}]

        if not self.no_symbolic_response:
            args = self.translate_symbols(symbols, args)

        d = dict(zip(self.ip_connection_callback_names[callback_id], args))

        if "enumeration_type" in d and d["enumeration_type"] != 2 and "device_identifier" in d:
            d["_display_name"] = display_names[dev_id]

        payload = json.dumps(d)
        for path in self.ip_connection_response_paths[callback_id]:
            self.mqttc.publish(path, payload)

    def register_ip_connection_callback(self, callback_id, response_path):
        self.ip_connection_response_paths[callback_id].add(response_path)
        logging.debug("Registered ip connection callback {} under topic {}.".format(callback_id, response_path))

    def deregister_ip_connection_callback(self, callback_id, response_path):
        self.ip_connection_response_paths[callback_id].discard(response_path)
        logging.debug("Deregistered ip connection callback {} for topic {}.".format(callback_id, response_path))


    def handle_ip_connection_call(self, request_type, device, function, json_args, response_path):

        if request_type == "request":
            if function == "enumerate":
                logging.debug("Enumerating devices.")
                self.handle_ipcon_exceptions(lambda i: i.enumerate())
            elif function == "get_connection_state":
                state = self.handle_ipcon_exceptions(lambda i: i.get_connection_state())
                state = self.translate_symbols([{
                    self.ipcon.CONNECTION_STATE_DISCONNECTED: "disconnected",
                    self.ipcon.CONNECTION_STATE_CONNECTED: "connected",
                    self.ipcon.CONNECTION_STATE_PENDING: "pending"}], [state])[0]
                return json.dumps({'connection_state': state})
            else:
                return json_error("Unknown ip connection function " + function)

        elif request_type == "register":
            if function not in self.ip_connection_callbacks.keys():
                return json_error("Unknown ip connection callback " + function)
            callback_id = self.ip_connection_callbacks[function]

            try:
                should_register = json.loads(json_args)
            except Exception as e:
                payload = ""
                if self.show_payload:
                    payload = ". \n\tPayload was: " + repr(json_args)
                return json_error("Could not parse payload for {} callback registration as JSON encoding a boolean: {}{}".format(function, str(e), payload))

            if not isinstance(should_register, bool):
                #also support {"register": true/false} in addition to a top-level boolean
                if isinstance(should_register, dict) and 'register' in should_register and type(should_register['register']) == bool:
                    should_register = should_register['register']
                else:
                    return json_error("Expected bool as parameter of callback registration, but got " + str(json_args))

            if should_register:
                self.register_ip_connection_callback(callback_id, response_path)
            else:
                self.deregister_ip_connection_callback(callback_id, response_path)
        else:
            return json_error("Unknown ip connection request {}", request_type)

    def handle_bindings_call(self, request_type, device, function, json_args, response_path):
        if request_type == "callback" and function == "restart":
            logging.warning("Another MQTT bindings instance started on this broker with the same global prefix. This is not recommended as both bindings instances will receive requests and send responses.")
            return

        if request_type != "request":
            return json_error("Unknown bindings request {}".format(request_type))

        if function != "reset_callbacks":
            return json_error("Unknown bindings function {}".format(function))

        logging.debug("Resetting callbacks")

        self.ip_connection_response_paths = {
            IPConnection.CALLBACK_ENUMERATE: set(),
            IPConnection.CALLBACK_CONNECTED: set(),
            IPConnection.CALLBACK_DISCONNECTED: set()
        }

        self.callback_devices = {}
        self.ipcon.devices = {}


    def on_connect(self, mqttc, obj, flags, rc):
        if rc == 0:
            logging.debug("Connected to mqtt broker.")
            self.mqttc.subscribe(self.global_prefix + "request/#")
            self.mqttc.subscribe(self.global_prefix + "register/#")
            if not self.was_connected:
                self.mqttc.publish(self.global_prefix + "callback/bindings/restart", "null")
                self.was_connected = True
            self.mqttc.subscribe(self.global_prefix + "callback/bindings/restart")
            self.broker_connected_event.set()
        else:
            logging.debug("Failed to connect to mqtt broker: " + mqtt.connack_string(rc))

    @staticmethod
    def parse_path(global_prefix_len, path):
        if global_prefix_len > 0:
            global_prefix = path[:global_prefix_len - 1] #main ensures that the prefix ends with a '/'
        else:
            global_prefix = None

        splt = path[global_prefix_len:].split("/")

        if len(splt) < 3:
            logging.error("malformed topic: Expected at least [request_type]/[device_type]/(uid if device_type is not 'ip_connection'/)[function], but got: " + path)
            return

        request_type = splt.pop(0)
        device = splt.pop(0)
        uid_less_device = device in ["ip_connection", "bindings"]
        if not uid_less_device and len(splt) < 2:
            logging.error("malformed topic: Expected at least [request_type; was: {}]/[device_type; was: {}]/[uid]/[function], but got: {}".format(request_type, device, path))
            return

        uid = splt.pop(0) if not uid_less_device else None
        function = splt.pop(0)
        suffix = '/'.join(splt) if len(splt) > 0 else None

        response_type = "response" if request_type == "request" else "callback"

        to_join = [global_prefix, response_type, device] if global_prefix_len > 0 else [response_type, device]

        if uid is not None:
            to_join.append(uid)
        to_join.append(function)
        if suffix is not None:
            to_join.append(suffix)

        response_path = '/'.join(to_join)

        return global_prefix, request_type, device, uid, function, suffix, response_path

    def on_message(self, mqttc, global_prefix_len, msg):
        try:
            logging.debug("\n")
            path_info = self.parse_path(global_prefix_len, msg.topic)
            if path_info is None:
                return

            global_prefix, request_type, device, uid, function, suffix, response_path = path_info

            # msg.payload could be from an init file, then it is already decoded.
            if isinstance(msg.payload, str):
                payload = msg.payload
            else:
                try:
                    payload = msg.payload.decode('utf-8')
                except Exception as e:
                    payload_str = (" Payload was: " + repr(msg.payload)) if self.show_payload else ''
                    response = json_error("Could not decode payload as utf-8: {}{}".format(str(e), payload_str))
                    logging.debug("Publishing response to {}".format(response_path))
                    self.mqttc.publish(response_path, response)
                    logging.debug("\n")
                    return

            if device == "ip_connection":
                response = self.handle_ip_connection_call(request_type, device, function, payload, response_path)
            elif device == "bindings":
                response = self.handle_bindings_call(request_type, device, function, payload, response_path)
            else:
                response = self.dispatch_call(request_type, device, uid, function, payload, response_path)

            if response is None:
                return
            logging.debug("Publishing response to {}".format(response_path))
            self.mqttc.publish(response_path, response)
            logging.debug("\n")
        except:
            traceback.print_exc()


    def handle_ipcon_exceptions(self, function, resultDict=None, infoString = None):
        try:
            return function(self.ipcon)
        except Error as e:
            if e.value in [Error.INVALID_PARAMETER, Error.NOT_SUPPORTED, Error.UNKNOWN_ERROR_CODE, Error.STREAM_OUT_OF_SYNC, Error.TIMEOUT, Error.NOT_CONNECTED]:
                if infoString is not None:
                    return json_error(e.description + " " + infoString, resultDict)
                return json_error(e.description, resultDict)

            fatal_error(e.description.lower(), IPCONNECTION_ERROR_OFFSET - e.value)
        except struct.error as e:
            if infoString is not None:
                return json_error(e.args[0] + " " + infoString, resultDict)
            return json_error(e.args[0], resultDict)
        except socket.error as e:
            fatal_error(str(e).lower(), ERROR_SOCKET_ERROR)
        except Exception as e:
            if sys.hexversion < 0x03000000 and isinstance(e, ValueError) and "JSON" in str(e):
                return json_error(str(e), resultDict)
            if sys.hexversion >= 0x03000000 and isinstance(e, json.JSONDecodeError):
                return json_error(str(e), resultDict)
            fatal_error(str(e).lower(), ERROR_OTHER_EXCEPTION)

    def authenticate(self, secret, message):
        logging.debug("Authenticating. Disabling auto-reconnect")
        # don't auto-reconnect on authentication error
        self.ipcon.set_auto_reconnect(False)

        try:
            self.ipcon.authenticate(secret)
        except:
            fatal_error(message, ERROR_AUTHENTICATION_ERROR)

        logging.debug("Authentication succeded. Re-enabling auto-reconnect")
        self.ipcon.set_auto_reconnect(True)

    @staticmethod
    def type_check_args(args, arg_names, arg_types):
        type_map = {
            'int': int,
            'float': float,
            'bool': bool,
            'char': str
        }

        for a, n, t in zip(args, arg_names, arg_types):
            if isinstance(t, tuple):
                t_name, t_len = t
                t = type_map[t_name]
                if not isinstance(a, list):
                    return "Argument {name} was not of expected type list of {type}.".format(name=n, type=t_name)
                if t_len < 0 and len(a) > abs(t_len):
                    return "Argument {name} was a list of length {have}, but max length of {want} is allowed.".format(name=n, have=len(a), want=abs(t_len))
                if t_len > 0 and not len(a) == t_len:
                    return "Argument {name} was a list of length {have}, but length {want} was expected.".format(name=n, have=len(a), want=t_len)

                for idx, a_elem in enumerate(a):
                    if type(a_elem) != t:
                        return "Argument {name}[{idx}] was not of expected type {type}.".format(name=n, idx=idx, type=t_name)
            else:
                if t == 'char' or t == 'string':
                    if sys.hexversion < 0x03000000 and not isinstance(a, basestring):
                        return "Argument {name} was not of expected type {type}.".format(name=n, type=t)
                    elif sys.hexversion >= 0x03000000 and not isinstance(a, str):
                        return "Argument {name} was not of expected type {type}.".format(name=n, type=t)
                    if t == 'char' and len(a) > 1:
                        return "Argument {name} was a string of length {len}, but a single character was expected.".format(name=n, len=len(a))
                elif type(a) != type_map[t]:
                    return "Argument {name} was not of expected type {type}.".format(name=n, type=t)

    def is_error(self, response):
        if isinstance(response, str) or isinstance(response, basestring):
            d = json.loads(response)
            return "_ERROR" in d
        return False

    def translate_symbols(self, symbol_list, data_list):
        return [(symbols[data] if isinstance(data, Hashable) and data in symbols else data)
                 for symbols, data in zip(symbol_list, data_list)]

    def device_stream_call(self, device, device_name, uid, fnName, fnInfo, json_args):
        logging.debug("Starting stream call {} for device {} of type {}.".format(fnName, uid, device_name))
        if len(json_args) > 0:
            try:
                obj = json.loads(json_args)
            except Exception as e:
                payload = ""
                if self.show_payload:
                    payload = ". \n\tPayload was: " + repr(json_args)
                return json_error("Could not parse payload for {} call of {} {} as JSON: {}{}".format(fnName, device_name, uid, str(e), payload))


        function_id, direction, high_level_roles_in, high_level_roles_out, \
            low_level_roles_in, low_level_roles_out, arg_names, arg_types, arg_symbols, \
            format_in, result_names, result_symbols, format_out, chunk_padding, \
            chunk_cardinality, chunk_max_offset, short_write, single_read, fixed_length = fnInfo

        request_data = []
        missing_args = []
        for a in arg_names:
            if a not in obj:
                missing_args.append(a)
            else:
                request_data.append(obj[a])

        if len(missing_args) > 0:
            return json_error("The arguments {} where missing for a call of {} of device {} of type {}.".format(str(missing_args), fnName, uid, device_name), dict([(name, None) for name in fnInfo.result_names]))


        normal_level_request_data = [data for role, data in zip(high_level_roles_in, request_data) if role == None]

        reversed_symbols = [{v: k for k, v in d.items()}  for d in fnInfo.arg_symbols] # reverse dict to map from constant to it's value
        normal_level_request_data = self.translate_symbols(reversed_symbols, normal_level_request_data)

        type_error = MQTTBindings.type_check_args(request_data, arg_names, arg_types)
        if type_error is not None:
            return json_error("Call {} of {} {}: {}".format(fnName, device_name, uid, type_error),  dict([(name, None) for name in result_names]))

        if device.response_expected[function_id] != 1 and "_response_expected" in obj:
            re = obj["_response_expected"]
            if isinstance(re, bool):
                device.set_response_expected(function_id, re)
            else:
                logging.debug("Ignoring _response_expected, it was not of boolean type. (Call of {} of device {} of type {}.)".format(fnName, uid, device_name))

        if direction == 'in':
            def create_low_level_request_data(stream_length, stream_chunk_offset, stream_chunk_data):
                low_level_request_data = []
                normal_level_request_data_iter = iter(normal_level_request_data)

                for role in low_level_roles_in:
                    if role == None:
                        low_level_request_data.append(next(normal_level_request_data_iter))
                    elif role == 'stream_length':
                        low_level_request_data.append(stream_length)
                    elif role == 'stream_chunk_offset':
                        low_level_request_data.append(stream_chunk_offset)
                    elif role == 'stream_chunk_data':
                        low_level_request_data.append(stream_chunk_data)

                return low_level_request_data

            stream_data_index = high_level_roles_in.index('stream_data')
            stream_data = request_data[stream_data_index]

            if sys.hexversion < 0x03000000:
                if isinstance(stream_data, basestring):
                    stream_data = create_char_list(stream_data)
            else:
                if isinstance(stream_data, str):
                    stream_data = create_char_list(stream_data)
            stream_length = len(stream_data)
            stream_chunk_offset = 0

            if short_write:
                stream_chunk_written_index = None if len(low_level_roles_out) == 1 else low_level_roles_out.index('stream_chunk_written')
                stream_written = 0

            if stream_length == 0:
                stream_chunk_data = [chunk_padding] * chunk_cardinality
                low_level_request_data = create_low_level_request_data(stream_length, stream_chunk_offset, stream_chunk_data)

                response = self.handle_ipcon_exceptions(lambda i: i.send_request(device, function_id, low_level_request_data, format_in, format_out), dict([(name, None) for name in result_names]), "(call of {} of {} {})".format(fnName, device_name, uid))
                if isinstance(response, dict) and "_ERROR" in response:
                    return response

                if short_write:
                    if stream_chunk_written_index == None:
                        stream_written = response
                    else:
                        stream_written = response[stream_chunk_written_index]
            else:
                while stream_chunk_offset < stream_length:
                    stream_chunk_data = create_chunk_data(stream_data, stream_chunk_offset, chunk_cardinality, chunk_padding)
                    low_level_request_data = create_low_level_request_data(stream_length, stream_chunk_offset, stream_chunk_data)

                    response = self.handle_ipcon_exceptions(lambda i: i.send_request(device, function_id, low_level_request_data, format_in, format_out), dict([(name, None) for name in result_names]), "(call of {} of {} {})".format(fnName, device_name, uid))
                    if isinstance(response, dict) and "_ERROR" in response:
                        return response

                    if short_write:
                        if stream_chunk_written_index == None:
                            stream_chunk_written = response
                        else:
                            stream_chunk_written = response[stream_chunk_written_index]

                        stream_written += stream_chunk_written

                        if stream_chunk_written < chunk_cardinality:
                            break # either last chunk or short write

                    stream_chunk_offset += chunk_cardinality

            if short_write:
                if not isinstance(response, tuple):
                    response = (response,)

                normal_level_response_iter = (data for role, data in zip(low_level_roles_out, response) if role == None)
                high_level_response = []

                for role in high_level_roles_out:
                    if role == None:
                        high_level_response.append(next(normal_level_response_iter))
                    elif role == 'stream_written':
                        high_level_response.append(stream_written)

                if len(high_level_response) == 1:
                    response = high_level_response[0]
                else:
                    response = tuple(high_level_response)
        else: # out
            low_level_response = self.handle_ipcon_exceptions(lambda i: i.send_request(device, function_id, normal_level_request_data, format_in, format_out), dict([(name, None) for name in result_names]), "(call of {} of {} {})".format(fnName, device_name, uid))
            if self.is_error(low_level_response):
                return low_level_response

            if fixed_length == None:
                stream_length_index = low_level_roles_out.index('stream_length')
                stream_length = low_level_response[stream_length_index]
            else:
                stream_length_index = None
                stream_length = fixed_length

            if not single_read:
                stream_chunk_offset_index = low_level_roles_out.index('stream_chunk_offset')
                stream_chunk_offset = low_level_response[stream_chunk_offset_index]
            else:
                stream_chunk_offset_index = None
                stream_chunk_offset = 0

            stream_chunk_data_index = low_level_roles_out.index('stream_chunk_data')
            stream_chunk_data = low_level_response[stream_chunk_data_index]

            if fixed_length != None and stream_chunk_offset == chunk_max_offset:
                stream_length = 0
                stream_out_of_sync = False
                stream_data = ()
            else:
                stream_out_of_sync = stream_chunk_offset != 0
                stream_data = stream_chunk_data

            while not stream_out_of_sync and len(stream_data) < stream_length:
                low_level_response = self.handle_ipcon_exceptions(lambda i: i.send_request(device, function_id, normal_level_request_data, format_in, format_out), dict([(name, None) for name in result_names]), "(call of {} of {} {})".format(fnName, device_name, uid))

                if self.is_error(low_level_response):
                    return low_level_response

                if stream_length_index != None:
                    stream_length = low_level_response[stream_length_index]

                if stream_chunk_offset_index != None:
                    stream_chunk_offset = low_level_response[stream_chunk_offset_index]

                stream_chunk_data = low_level_response[stream_chunk_data_index]
                stream_out_of_sync = stream_chunk_offset != len(stream_data)
                stream_data += stream_chunk_data

            if stream_out_of_sync: # discard remaining stream to bring it back in-sync
                while stream_chunk_offset + chunk_cardinality < stream_length:
                    low_level_response = self.handle_ipcon_exceptions(lambda i: i.send_request(device, function_id, normal_level_request_data, format_in, format_out), dict([(name, None) for name in result_names]), "(call of {} of {} {})".format(fnName, device_name, uid))
                    if self.is_error(low_level_response):
                        return low_level_response

                    if stream_length_index != None:
                        stream_length = low_level_response[stream_length_index]

                    if stream_chunk_offset_index != None:
                        stream_chunk_offset = low_level_response[stream_chunk_offset_index]

                    stream_chunk_data = low_level_response[stream_chunk_data_index]

                return json_error("Stream is out-of-sync", dict([(name, None) for name in result_names]))

            normal_level_response_iter = (data for role, data in zip(low_level_roles_out, low_level_response) if role == None)
            high_level_response = []

            for role in high_level_roles_out:
                if role == None:
                    high_level_response.append(next(normal_level_response_iter))
                elif role == 'stream_data':
                    high_level_response.append(stream_data[:stream_length])

            if len(high_level_response) == 1:
                response = high_level_response[0]
            else:
                response = tuple(high_level_response)

        if response != None:
            if len(result_symbols) == 1:
                response = (response,)

            if not self.no_symbolic_response:
                response = self.translate_symbols(fnInfo.result_symbols, response)
            response = json.dumps(dict(zip(result_names, response)))
            logging.debug("Stream call {} for device {} of type {} succeded.".format(fnName, uid, device_name))
            return response
    @staticmethod
    def parse_uid(uid):
        uid_ = base58decode(uid)

        if uid_ > 0xFFFFFFFF:
            uid_ = uid64_to_uid32(uid_)
        return uid_

    def ensure_dev_exists(self, uid, device_class, device_class_name, mqttc):
        uid_ = self.parse_uid(uid)

        if uid_ in self.ipcon.devices and isinstance(self.ipcon.devices[uid_], device_class):
            device = self.ipcon.devices[uid_]
        else:
            try:
                device = device_class(uid, self.ipcon, device_class, mqttc)
            except Exception as e:
                return False, json_error("Could not create device object: {}".format(str(e)))
        return True, device

    def dispatch_call(self, call_type, device_class_name, uid, fnName, json_args, response_path):
        if device_class_name not in devices:
            return json_error("Unknown device type " + device_class_name,)
        device_class = devices[device_class_name]
        if call_type == 'request':
            if fnName not in device_class.functions:
                return json_error("Unknown function {} for device {} of type {}".format(fnName, uid, device_class_name),)
            fnInfo = device_class.functions[fnName]

            success, device = self.ensure_dev_exists(uid, device_class, device_class_name, self.mqttc)
            if not success:
                return device

            if isinstance(fnInfo, HighLevelFunctionInfo):
                return self.device_stream_call(device, device_class_name, uid, fnName, fnInfo, json_args)
            else:
                return self.device_call(device, device_class_name, uid, fnName, fnInfo, json_args)
        elif call_type == 'register':
            if fnName not in device_class.callbacks:
                return json_error("Unknown callback {} for device {} of type {}".format(fnName, uid, device_class_name),)
            fnInfo = device_class.callbacks[fnName]

            return self.device_callback_registration(device_class, device_class_name, uid, fnName, fnInfo, json_args, response_path)

    def device_callback_registration(self, device_class, device_name, uid, callbackName, callbackInfo, json_args, path):
        try:
            should_register = json.loads(json_args)
        except Exception as e:
            payload = ""
            if self.show_payload:
                payload = ". \n\tPayload was: " + repr(json_args)
            return json_error("Could not parse payload for {} callback registration of {} {} as JSON encoding a boolean: {}{}".format(callbackName, device_class, device_name, str(e), payload))

        if not isinstance(should_register, bool):
            #also support {"register": true/false} in addition to a top-level boolean
            if isinstance(should_register, dict) and 'register' in should_register:
                should_register = should_register['register']
            else:
                return json_error("Expected bool as parameter of callback registration, but got " + str(json_args))

        if should_register:
            success, callback_device = self.ensure_dev_exists(uid, device_class, device_name, self.mqttc)
            if not success:
                return callback_device

            callback_device.add_callback(callbackInfo.id, callbackInfo.fmt, callbackInfo.names, callbackInfo.symbols, callbackInfo.high_level_info)
            callback_device.register_callback(self, callbackInfo.id, path)

            logging.debug("Registered callback {} for device {} of type {}. Will publish messages to {}.".format(callbackName, uid, device_name, path))
        else:
            uid_ = self.parse_uid(uid)

            if uid_ not in self.ipcon.devices or not isinstance(self.ipcon.devices[uid_], device_class):
                reason = "no callbacks where registered for this device" if uid_ not in self.ipcon.devices else "a device of type {} with the same UID has callbacks registered".format(self.callback_devices[uid].device_class)
                logging.debug("Got callback deregistration request for device {} of type {}, but {}. Ignoring the request.".format(uid, device_name, reason))
                return None
            reg_found = self.ipcon.devices[uid_].deregister_callback(callbackInfo.id, path)
            if reg_found:
                logging.debug("Deregistered callback {} for device {} of type {}. Will stop publishing messages to {}.".format(callbackName, uid, device_name, path))

    def device_call(self, device, device_name, uid, fnName, fnInfo, json_args):
        logging.debug("Calling function {} for device {} of type {}.".format(fnName, uid, device_name))
        if len(json_args) > 0:
            try:
                obj = json.loads(json_args)
            except Exception as e:
                payload = ""
                if self.show_payload:
                    payload = ". \n\tPayload was: " + repr(json_args)
                return json_error("Could not parse payload for {} call of {} {} as JSON: {}{}".format(fnName, device_name, uid, str(e), payload))
        else:
            obj = {}
        args = []

        missing_args = []
        for a in fnInfo.arg_names:
            if a not in obj:
                missing_args.append(a)
            else:
                args.append(obj[a])

        if len(missing_args) > 0:
            return json_error("The arguments {} where missing for a call of {} of device {} of type {}.".format(str(missing_args), fnName, uid, device_name), dict([(name, None) for name in fnInfo.result_names]))

        reversed_symbols = [{v: k for k, v in d.items()}  for d in fnInfo.arg_symbols] # reverse dict to map from constant to it's value
        args = self.translate_symbols(reversed_symbols, args)

        type_error = MQTTBindings.type_check_args(args, fnInfo.arg_names, fnInfo.arg_types)
        if type_error is not None:
            return json_error("Call {} of {} {}: {}".format(fnName, device_name, uid, type_error),  dict([(name, None) for name in fnInfo.result_names]))

        if device.response_expected[fnInfo.id] != 1 and "_response_expected" in obj:
            re = obj["_response_expected"]
            if isinstance(re, bool):
                device.set_response_expected(fnInfo.id, re)
            else:
                logging.debug("Ignoring _response_expected, it was not of boolean type. (Call of {} of device {} of type {}.)".format(fnName, uid, device_name))

        response = self.handle_ipcon_exceptions(lambda i: i.send_request(device, fnInfo.id, tuple(args), fnInfo.payload_fmt, fnInfo.response_fmt), dict([(name, None) for name in fnInfo.result_names]), "(call of {} of {} {})".format(fnName, device_name, uid))
        if isinstance(response, dict) and "_ERROR" in response:
            return response

        logging.debug("Calling function {} for device {} of type {} succedded.".format(fnName, uid, device_name))
        if response != None:
            if len(fnInfo.result_names) == 1:
                response = (response,)

            if not self.no_symbolic_response:
                response = self.translate_symbols(fnInfo.result_symbols, response)

            d = dict(zip(fnInfo.result_names, response))
            if fnName == "get_identity" and "device_identifier" in d:
                dev_id = d["device_identifier"]
                d["_display_name"] = display_names[dev_id]
                if not self.no_symbolic_response:
                    d["device_identifier"] = mqtt_names[dev_id]
            response = json.dumps(d)
            return response

    def callback_function(self, mqtt_callback_device, callback_id, *args):
        names = mqtt_callback_device.callback_names[callback_id]
        paths = mqtt_callback_device.publish_paths[callback_id]
        symbols = mqtt_callback_device.callback_symbols[callback_id]
        if not self.no_symbolic_response:
            response = self.translate_symbols(symbols, args)
        else:
            response = args
        payload = json.dumps(dict(zip(names, response)))
        for path in paths:
            self.mqttc.publish(path, payload)


def parse_positive_int(value):
    value = int(value)

    if value < 0:
        raise ValueError()

    return value

parse_positive_int.__name__ = 'positive-int'

IPCON_HOST = 'localhost'
IPCON_PORT = 4223
IPCON_TIMEOUT = 2500
IPCON_AUTH_SECRET = ''
BROKER_HOST = 'localhost'
BROKER_PORT = 1883 # 8883 for TLS
GLOBAL_TOPIC_PREFIX = 'tinkerforge/'

bindings = None

def terminate(signal=None, frame=None):
    global bindings

    logging.debug("Disconnecting from brickd and mqtt broker.")

    if bindings is not None:
        try:
            bindings.ipcon.disconnect()
        except:
            pass

        bindings.mqttc.publish(bindings.global_prefix + 'callback/bindings/shutdown', 'null')
        bindings.mqttc.disconnect()
        bindings.mqttc.loop_stop()

    sys.exit(0)


def main():
    global bindings

    signal.signal(signal.SIGINT, terminate)
    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGQUIT, terminate)

    parser = argparse.ArgumentParser(description='Tinkerforge MQTT Bindings')
    parser.add_argument('--ipcon-host', dest='ipcon_host', type=str, default=IPCON_HOST,
                        help='hostname or IP address of Brick Daemon, WIFI or Ethernet Extension (default: {0})'.format(IPCON_HOST))
    parser.add_argument('--ipcon-port', dest='ipcon_port', type=int, default=IPCON_PORT,
                        help='port number of Brick Daemon, WIFI or Ethernet Extension (default: {0})'.format(IPCON_PORT))
    parser.add_argument('--ipcon-auth-secret', dest='ipcon_auth_secret', type=str, default=IPCON_AUTH_SECRET,
                        help='authentication secret of Brick Daemon, WIFI or Ethernet Extension (default: {0})'.format(IPCON_AUTH_SECRET))
    parser.add_argument('--ipcon-timeout', dest='ipcon_timeout', type=int, default=IPCON_TIMEOUT,
                        help='timeout in milliseconds for communication with Brick Daemon, WIFI or Ethernet Extension (default: {0})'.format(IPCON_TIMEOUT))
    parser.add_argument('--broker-host', dest='broker_host', type=str, default=BROKER_HOST,
                        help='hostname or IP address of MQTT broker (default: {0})'.format(BROKER_HOST))
    parser.add_argument('--broker-port', dest='broker_port', type=int, default=BROKER_PORT,
                        help='port number of MQTT broker (default: {0})'.format(BROKER_PORT))
    parser.add_argument('--broker-username', dest='broker_username', type=str, default=None,
                        help='username for the MQTT broker connection')
    parser.add_argument('--broker-password', dest='broker_password', type=str, default=None,
                        help='password for the MQTT broker connection')
    parser.add_argument('--broker-certificate', dest='broker_certificate', type=str, default=None,
                        help='Certificate Authority certificate file used for SSL/TLS connections')
    parser.add_argument('--broker-tls-insecure', dest='broker_tls_insecure', action='store_true',
                        help='disable verification of the server hostname in the server certificate for the MQTT broker connection')
    parser.add_argument('--global-topic-prefix', dest='global_topic_prefix', type=str, default=GLOBAL_TOPIC_PREFIX,
                        help='global MQTT topic prefix for this proxy instance (default: {0})'.format(GLOBAL_TOPIC_PREFIX))
    parser.add_argument('--debug', dest='debug', action='store_true', help='enable debug output')
    parser.add_argument('--no-symbolic-response', dest='no_symbolic_response', action='store_true', help='disable translation into string constants for responses')
    parser.add_argument('--show-payload', dest='show_payload', action='store_true', help='show received payload if JSON parsing fails')
    parser.add_argument('--init-file', dest='init_file', type=str, default=None,
                        help='file from where to load initial messages to publish')
    parser.add_argument('-v', '--version', action='version', version='%(prog)s 2.0.8')

    args = parser.parse_args(sys.argv[1:])

    if args.broker_username is None and args.broker_password is not None:
        parser.error('--broker-password cannot be used without --broker-username')

    global_topic_prefix = args.global_topic_prefix

    if len(global_topic_prefix) > 0 and not global_topic_prefix.endswith('/'):
        global_topic_prefix += '/'

    if args.init_file is not None:
        try:
            with open(args.init_file) as f:
                initial_config = json.load(f, object_pairs_hook=OrderedDict)
        except Exception as e:
            print("Could not read init file: {}".format(str(e)))
            sys.exit(ERROR_COULD_NOT_READ_INIT_FILE)
    else:
        initial_config = {}

    bindings = MQTTBindings(args.debug, args.no_symbolic_response, args.show_payload, global_topic_prefix, float(args.ipcon_timeout)/1000, args.broker_username, args.broker_password, args.broker_certificate, args.broker_tls_insecure)
    bindings.connect_to_broker(args.broker_host, args.broker_port)
    if 'pre_connect' in initial_config:
        bindings.run_config(initial_config['pre_connect'])
    bindings.connect_to_brickd(args.ipcon_host, args.ipcon_port, args.ipcon_auth_secret)
    if 'post_connect' in initial_config:
        bindings.run_config(initial_config['post_connect'])
    else:
        bindings.run_config(initial_config)
    bindings.run()

if __name__ == '__main__':
    main()
