#!/usr/bin/python3 -u
# -*- coding: utf-8 -*-

# takes ACSensor data from one or more VEBus dbus services, and converts it into a nice looking
# PV Inverter dbus service.

from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib
import dbus
import dbus.service
import inspect
import logging
import argparse
import sys
import os

# Victron packages
sys.path.insert(1, os.path.join(os.path.dirname(__file__), './ext/velib_python'))
from vedbus import VeDbusService, VeDbusItemImport

softwareVersion = '1.31'

# Dictionary containing all acDevices exported to dbus
acDevices = {}

# Dict, key is the servicename, Value is the VeDbusItemImport object, monitoring /AcSensor/Count
sensorcounts = {}

# One VE.Bus AC Sensor, contains links to the four D-Bus items
class AcSensor(object):
	def __init__(self, sensor_voltage=None, sensor_power=None, sensor_current=None, sensor_energycounter=None):
		self.dbusobjects = {
			'voltage': sensor_voltage,
			'power':  sensor_power,
			'current': sensor_current,
			'energycounter': sensor_energycounter}

	def __getitem__(self, key):
		return self.dbusobjects[key]

	def set_eventcallback(self, neweventcallback):
		for key, dbusitem in self.dbusobjects.items():
			if dbusitem:
				dbusitem.eventCallback = neweventcallback

class SystemBus(dbus.bus.BusConnection):
	def __new__(cls):
		return dbus.bus.BusConnection.__new__(cls, dbus.bus.BusConnection.TYPE_SYSTEM)

class SessionBus(dbus.bus.BusConnection):
	def __new__(cls):
		return dbus.bus.BusConnection.__new__(cls, dbus.bus.BusConnection.TYPE_SESSION)

def dbusconnection():
	return SessionBus() if 'DBUS_SESSION_BUS_ADDRESS' in os.environ else SystemBus()

# Class representing one PV Inverter. I chose a more generic name, since in future it
# will probably also become something else, such as a grid connection, or wind inverter
class AcDevice(object):
	def __init__(self, position):
		# Dictionary containing the AC Sensors per phase. This is the source of the data
		self._acSensors = {'L1': [], 'L2': [], 'L3': []}

		# Type and position (numbering is equal to numbering in VE.Bus Assistant):
		self._names = {0: 'PV Inverter on input 1', 1: 'PV Inverter on output', 2: 'PV Inverter on input 2'}
		self._name = position
		self._dbusService = None

	def __str__(self):
		return self._names[self._name] + ' containing ' + \
			str(len(self._acSensors['L1'])) + ' AC-sensors on L1, ' + \
			str(len(self._acSensors['L2'])) + ' AC-sensors on L2, ' + \
			str(len(self._acSensors['L3'])) + ' AC-sensors on L3'

	# add_ac_sensor function is called to add dbusitems that represent power for a certain phase
	def add_ac_sensor(self, acsensor, phase):
		acsensor.set_eventcallback(self.value_has_changed)
		self._acSensors[phase].append(acsensor)

	def value_has_changed(self, dbusName, dbusObjectPath, changes):
		# decouple, and process update in the mainloop
		GLib.idle_add(self.update_values)

	# iterates through all sensor dbusItems, and recalculates our values. Adds objects to exported
	# dbus values if necessary.
	def update_values(self):

		if not self._dbusService:
			return

		totals = {'I': 0, 'P': 0, 'E': 0}

		for phase in ['L1', 'L2', 'L3']:
			pre = '/Ac/' + phase

			if len(self._acSensors[phase]) == 0:
				if (pre + '/Power') in self._dbusService:
					self._dbusService[pre + '/Power'] = None
					self._dbusService[pre + '/Energy/Forward'] = None
					self._dbusService[pre + '/Voltage'] = None
					self._dbusService[pre + '/Current'] = None
			else:
				phaseTotals = {'I': 0, 'P': 0, 'E': 0}
				for o in self._acSensors[phase]:
					phaseTotals['I'] += float(o['current'].get_value() or 0)
					phaseTotals['P'] += float(o['power'].get_value() or 0)
					phaseTotals['E'] += float(o['energycounter'].get_value() or 0)
					voltage = float(o['voltage'].get_value() or 0) # just take the last voltage

				if (pre + '/Power') not in self._dbusService:
					# This phase hasn't been added yet, adding it now

					self._dbusService.add_path(pre + '/Voltage', voltage, gettextcallback=self.gettextforV)
					self._dbusService.add_path(pre + '/Current', phaseTotals['I'], gettextcallback=self.gettextforA)
					self._dbusService.add_path(pre + '/Power', phaseTotals['P'], gettextcallback=self.gettextforW)
					self._dbusService.add_path(pre + '/Energy/Forward', phaseTotals['E'], gettextcallback=self.gettextforkWh)
				else:
					self._dbusService[pre + '/Voltage'] = voltage
					self._dbusService[pre + '/Current'] = phaseTotals['I']
					self._dbusService[pre + '/Power'] = phaseTotals['P']
					self._dbusService[pre + '/Energy/Forward'] = phaseTotals['E']

				totals['I'] += phaseTotals['I']
				totals['P'] += phaseTotals['P']
				totals['E'] += phaseTotals['E']

				#logging.debug(
				#	self._names[self._name] + '. Phase ' + phase + ' recalculated: %0.2fV,  %0.2fA, %0.4fW and %0.4f kWh' %
				#	(voltage,  phaseTotals['I'],  phaseTotals['P'],  phaseTotals['E']))

			# TODO, why doesn't the application crash on an exception? I want it to crash, also on exceptions
			# in threads.
			#raise Exception ("exit Exception!")

		if '/Ac/Current' not in self._dbusService:
			self._dbusService.add_path('/Ac/Current', totals['I'], gettextcallback=self.gettextforA)
			self._dbusService.add_path('/Ac/Power', totals['P'], gettextcallback=self.gettextforW)
			self._dbusService.add_path('/Ac/Energy/Forward', totals['E'], gettextcallback=self.gettextforkWh)
		else:
			self._dbusService['/Ac/Current'] = totals['I']
			self._dbusService['/Ac/Power'] =  totals['P']
			self._dbusService['/Ac/Energy/Forward'] = totals['E']

	# Call this function after you have added AC sensors to this class. Code will check if we have any,
	# and if yes, add ourselves to the dbus.
	def update_dbus_service(self):
		if (len(self._acSensors['L1']) > 0 or len(self._acSensors['L2']) > 0 or
			len(self._acSensors['L3']) > 0):

			if self._dbusService is None:

				pf = {0: 'input1', 1: 'output', 2: 'input2'}
				self._dbusService = VeDbusService('com.victronenergy.pvinverter.vebusacsensor_' + pf[self._name], dbusconnection())
				#, self._dbusConn)

				self._dbusService.add_path('/Position', self._name, description=None, gettextcallback=self.gettextforposition)

				# Create the mandatory objects, as per victron dbus api document
				self._dbusService.add_path('/Mgmt/ProcessName', __file__)
				self._dbusService.add_path('/Mgmt/ProcessVersion', softwareVersion)
				self._dbusService.add_path('/Mgmt/Connection', 'AC Sensor on VE.Bus device')
				self._dbusService.add_path('/DeviceInstance', int(self._name) + 10)
				self._dbusService.add_path('/ProductId', 0xA141)
				self._dbusService.add_path('/ProductName', self._names[self._name])
				self._dbusService.add_path('/Connected', 1)

				logging.info('Added to D-Bus: ' + self.__str__())

			self.update_values()

	# Apparantly some service from which we imported AC Sensors has gone offline. Remove those sensors
	# from our repo.
	def remove_ac_sensors_imported_from(self, serviceBeingRemoved):
		logging.debug(
			'%s: Checking if we have sensors from %s, and removing them' %
			(self._names[self._name], serviceBeingRemoved))

		for phase in ['L1', 'L2', 'L3']:
			self._acSensors[phase][:] = [x for x in self._acSensors[phase] if not x['power'].serviceName == serviceBeingRemoved]

		if self._dbusService is None:
			return

		if (not self._acSensors['L1'] and not self._acSensors['L2'] and
			not self._acSensors['L3']):
			# No sensors left for us, clean up

			self._dbusService.__del__()  # explicitly call __del__(), instead of waiting for gc
			self._dbusService = None

			logging.info("Removed from D-Bus: %s" % self.__str__())
		else:
			# Still some sensors left for us, update values
			self.update_values()

	def gettextforkWh(self, path, value):
		return ("%.3FkWh" % (float(value) / 1000.0))

	def gettextforW(self, path, value):
		return ("%.0FW" % (float(value)))

	def gettextforV(self, path, value):
		return ("%.0FV" % (float(value)))

	def gettextforA(self, path, value):
		return ("%.0FA" % (float(value)))

	def gettextforposition(self, path, value):
		return self._names[value]


def dbus_name_owner_changed(name, oldOwner, newOwner):
	# decouple, and process in main loop
	GLib.idle_add(process_name_owner_changed, name, oldOwner, newOwner)


def process_name_owner_changed(name, oldOwner, newOwner):
	logging.debug('D-Bus name owner changed. Name: %s, oldOwner: %s, newOwner: %s' % (name, oldOwner, newOwner))

	if newOwner != '':
		scan_dbus_service(name)
	else:
		for a, b in acDevices.items():
			b.remove_ac_sensors_imported_from(name)


# Function is called when a new vebus service is found, and also when the count changes.
def countchanged(servicename, path, changes, skipremove=False):

	acSensorCount = sensorcounts[servicename].get_value()

	logging.info(
		"New service added, or sensorcount was changed on an existing service. Count for %s is now %s" %
		(servicename, acSensorCount))

	# First remove the service
	if not skipremove:
		for a, b in acDevices.items():
			b.remove_ac_sensors_imported_from(servicename)

	# Note that the mk2 service will first come on to the D-Bus with an invalidated sensor count,
	# and only after a couple of seconds (while communicating with the Multi), it will set it to 0
	# or something else.

	if acSensorCount is None:
		return

	# loop through all the ac current sensors in the system, and add to right acDevice object
	for x in range(0, acSensorCount):

		# TODO 1: put a signal monitor on the location and the phase?
		sensor_path = '/AcSensor/%s' % x
		location = VeDbusItemImport(dbusConn, servicename,
				sensor_path + '/Location', createsignal=False).get_value()
		phase = VeDbusItemImport(dbusConn, servicename,
				sensor_path + '/Phase', createsignal=False).get_value()
		if location is None or phase is None:
			# We get here when the vebus service is removed from the D-Bus shortly after creation.
			continue
		phase = 'L%s' % (phase + 1)

		logging.info('AC Sensor on %s, location: %s, phase: %s' % (sensor_path, location, phase))

		if location not in acDevices:
			raise Exception('Unexpected AC Current Sensor Location: %s' % location)

		newacsensor = AcSensor(
			sensor_power=VeDbusItemImport(dbusConn, servicename, sensor_path + '/Power'),
			sensor_energycounter=VeDbusItemImport(dbusConn, servicename, sensor_path + '/Energy'),
			sensor_voltage=VeDbusItemImport(dbusConn, servicename, sensor_path + '/Voltage'),
			sensor_current=VeDbusItemImport(dbusConn, servicename, sensor_path + '/Current'))

		acDevices[location].add_ac_sensor(newacsensor, phase)

	for a, b in acDevices.items():
		b.update_dbus_service()


# Scans the given dbus service to see if it contains anything interesting for us.
def scan_dbus_service(serviceName):
	# Not for us? Exit.
	if serviceName.split('.')[0:3] != ['com', 'victronenergy', 'vebus']:
		return

	logging.info("Found: %s, checking for valid AC Current Sensors" % serviceName)

	global sensorcounts
	sensorcounts[serviceName] = VeDbusItemImport(dbusConn, serviceName, '/AcSensor/Count', countchanged)

	countchanged(serviceName, None, None, skipremove=True)


def main():
	global acDevices
	global dbusItems
	global dbusConn
	global dbusConnName

	# Argument parsing
	parser = argparse.ArgumentParser(
		description='Converts readings from AC-Sensors connected to a VE.Bus device in a pvinverter ' +
					'D-Bus service.'
	)

	parser.add_argument("-d", "--debug", help="set logging level to debug",
					action="store_true")

	args = parser.parse_args()

	# Init logging
	logging.basicConfig(level=(logging.DEBUG if args.debug else logging.INFO))
	logging.info("-------- dbus-pvinverter-vebus, v" + softwareVersion + " is starting up --------")
	logLevel = {0: 'NOTSET', 10: 'DEBUG', 20: 'INFO', 30: 'WARNING', 40: 'ERROR'}
	logging.info('Loglevel set to ' + logLevel[logging.getLogger().getEffectiveLevel()])

	# Have a mainloop, so we can send/receive asynchronous calls to and from dbus
	DBusGMainLoop(set_as_default=True)

	# For a PC, connect to the SessionBus
	# For a CCGX, connect to the SystemBus
	dbusConn = dbus.SessionBus() if 'DBUS_SESSION_BUS_ADDRESS' in os.environ else dbus.SystemBus()

	# subscribe to NameOwnerChange for bus connect / disconnect events.
	dbusConn.add_signal_receiver(dbus_name_owner_changed, signal_name='NameOwnerChanged')

	# Add the acDevices, and use same numbering as in VE.Bus
	acDevices[0] = AcDevice(0)
	acDevices[1] = AcDevice(1)
	acDevices[2] = AcDevice(2)

	logging.info('Searching dbus for vebus devices...')
	serviceNames = dbusConn.list_names()
	for serviceName in serviceNames:
		scan_dbus_service(serviceName)
	logging.info('Finished search for vebus devices')

	# Start and run the mainloop
	logging.info("Starting mainloop, responding only on events")
	mainloop = GLib.MainLoop()
	mainloop.run()

if __name__ == "__main__":
	main()
