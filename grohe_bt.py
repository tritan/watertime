from time import sleep
from gi.repository import GLib
import pydbus
import base64
import hmac
import time
import logging
import sys

water_uuid = '00001705-0000-1000-8000-00805f9b34fb'
heartbeat_uuid = '00001706-0000-1000-8000-00805f9b34fb'

# DBus object paths
bluez_service = 'org.bluez'
adapter_path = '/org/bluez/hci0'

class GroheBT(object):
    def __init__(self):
        self.device = None
        
    def connect(self, address, user_id, pre_shared_key):
        # Store parameters
        self.user_id = user_id
        self.key = base64.b64decode(pre_shared_key)
        
        
        # setup dbus
        self.bus = pydbus.SystemBus()
        self.mngr = self.bus.get(bluez_service, '/')
        adapter = self.bus.get(bluez_service, adapter_path) 
        device_path = f"{adapter_path}/dev_{address.replace(':', '_')}"
        device = self.bus.get(bluez_service, device_path)
        self.device = device

        self._connect()
        
    def _connect(self):
        # connection can be a bit fiddly, try a few times
        tries = 15
        while (True):
            try:
                self.device.Connect()
                timeout = 20
                while not self.device.ServicesResolved:
                    sleep(0.5)
                    timeout -= 1
                    if timeout == 0:
                        logging.warning("timeout resolving GATT services, retrying...")
                        tries -= 1
                        if not tries: raise Exception("too many retries")
                        sleep(5)
                        self.device.Disconnect()
                        break
                if not self.device.ServicesResolved:
                    continue
                # Characteristic DBus information
                water_path = self.get_characteristic_path(self.device._path, water_uuid)
                heartbeat_path = self.get_characteristic_path(self.device._path, heartbeat_uuid)
                self.water_object = self.bus.get(bluez_service, water_path)
                self.heartbeat_object = self.bus.get(bluez_service, heartbeat_path)
                break
            except Exception as e:
                logging.warning("got exception %s, retrying..." %e)
                tries -= 1
                if not tries:
                    logging.critical("Retries failed")
                    sys.exit(1)
                sleep(5)

        
    def dispense_water(self, amount, taste):
        # construct the message
        message = "%s:%d:%d:%d" %(self.user_id, time.time(), amount, taste)
        digest = hmac.new(self.key, msg=message.encode('iso-8859-1'),
                          digestmod='sha256').digest()
        digest64 = base64.b64encode(digest)
        message = "%s:%s" %(message, digest64.decode('iso-8859-1'))

        # send it
        tries = 2
        while (True):
            try:
                self.water_object.WriteValue(message.encode('iso-8859-1'), {})
                break
            except Exception as e:
                tries -= 1
                if tries:
                    logging.warning("Message failed, retrying...")
                    self.device.Disconnect()
                    self._connect()
                    continue
                else:
                    logging.critical("Retries failed")
                    sys.exit(1)

    def heartbeat(self):
        tries = 5
        while (True):
            try:
                return bytes(self.heartbeat_object.ReadValue({})).decode('iso-8859-1')
            except Exception as e:
                tries -= 1
                if (tries):
                    logging.warning("Hearbeat failed. Reconnecting...")
                    self.device.Disconnect()
                    self._connect()
                    continue
                else:
                    logging.critical("Retries failed")
                    sys.exit(1)


    def get_characteristic_path(self, dev_path, uuid):
        """Look up DBus path for characteristic UUID"""
        mng_objs = self.mngr.GetManagedObjects()
        for path in mng_objs:
            chr_uuid = mng_objs[path].get('org.bluez.GattCharacteristic1', {}).get('UUID')
            if path.startswith(dev_path) and chr_uuid == uuid.casefold():
                return path

    def __del__(self):
        if (self.device):
            self.device.Disconnect()

# mainloop = GLib.MainLoop()

# try:
#     mainloop.run()
# except KeyboardInterrupt:
#     mainloop.quit()
#     btn_a.StopNotify()
#     device.Disconnect()
