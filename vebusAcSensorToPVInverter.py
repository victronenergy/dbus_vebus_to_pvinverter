#!/usr/bin/env python
# -*- coding: utf-8 -*-

## @package conversions
# takes ACSensor data from the VEBus dbus service, and converts it into a nice looking
# PV Inverter dbus service.

from dbus.mainloop.glib import DBusGMainLoop
import gobject
from gobject import idle_add
import dbus
import dbus.service
import inspect
import platform
import pprint
import logging

# our own packages
from vedbus import VeDbusItemExport, VeDbusItemImport

logging.basicConfig(level=logging.DEBUG)

softwareVersion = '1.0'

# Dictionary containing all acDevices exported to dbus
acDevices = {}

# Dictionary containing all dbusItems that belong to the main dbus service
dbusItems = {}

# Class representing one PV Inverter. I chose a more generic name, since in future it
# will probably also become something else, # such as a grid connection, or wind inverter
class AcDevice(object):
	def __init__(self, position):
		# Dictionary containing the AC Sensors per phase. This is the source of the data
		self._acSensors = {'L1' : [], 'L2' : [], 'L3' : []}

		# Dictionary containing the dbusItems exporting the data to the dbus. So this is
		# the destination of the data
		self._dbusItems = {}

		# Type and position (numbering is equal to numbering in VE.Bus Assistant):
		self._positions = {0: 'PV Inverter on input 1', 1: 'PV Inverter on output', 2: 'PV Inverter on input 2'}
		self._position = position
		self._dbusConn = None
		self._dbusName = None

	def __str__(self):
		return self._positions[self._position] + ' containing ' + str(len(self._acSensors['L1'])) + ' AC-sensors on L1, ' + \
																  str(len(self._acSensors['L2'])) + ' AC-sensors on L2, ' + \
																  str(len(self._acSensors['L3'])) + ' AC-sensors on L3'

	def add_ac_sensor(self, dbusItem, phase = 'L1'):
		dbusItem.SetEventCallback(self.handler_value_changes)
		self._acSensors[phase].append(dbusItem)

	def handler_value_changes(self, dbusName, dbusObjectPath, changes):
		# decouple, and process update in the mainloop
		idle_add(self.update_values)

	def update_values(self):
		logging.debug(self._positions[self._position] + ': update_values')

		for phase in ['L1', 'L2', 'L3']:
			totalPower = 0
			for o in self._acSensors[phase]:
				totalPower += float(o.GetValue())

			self._dbusItems['/Ac/' + phase + '/P'].SetValue(totalPower)

			# TODO, why doesn't the application crash on an exception? I want it to crash, also on exceptions
			# in threads.
			#raise Exception ("exit Exception!")

	def update_dbus_service(self):
		# TODO, if self._dbusConn != None, remove ourselfs from the bus? Or what do we want to do?

		if len(self._acSensors['L1']) > 0 or len(self._acSensors['L2']) > 0 or len(self._acSensors['L3']) > 0:
			self._dbusConn = dbus.SystemBus(True) if (platform.machine() == 'armv7l') else dbus.SessionBus(True)
			self._dbusName = dbus.service.BusName("com.victronenergy.pvinverter.input1", self._dbusConn)

			# Create the mandatory objects
			add_dbus_object(self._dbusItems, self._dbusConn, '/DeviceInstance', 0)
			add_dbus_object(self._dbusItems, self._dbusConn, '/ProductId', 0)
			add_dbus_object(self._dbusItems, self._dbusConn, '/ProductName', 'PV Inverter on input 1')
			add_dbus_object(self._dbusItems, self._dbusConn, '/FirmwareVersion', 0)
			add_dbus_object(self._dbusItems, self._dbusConn, '/HardwareVersion', 0)
			add_dbus_object(self._dbusItems, self._dbusConn, '/Connected', 1)

			# Create all the objects that we want to export to the dbus
			add_dbus_object(self._dbusItems, self._dbusConn, '/Ac/L1/P', 0, False)
			add_dbus_object(self._dbusItems, self._dbusConn, '/Ac/L2/P', 0, False)
			add_dbus_object(self._dbusItems, self._dbusConn, '/Ac/L3/P', 0, False)

			logging.debug(self.__str__() + ' added to dbus')

def dbus_name_owner_changed(name, oldOwner, newOwner):
	#decouple, and process in main loop
	idle_add(process_name_owner_changed, name, oldOwner, newOwner)

def process_name_owner_changed(name, oldOwner, newOwner):
	pass
	#print 'TODO some service came, changed name, or left the dbus. we dont do anything, but we should!'
	#todo

def add_dbus_object(dictionary, dbusConn, path, value, isValid = True, description = '', callback = None):
		dictionary[path] = VeDbusItemExport(dbusConn, path, value, isValid, description, callback)

def main(argv):
	global acDevices
	global dbusItems

	logging.info (__file__ + ", version " + softwareVersion + " is starting up")

	# Have a mainloop, so we can send/receive asynchronous calls to and from dbus
	DBusGMainLoop(set_as_default=True)

	# For a PC, connect to the SessionBus
	# For a CCGX, connect to the SystemBus
	dbusConn = dbus.SystemBus() if (platform.machine() == 'armv7l') else dbus.SessionBus()

	# Register ourserves on the dbus
	dbusConnName = dbus.service.BusName("com.victronenergy.conversions", dbusConn)

	# subscribe to NameOwnerChange for bus connect / disconnect events.
	dbusConn.add_signal_receiver(dbus_name_owner_changed, signal_name='NameOwnerChanged')

	# Create the management objects, as specified in the ccgx dbus-api document
	add_dbus_object(dbusItems, dbusConn, '/Mgmt/ProcessName', __file__)
	add_dbus_object(dbusItems, dbusConn, '/Mgmt/ProcessVersion', softwareVersion + ' running on Python ' + platform.python_version())
	add_dbus_object(dbusItems, dbusConn, '/Mgmt/Connection', 'not relevant')

	# Add the acDevices, and use same numbering as in VE.Bus
	acDevices[0] = AcDevice(0)
	acDevices[1] = AcDevice(1)
	acDevices[2] = AcDevice(2)

	logging.info('Starting search for services (vebus, solar chargers, etc.)...')

	serviceNames = dbusConn.list_names()

	# TODO: make the code also respond well to dynamic changes
	# option1: move all code below to a separate place, reset acSensorsOnInput etc to empty dictionaries
	# option1: just exit on a change, and let the script restart, perhaps preferred!

	# scan all victron dbus connection for known services
	for serviceName in serviceNames:
		if serviceName.startswith('com.victronenergy.vebus'):
			logging.info("Found: %s, checking for valid AC Current Sensors" % serviceName)

			acSensorCount = VeDbusItemImport(dbusConn, serviceName, '/AcSensor/Count').GetValue()
			logging.info("Number of AC Current Sensors found: " + str(acSensorCount))

			# loop through all the ac current sensors in the system, and put them in the right dictionary
			for x in range(0, acSensorCount):

				location = VeDbusItemImport(dbusConn, serviceName, '/AcSensor/' + str(x) + '/Location').GetValue()
				phase = 'L' + str(VeDbusItemImport(dbusConn, serviceName, '/AcSensor/' + str(x) + '/Phase').GetValue() + 1)
				logging.info('Found AC Sensor on /AcSensor/' + str(x) + ', location: ' + str(location) + ', phase: ' + phase)

				if location not in acDevices:
					raise Exception('Unexpected AC Current Sensor Location: ' + str(location))

				acDevices[location].add_ac_sensor(VeDbusItemImport(dbusConn, serviceName, '/AcSensor/' + str(x) + '/Power'), phase)

	logging.info('Finished search for services')

	logging.info('Putting PV Inverters on dbus...')
	for a, b in acDevices.iteritems():
		b.update_dbus_service()
	logging.info('Finished putting PV Inverters on dbus')

	# Start and run the mainloop
	logging.info("Starting mainloop, from now on events only")
	mainloop = gobject.MainLoop()
	mainloop.run()

# main(sys.argv[1:])
main("")
