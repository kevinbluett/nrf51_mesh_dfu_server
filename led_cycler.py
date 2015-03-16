#!/usr/bin/env python

import os
import pexpect
import optparse
import time
from intelhex import IntelHex

# DFU Opcodes
class Commands:
    START_DFU = 1
    INITIALIZE_DFU = 2
    RECEIVE_FIRMWARE_IMAGE = 3
    VALIDATE_FIRMWARE_IMAGE = 4
    ACTIVATE_FIRMWARE_AND_RESET = 5
    SYSTEM_RESET = 6 

def convert_uint32_to_array(value):
    """ Convert a number into an array of 4 bytes (LSB). """
    return [
        (value >> 0 & 0xFF), 
        (value >> 8 & 0xFF), 
        (value >> 16 & 0xFF), 
        (value >> 24 & 0xFF)
    ] 

def convert_uint16_to_array(value):
    """ Convert a number into an array of 2 bytes (LSB). """
    return [
        (value >> 0 & 0xFF), 
        (value >> 8 & 0xFF)
    ] 

def convert_array_to_hex_string(arr):
    hex_str = ""
    for val in arr:
        if val > 255:
            raise Exception("Value is greater than it is possible to represent with one byte")
        hex_str += "%02x" % val
    return hex_str 


class BleDfuUploader(object):

    ctrlpt_handle = 0x000e
    ctrlpt_cccd_handle = 0x11
    data_handle = 0x0E

    def __init__(self, target_mac):
        self.ble_conn = pexpect.spawn("gatttool -b '%s' -t random --interactive" % target_mac)

    # Connect to peer device.
    def scan_and_connect(self):
        try:
            self.ble_conn.expect('\[LE\]>', timeout=10)
        except pexpect.TIMEOUT, e:
            print "timeout"
        
        self.ble_conn.sendline('connect')

        # try:
        #     res = self.ble_conn.expect('\[CON\].*>', timeout=10)
        # except pexpect.TIMEOUT, e:
        #     print "timeout"
    
    def _dfu_state_set(self, opcode):
        self.ble_conn.sendline('char-write-req 0x%02x %02x' % (self.ctrlpt_handle, opcode))        

        # Verify that command was successfully written
        try:
            res = self.ble_conn.expect('Characteristic value was written successfully', timeout=0.1)
        except pexpect.TIMEOUT, e:
            print "timeout"

    def _dfu_data_send(self, data_arr):
        hex_str = convert_array_to_hex_string(data_arr)
        self.ble_conn.sendline('char-write-req 0x%02x %s' % (self.data_handle, hex_str))        
        
        # Verify that data was successfully written
        try:
            res = self.ble_conn.expect('.* Characteristic value was written successfully', timeout=10)
        except pexpect.TIMEOUT, e:
            print "timeout"

    def _dfu_enable_cccd(self):
        cccd_enable_value_array_lsb = convert_uint16_to_array(0x0001)
        cccd_enable_value_hex_string = convert_array_to_hex_string(cccd_enable_value_array_lsb) 
        self.ble_conn.sendline('char-write-req 0x%02x %s' % (self.ctrlpt_cccd_handle, cccd_enable_value_hex_string))        

        # Verify that CCCD was successfully written
        try:
            res = self.ble_conn.expect('.* Characteristic value was written successfully', timeout=10)
        except pexpect.TIMEOUT, e:
            print "timeout"

    # Transmit the hex image to peer device.
    def dfu_send_image(self):
        # Sending 'START DFU' Command
        while True:
            self._dfu_state_set(01)
            time.sleep(0.110)
            self._dfu_state_set(00)
            time.sleep(0.110)

    # Disconnect from peer device if not done already and clean up. 
    def disconnect(self):
        self.ble_conn.sendline('exit')
        self.ble_conn.close()


if __name__ == '__main__':
    try:
        parser = optparse.OptionParser(usage='%prog -f <hex_file> -a <dfu_target_address>\n\nExample:\n\tdfu.py -f blinky.hex -a cd:e3:4a:47:1c:e4',
                                       version='0.1')

        parser.add_option('-a', '--address',
                  action='store',
                  dest="address",
                  type="string",
                  default=None,
                  help='DFU target address. (Can be found by running "hcitool lescan")'
                  )

        options, args = parser.parse_args()

    except Exception, e:
        print e
        print "For help use --help"
        sys.exit(2)

    ble_dfu = BleDfuUploader(options.address.upper())
    
    # Connect to peer device.
    ble_dfu.scan_and_connect()
    
    # Transmit the hex image to peer device.
    ble_dfu.dfu_send_image()
    
    # wait a second to be able to recieve the disconnect event from peer device.
    time.sleep(1)
    
    # Disconnect from peer device if not done already and clean up. 
    ble_dfu.disconnect()