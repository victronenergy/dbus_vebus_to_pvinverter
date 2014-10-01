dbus_vebus_to_pvinverter
========================

This code runs as a service on the CCGX. It searches the D-Bus for VE.Bus devices that have an AC Current Sensor installed. The VE.Bus product (Multi, Quattro), and the service that takes care of the VE.Bus protocol on the CCGX (mk2dbus), both act as a gateway. The Multi reads the analog value from the AC Current Sensor, and makes that information available on the VE.Bus network. Then mk2dbus service on the CCGX reads that data from the VE.Bus network, and makes it available on the D-Bus, in a raw format.

And then, at the end of this chain, is this service, dbus_vebus_to_pvinverter, which takes the data from the ve.bus service (via D-Bus) and republishes it on the D-Bus as a com.victronenergy.pvinverter service.

More graphically, this is how it looks: 

    AC Current Sensor (hardware)
        |
        > Multi (hardware)
            |
            > VE.Bus (network)
                |
                > CCGX (the VE.Bus comm. ports)

And from there, now in the Color Control:

    VE.Bus comm. ports
        |
        > mk2dbus (service)
            |
            > D-Bus (com.victronenergy.vebus)
                |
                > dbus_vebus_to_pvinverter (service)
                    |
                    > D-Bus (com.victronenergy.pvinverter)
