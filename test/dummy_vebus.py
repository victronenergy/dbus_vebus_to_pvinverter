#!/usr/bin/env python

## @package conversions
# takes data from the dbus, does calculations with it, and puts it back on
from dbus.mainloop.glib import DBusGMainLoop
import gobject
from gobject import idle_add
import dbus
import dbus.service
import inspect
import platform
from threading import Timer
import argparse
import logging
import sys
import os

# our own packages
sys.path.insert(1, os.path.join(os.path.dirname(__file__), '../ext/velib_python'))
from vedbus import VeDbusService

dbusservice = None

def update():
	p = '/Dc/V'
	logging.info("value now for %s is %s, incrementing..." % (p, dbusservice[p]))
	dbusservice[p] += 1
	gobject.timeout_add(1000, update)


# Argument parsing
parser = argparse.ArgumentParser(
	description='dbusMonitor.py demo run'
)

parser.add_argument("-n", "--name", help="the D-Bus service you want me to claim",
				type=str, default="com.victronenergy.vebus.ttyO1")

parser.add_argument("-i", "--deviceinstance", help="the device instance you want me to be",
				type=str, default="0")

parser.add_argument("-d", "--debug", help="set logging level to debug",
				action="store_true")

args = parser.parse_args()

# Init logging
logging.basicConfig(level=(logging.DEBUG if args.debug else logging.INFO))
logging.info(__file__ + " is starting up")
logLevel = {0: 'NOTSET', 10: 'DEBUG', 20: 'INFO', 30: 'WARNING', 40: 'ERROR'}
logging.info('Loglevel set to ' + logLevel[logging.getLogger().getEffectiveLevel()])

# Have a mainloop, so we can send/receive asynchronous calls to and from dbus
DBusGMainLoop(set_as_default=True)

dbusservice = VeDbusService(args.name)

logging.info("using device instance %s" % args.deviceinstance)

# Create the management objects, as specified in the ccgx dbus-api document
dbusservice.add_path('/Management/ProcessName', __file__)
dbusservice.add_path('/Management/ProcessVersion', 'Unkown version, and running on Python ' + platform.python_version())
dbusservice.add_path('/Management/Connection', 'Data taken from mk2dbus')

# Create the mandatory objects
dbusservice.add_path('/DeviceInstance', args.deviceinstance)
dbusservice.add_path('/ProductId', 0)
dbusservice.add_path('/ProductName', 'PV Inverter on Output')
dbusservice.add_path('/FirmwareVersion', 0)
dbusservice.add_path('/HardwareVersion', 0)
dbusservice.add_path('/Connected', 1)

# Create all the objects that we want to export to the dbus
dbusservice.add_path('/AcSensor/Count', 2)
dbusservice.add_path('/AcSensor/0/Location', 0)
dbusservice.add_path('/AcSensor/0/Phase', 0)
dbusservice.add_path('/AcSensor/0/Power', 1000)
dbusservice.add_path('/AcSensor/0/Energy', 100)
dbusservice.add_path('/AcSensor/0/Current', 10)
dbusservice.add_path('/AcSensor/0/Voltage', 240)

dbusservice.add_path('/AcSensor/1/Location', 0)
dbusservice.add_path('/AcSensor/1/Phase', 0)
dbusservice.add_path('/AcSensor/1/Power', 1500)
dbusservice.add_path('/AcSensor/1/Energy', 150)
dbusservice.add_path('/AcSensor/1/Current', 15)
dbusservice.add_path('/AcSensor/1/Voltage', 220)

dbusservice.add_path('/AcSensor/2/Location', 1)
dbusservice.add_path('/AcSensor/2/Phase', 0)
dbusservice.add_path('/AcSensor/2/Power', 9210)
dbusservice.add_path('/AcSensor/2/Energy', 30)

dbusservice.add_path('/Dc/V', 12.4)

dbusservice.add_path('/Devices/0/Version', 'testversie')


gobject.timeout_add(1000, update)

print 'Connected to dbus, and switching over to gobject.MainLoop() (= event based)'
mainloop = gobject.MainLoop()
mainloop.run()




