#!/usr/bin/python -u
# -*- coding: utf-8 -*-

## @package conversions
# takes ACSensor data from one or more VEBus dbus services, and converts it into a nice looking
# PV Inverter dbus service.

# TODO:
# - (optional) when sensors change from location, update ourselves. Or just exit, and let us be restarted.
#   See TODO 1 in the code.
# - Perhaps add the DBus items used in GUI item AC Totals: /AC/Power, /AC/Current and /AC/Energy/Forward. As
#   qwacs has them as well. Or change QML that QML does the calculation.

from dbus.mainloop.glib import DBusGMainLoop
import gobject
from gobject import idle_add
import dbus
import dbus.service
import inspect
import platform
import logging
import argparse

# our own packages
from vedbus import VeDbusItemExport, VeDbusItemImport, VEDBUS_INVALID

softwareVersion = '1.10'

# Dictionary containing all acDevices exported to dbus
acDevices = {}


# Class representing one PV Inverter. I chose a more generic name, since in future it
# will probably also become something else, such as a grid connection, or wind inverter
class AcDevice(object):
	def __init__(self, position):
		# Dictionary containing the AC Sensors per phase. This is the source of the data
		self._acSensorsPower = {'L1': [], 'L2': [], 'L3': []}
		self._acSensorsEnergy = {'L1': [], 'L2': [], 'L3': []}

		# Dictionary containing the dbusItems exporting the data to the dbus. So this is
		# the destination of the data
		self._dbusItems = {}

		# Type and position (numbering is equal to numbering in VE.Bus Assistant):
		self._names = {0: 'PV Inverter on input 1', 1: 'PV Inverter on output', 2: 'PV Inverter on input 2'}
		self._name = position

		# keep a connection to dbus for the whole time. Only add & remove the dbusName when we find / lose
		# sensors. I agree that it would sound logically to remove or not even start connection when not
		# necessary. But couldn't find a way without causing the mainloop to stop: self._dbusConn.close()
		# stops the mainloop even though this process has multiple busconnections. Another solution might be
		# to stick with one connection, and publish multiple names. API docs hint that that should be
		# possible.
		self._dbusConn = dbus.SystemBus(True) if (platform.machine() == 'armv7l') else dbus.SessionBus(True)
		self._dbusName = None

	def __str__(self):
		return self._names[self._name] + ' containing ' + \
			str(len(self._acSensorsPower['L1'])) + ' AC-sensors on L1, ' + \
			str(len(self._acSensorsPower['L2'])) + ' AC-sensors on L2, ' + \
			str(len(self._acSensorsPower['L3'])) + ' AC-sensors on L3'

	# add_ac_sensor_power function is called to add dbusitems that represent power for a certain phase
	def add_ac_sensor_power(self, dbusItem, phase='L1'):
		dbusItem.eventCallback = self.handler_value_changes
		self._acSensorsPower[phase].append(dbusItem)

	# add_ac_sensor_energy function is called to add dbusitems that represent power for a certain phase
	def add_ac_sensor_energy(self, dbusItem, phase='L1'):
		dbusItem.eventCallback = self.handler_value_changes
		self._acSensorsEnergy[phase].append(dbusItem)

	def handler_value_changes(self, dbusName, dbusObjectPath, changes):
		# decouple, and process update in the mainloop
		idle_add(self.update_values)

	# iterates through all sensor dbusItems, and recalculates our values. Adds objects to exported
	# dbus values if necessary.
	# called from handler_value_changes
	def update_values(self):

		for phase in ['L1', 'L2', 'L3']:
			pre = '/AC/' + phase

			if len(self._acSensorsPower[phase]) == 0:
				if (pre + '/Power') in self._dbusItems:
					self._dbusItems[pre + '/Power'].local_set_value(0, isValid=False)
					self._dbusItems[pre + '/Energy/Forward'].local_set_value(0, isValid=False)
					# TODO: remove them as well? Since we also don't export at startup when no sensors found
			else:
				totalPower = 0
				for o in self._acSensorsPower[phase]:
					totalPower += float(o.GetValue())

				totalEnergy = 0
				for o in self._acSensorsEnergy[phase]:
					totalEnergy += float(o.GetValue())

				if (pre + '/Power') not in self._dbusItems:
					# Create all the objects that we want to export to the dbus
					# The quby ac-sensor dbus service also has some more: /NumberOfPhases and (per phase)
					# Energy/Reverse.
					self._dbusItems[pre + '/Power'] = VeDbusItemExport(self._dbusConn,
						pre + '/Power', totalPower, isValid=True, gettextcallback=self.gettextW)

					self._dbusItems[pre + '/Energy/Forward'] = VeDbusItemExport(self._dbusConn,
						pre + '/Energy/Forward', totalEnergy, isValid=True, gettextcallback=self.gettextkWh)

				else:
					self._dbusItems[pre + '/Power'].SetValue(totalPower)
					self._dbusItems[pre + '/Energy/Forward'].SetValue(totalEnergy)

				logging.debug(self._names[self._name] + '. Phase ' + phase +
					' recalculated: %0.4f W and %0.4f kWh' % (totalPower, totalEnergy))

			# TODO, why doesn't the application crash on an exception? I want it to crash, also on exceptions
			# in threads.
			#raise Exception ("exit Exception!")

	# Call this function after you have added AC sensors to this class. Code will check if we have any,
	# and if yes, add ourselves to the dbus.
	def update_dbus_service(self):
		if (len(self._acSensorsPower['L1']) > 0 or len(self._acSensorsPower['L2']) > 0 or
			len(self._acSensorsPower['L3']) > 0):

			if self._dbusName is None:

				pf = {0: 'input1', 1: 'output', 2: 'input2'}
				self._dbusName = dbus.service.BusName("com.victronenergy.pvinverter.vebusacsensor_" + pf[self._name],
														self._dbusConn)

				self._dbusItems['/Position'] = VeDbusItemExport(self._dbusConn,
					'/Position', self._name, gettextcallback=self.gettextposition)

				# Create the mandatory objects, as per victron dbus api document
				self._dbusItems['/Mgmt/ProcessName'] = VeDbusItemExport(self._dbusConn,
					'/Mgmt/ProcessName', __file__)

				self._dbusItems['/Mgmt/ProcessVersion'] = VeDbusItemExport(self._dbusConn,
					'/Mgmt/ProcessVersion', softwareVersion + ' running on Python ' + platform.python_version())

				self._dbusItems['/Mgmt/Connection'] = VeDbusItemExport(self._dbusConn,
					'/Mgmt/Connection', 'AC Sensor on VE.Bus ')

				self._dbusItems['/DeviceInstance'] = VeDbusItemExport(self._dbusConn,
					'/DeviceInstance', 0)

				self._dbusItems['/ProductId'] = VeDbusItemExport(self._dbusConn,
					'/ProductId', 0)

				self._dbusItems['/ProductName'] = VeDbusItemExport(self._dbusConn, '/ProductName',
					self._names[self._name])

				self._dbusItems['/Connected'] = VeDbusItemExport(self._dbusConn,
					'/Connected', 1)

				logging.info('Added to D-Bus: ' + self.__str__())

			self.update_values()

	# scan all ac sensor items we have, and see if we need to remove something.
	def remove_service_imported_from(self, serviceName):

		for phase in ['L1', 'L2', 'L3']:
			for o in self._acSensorsPower[phase]:
				if o.serviceName == serviceName:
					self._acSensorsPower[phase].remove(o)

			for o in self._acSensorsEnergy[phase]:
				if o.serviceName == serviceName:
					self._acSensorsEnergy[phase].remove(o)

		if (
			not self._acSensorsPower['L1'] and not self._acSensorsPower['L2'] and
			not self._acSensorsPower['L3'] and self._dbusName is not None):

			# There are no sensors left: take ourselves off the dbus
			r = []
			for k, o in self._dbusItems.iteritems():
				o.remove_from_connection()
				r.append(k)

			# can't remove items during above iteration, so do it afterwards
			for k in r:
				del self._dbusItems[k]

			# Explicitly call __del__ since we don't want to wait for the garbage collector.
			# we want to go offline sofort
			self._dbusName.__del__()
			self._dbusName = None

			logging.info(self.__str__() + ' has removed itself from dbus')

		self.update_values()

	def gettextkWh(self, path, value):
		return ("%.3FkWh" % (float(value) / 1000.0))

	def gettextW(self, path, value):
		return ("%.0FW" % (float(value)))

	def gettextposition(self, path, value):
		return self._names[value]


def dbus_name_owner_changed(name, oldOwner, newOwner):
	#decouple, and process in main loop
	idle_add(process_name_owner_changed, name, oldOwner, newOwner)


def process_name_owner_changed(name, oldOwner, newOwner):
	logging.debug('D-Bus name owner changed. Name: %s, oldOwner: %s, newOwner: %s' % (name, oldOwner, newOwner))

	if newOwner != '':
		scan_dbus_service(name)
	else:
		for a, b in acDevices.iteritems():
			b.remove_service_imported_from(name)


# Scans the given dbus service to see if it contains anything interesting for us.
def scan_dbus_service(serviceName):
	# Not for us? Exit.
	if serviceName.split('.')[0:3] != ['com', 'victronenergy', 'vebus']:
		return

	logging.info("Found: %s, checking for valid AC Current Sensors" % serviceName)

	# TODO 1: put a signal monitor on the acSensorCount, for when someone changes the config in the Multi.
	acSensorCount = VeDbusItemImport(dbusConn, serviceName, '/AcSensor/Count').GetValue()

	if acSensorCount == VEDBUS_INVALID:
		logging.info("Sensor count is invalid: mk2 service is still reading data from vebus. Retry in 5 secs.")
		gobject.timeout_add(5000, scan_dbus_service, serviceName)
		return

	logging.info("Number of AC Current Sensors found: " + str(acSensorCount))

	# loop through all the ac current sensors in the system, and add to right acDevice object
	for x in range(0, acSensorCount):

		# TODO 1: put a signal monitor on the location and the phase?
		location = VeDbusItemImport(dbusConn, serviceName,
				'/AcSensor/' + str(x) + '/Location').GetValue()
		phase = 'L' + str(VeDbusItemImport(dbusConn, serviceName,
				'/AcSensor/' + str(x) + '/Phase').GetValue() + 1)

		logging.info('AC Sensor on /AcSensor/' + str(x) + ', location: ' + str(location) +
			', phase: ' + phase)

		if location not in acDevices:
			raise Exception('Unexpected AC Current Sensor Location: ' + str(location))

		# Monitor Power and the kWh counter. Note that the kWh counter restarts at 0 on when the Multi
		# powers up. And there is more available on dbus (voltage & current), but we are not interested
		# in that, so leave it.
		acDevices[location].add_ac_sensor_power(VeDbusItemImport(
			dbusConn, serviceName, '/AcSensor/' + str(x) + '/Power'), phase)

		acDevices[location].add_ac_sensor_energy(VeDbusItemImport(
			dbusConn, serviceName, '/AcSensor/' + str(x) + '/Energy'), phase)

	for a, b in acDevices.iteritems():
		b.update_dbus_service()


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
	dbusConn = dbus.SystemBus() if (platform.machine() == 'armv7l') else dbus.SessionBus()

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
	mainloop = gobject.MainLoop()
	mainloop.run()

if __name__ == "__main__":
	main()
