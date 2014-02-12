#!/usr/bin/env python
# -*- coding: utf-8 -*-

#!/usr/bin/python -u

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

# our own packages
from vedbus import VeDbusItemExport

softwareVersion = '1.0'

# Dictionary containing all objects exported to dbus
dbusObjects = {}

def handleDbusNameOwnerChanged(name, oldOwner, newOwner):
        #print('handlerNameOwnerChanged name=%s oldOwner=%s newOwner=%s' % (name, oldOwner, newOwner))
        #decouple, and process in main loop
        #idle_add(processNameOwnerChanged, name, oldOwner, newOwner)
        pass

def processNameOwnerChanged(name, oldOwner, newOwner):
        #print 'processingNameOwnerChanged'
        pass

def addDbusOject(dictionary, dbusConn, path, value, isValid = True, description = '', callback = None):
        dbusObjects[path] = VeDbusItemExport(dbusConn, path, value, isValid, description, callback)

def update():
	print 'time'
	print 'value now: ' + str(dbusObjects['/AcSensor/0/Power'].GetValue())
	dbusObjects['/AcSensor/0/Power'].SetValue(dbusObjects['/AcSensor/0/Power'].GetValue() + 1)
	gobject.timeout_add(1000, update)

print __file__ + " starting up"

# Have a mainloop, so we can send/receive asynchronous calls to and from dbus
DBusGMainLoop(set_as_default=True)

# For a PC, connect to the SessionBus
# For a CCGX, connect to the SystemBus
dbusConn = dbus.SystemBus() if (platform.machine() == 'armv7l') else dbus.SessionBus()

# Register ourserves on the dbus, fake that we are a Quattro
name = dbus.service.BusName("com.victronenergy.vebus", dbusConn)

# subscribe to NameOwnerChange for bus connect / disconnect events.
dbusConn.add_signal_receiver(handleDbusNameOwnerChanged, signal_name='NameOwnerChanged')

# Eerst de count opvragen
# dan allemaal ophalen

# Create the management objects, as specified in the ccgx dbus-api document
addDbusOject(dbusObjects, dbusConn, '/Mgmt/ProcessName', __file__)
addDbusOject(dbusObjects, dbusConn, '/Mgmt/ProcessVersion', softwareVersion + ' running on Python ' + platform.python_version())
addDbusOject(dbusObjects, dbusConn, '/Mgmt/Connection', 'Data taken from mk2dbus')

# Create the mandatory objects
addDbusOject(dbusObjects, dbusConn, '/DeviceInstance', 0)
addDbusOject(dbusObjects, dbusConn, '/ProductId', 0)
addDbusOject(dbusObjects, dbusConn, '/ProductName', 'PV Inverter on Output')
addDbusOject(dbusObjects, dbusConn, '/FirmwareVersion', 0)
addDbusOject(dbusObjects, dbusConn, '/HardwareVersion', 0)
addDbusOject(dbusObjects, dbusConn, '/Connected', 0)

# Create all the objects that we want to export to the dbus
addDbusOject(dbusObjects, dbusConn, '/AcSensor/Count', 2)
addDbusOject(dbusObjects, dbusConn, '/AcSensor/0/Location', 0)
addDbusOject(dbusObjects, dbusConn, '/AcSensor/0/Phase', 0)
addDbusOject(dbusObjects, dbusConn, '/AcSensor/0/Power', 9000)

addDbusOject(dbusObjects, dbusConn, '/AcSensor/1/Location', 1)
addDbusOject(dbusObjects, dbusConn, '/AcSensor/1/Phase', 2)
addDbusOject(dbusObjects, dbusConn, '/AcSensor/1/Power', 9112)

addDbusOject(dbusObjects, dbusConn, '/AcSensor/2/Location', 1)
addDbusOject(dbusObjects, dbusConn, '/AcSensor/2/Phase', 0)
addDbusOject(dbusObjects, dbusConn, '/AcSensor/2/Power', 9210)

# Start and run the mainloop


gobject.timeout_add(1000, update)

print 'Connected to dbus, and switching over to gobject.MainLoop() (= event based)'
mainloop = gobject.MainLoop()
mainloop.run()




