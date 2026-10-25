"""Private test-only NetworkManager facade on an explicitly supplied Unix bus."""

import json
import sys

import dbus
from dbus import service
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib

DBusGMainLoop(set_as_default=True)
connection = dbus.bus.BusConnection(sys.argv[1])
loop = GLib.MainLoop()
configuration = {"cost": 2, "state": 70, "format": "uint", "delay": 0}
calls = []


def filtered(_connection, message):
    if message.get_interface() == "org.freedesktop.DBus.Properties":
        calls.append(
            {
                "method": message.get_member(),
                "auto_start": bool(message.get_auto_start()),
                "arguments": [str(value) for value in message.get_args_list()],
            }
        )
        del calls[:-32]
    return dbus.lowlevel.HANDLER_RESULT_NOT_YET_HANDLED


connection.add_message_filter(filtered)


class Manager(service.Object):
    @service.method(
        "org.freedesktop.DBus.Properties",
        in_signature="ss",
        out_signature="v",
        async_callbacks=("respond", "fail"),
    )
    def Get(self, interface, property, respond, fail):
        if interface != "org.freedesktop.NetworkManager" or property not in {"Metered", "State"}:
            fail(dbus.DBusException("Unsupported property"))
            return
        value = configuration["cost" if property == "Metered" else "state"]
        if configuration["format"] == "string":
            result = dbus.String("not a network flag")
        elif configuration["format"] == "signed":
            result = dbus.Int32(value)
        else:
            result = dbus.UInt32(value)

        def reply():
            try:
                respond(result)
            except dbus.DBusException:
                pass  # A timed-out probe has already closed its private socket.
            return False

        if configuration["delay"]:
            GLib.timeout_add(configuration["delay"], reply)
        else:
            reply()


name = service.BusName("org.freedesktop.NetworkManager", bus=connection, do_not_queue=True)
manager = Manager(name, "/org/freedesktop/NetworkManager")


def control(_stream, _condition):
    line = sys.stdin.readline()
    if not line:
        loop.quit()
        return False
    command = json.loads(line)
    if command == "stats":
        print(json.dumps({"calls": calls}), flush=True)
    elif command == "quit":
        loop.quit()
        return False
    else:
        configuration.update(command)
        calls.clear()
        print('{"ok": true}', flush=True)
    return True


GLib.io_add_watch(sys.stdin, GLib.IO_IN | GLib.IO_HUP, control)
print('{"ready": true}', flush=True)
loop.run()
connection.close()
