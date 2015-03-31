#!/usr/bin/env python

import os
import pexpect
import optparse
import time
from ihextools import iHex
import numpy as np

# DFU Opcodes
class Commands:
    MESH_NOP = 0
    MESH_CONNECTION_REQUEST = 1
    MESH_CONNECTION_REQUEST_ACK = 2
    MESH_DISCONNECT_SERVER = 3
    MESH_DISCONNECT_CLIENT =4
    MESH_REQUEST_STATUS = 5
    MESH_REQUEST_STATUS_ACK = 6
    MESH_START_IMAGE_TRANSFER = 7
    MESH_START_IMAGE_TRANSFER_ACK = 8
    MESH_DATA_IMAGE_PACKET = 9
    MESH_DATA_IMAGE_PACKET_ACK = 10
    MESH_DATA_IMAGE_REQUEST = 11
    MESH_IMAGE_TRANSFER_SUCCESS = 12
    MESH_IMAGE_TRANSFER_SUCCESS_ACK = 13
    MESH_IMAGE_ACTIVATE = 14
    MESH_IMAGE_ACTIVATE_ACK = 15
    MESH_CLIENT_ERROR = 16

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

def convert_array_to_hex_string(arr, rv = True):
    hex_str = ""
    for val in arr:
        if val > 255:
            raise Exception("Value is greater than it is possible to represent with one byte")
        if rv:
            hex_str = ("%02x" % val) + hex_str
        else:
            hex_str += ("%02x" % val)
    return hex_str


class BleDfuUploader(object):

    ctrlpt_handle = 0x0012
    ctrlpt_cccd_handle = 0x11
    data_handle = 0x0E
    hexfile_path = ""

    def __init__(self, target_mac):
        self.ble_conn = pexpect.spawn("gatttool -b '%s' -t random --interactive" % target_mac)

    # Connect to peer device.
    def scan_and_connect(self):
        try:
            self.ble_conn.expect('\[LE\]>', timeout=15)
        except pexpect.TIMEOUT, e:
            print "timeout"
        
        self.ble_conn.sendline('connect')

        try:
            res = self.ble_conn.expect('Connection successful', timeout=10)
        except pexpect.TIMEOUT, e:
            print "timeout"
    
    def _get_handle_state(self, handle):
        # print 'char-read-hnd 0x%04x' % (self.ctrlpt_handle)
        self.ble_conn.sendline('char-read-hnd 0x%04x' % (self.ctrlpt_handle))        

        # Verify that command was successfully written
        try:
            res = self.ble_conn.expect('Characteristic value/descriptor: .*? \r', timeout=0.5)
            return int(self.ble_conn.after[33:].replace(' ', ''), 16)
        except pexpect.TIMEOUT, e:
            print "timeout"
            return -1

    def _dfu_state_set(self, opcode):
        print 'char-write-req 0x%04x %02x' % (self.ctrlpt_handle, opcode)
        self.ble_conn.sendline('char-write-req 0x%04x %02x' % (self.ctrlpt_handle, opcode))        

        # Verify that command was successfully written
        try:
            res = self.ble_conn.expect('Characteristic value was written successfully', timeout=0.1)
        except pexpect.TIMEOUT, e:
            print "timeout"

    def _dfu_cmd_set(self, opcode, data = '1DFF2AAA3BBB4CCC5DDD6EEE7FFF8AAA', addr = 0x0AD3):
        print "Current Data Hex ",data
        print "Opcode ", opcode
        opcode = opcode << 3;
        print hex(opcode)
        line = 'char-write-req 0x%04x %02x%04x%s' % (self.ctrlpt_handle, opcode, addr, data)
        print line
        self.ble_conn.sendline(line)

        # Verify that command was successfully written
        try:
            res = self.ble_conn.expect('Characteristic value was written successfully', timeout=2)
            print 'Success'
        except pexpect.TIMEOUT, e:
            print "timeout"

    def _dfu_image_info(self, image_size,addr = 0x0AD3):
        opcode = Commands.MESH_START_IMAGE_TRANSFER
        print opcode
        opcode = opcode << 3;
        print "Opcode", hex(opcode)
        print "Image array: ", convert_uint32_to_array(image_size)
        line = 'char-write-req 0x%04x %02x%04x%s' % (self.ctrlpt_handle, opcode, addr, convert_array_to_hex_string(convert_uint32_to_array(image_size)))
        print line
        self.ble_conn.sendline(line)

        # Verify that command was successfully written
        try:
            res = self.ble_conn.expect('Characteristic value was written successfully', timeout=2)
            print 'Success'
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

    def get_state(self, handle=0x0012):
        state = self._get_handle_state(handle)
        if state != 0:
            state = (state >> (195))
        return state       

    # Transmit the hex image to peer device.
    def dfu_send_image(self):
        # Sending 'START DFU' 
        ih = iHex()
        ih.load_ihex('mesh.hex')
        byte_array = ih.get_binary()

        image_size = len(byte_array)
        print "Image hex file size: ", image_size

        while True:
            time.sleep(0.110)
            state = self.get_state()
            print "state "+str(state) 

            if state == Commands.MESH_NOP:
                time.sleep(0.110)
                print "Starting DFU cycle"
                self._dfu_cmd_set(Commands.MESH_CONNECTION_REQUEST)
            elif state == Commands.MESH_CONNECTION_REQUEST:
                print "Awaiting mesh request acknowledgement..."
                time.sleep(2)
            elif state == Commands.MESH_CONNECTION_REQUEST_ACK:
                print "Mesh connection request acknowledgement recieved"
                self._dfu_image_info(image_size)
                time.sleep(3)
            elif state == Commands.MESH_START_IMAGE_TRANSFER_ACK:
                print "Starting mesh firmware image transfer..."
                chunk = 1
                total_chunks = image_size/16
                for i in range(0, image_size, 16):
                    data_to_send = byte_array[i:i + 16]
                    self._dfu_cmd_set(Commands.MESH_DATA_IMAGE_PACKET, data=convert_array_to_hex_string(data_to_send, rv=False))

                    print "Chunk # ", chunk, " of ", total_chunks
                    ack_state = 0
                    time.sleep(5)
                    while ack_state != Commands.MESH_DATA_IMAGE_PACKET_ACK:
                        ack_state = self.get_state()
                        time.sleep(0.005)
                    print "Chunk ACK # ", chunk, " of ", total_chunks
                    chunk += 1
                print "Sending mesh image activation"
                # check image for validation and running
                self._dfu_cmd_set(Commands.MESH_IMAGE_ACTIVATE)
                exit(1)
            else:
                print "ERROR ERROR ERROR ERROR"
                exit(1)

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