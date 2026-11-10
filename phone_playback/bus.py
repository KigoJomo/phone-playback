import ctypes as C
import os
import json

from .kde_install import find_bin

BIN = str(find_bin())
_dll_directory = os.add_dll_directory(BIN)
d = C.CDLL(os.path.join(BIN, "dbus-1-3.dll"))


def bind(name, restype, *args):
    f = getattr(d, name)
    f.restype = restype
    f.argtypes = list(args)
    return f


ptr = C.c_void_p
string = C.c_char_p
integer = C.c_int
bind("dbus_threads_init_default", integer)()
bus_get = bind("dbus_bus_get_private", ptr, integer, ptr)
is_connected = bind("dbus_connection_get_is_connected", integer, ptr)
connection_close = bind("dbus_connection_close", None, ptr)
connection_unref = bind("dbus_connection_unref", None, ptr)
exit_on_disconnect = bind("dbus_connection_set_exit_on_disconnect", None, ptr, integer)
new = bind("dbus_message_new_method_call", ptr, string, string, string, string)
send = bind("dbus_connection_send_with_reply_and_block", ptr, ptr, ptr, integer, ptr)
unref = bind("dbus_message_unref", None, ptr)
init = bind("dbus_message_iter_init", integer, ptr, ptr)
init_append = bind("dbus_message_iter_init_append", None, ptr, ptr)
append = bind("dbus_message_iter_append_basic", integer, ptr, integer, ptr)
open_container = bind("dbus_message_iter_open_container", integer, ptr, integer, string, ptr)
close_container = bind("dbus_message_iter_close_container", integer, ptr, ptr)
argtype = bind("dbus_message_iter_get_arg_type", integer, ptr)
basic = bind("dbus_message_iter_get_basic", None, ptr, ptr)
recurse = bind("dbus_message_iter_recurse", None, ptr, ptr)
nextarg = bind("dbus_message_iter_next", integer, ptr)
get_error = bind("dbus_message_get_error_name", string, ptr)
conn = None


def connection():
    global conn
    if conn and not is_connected(conn):
        connection_close(conn)
        connection_unref(conn)
        conn = None
    if not conn:
        conn = bus_get(0, None)
        if not conn:
            raise RuntimeError("Start KDE Connect to connect to its session bus.")
        exit_on_disconnect(conn, 0)
    return conn


def parse(it):
    result = []
    while t := argtype(it):
        if t in (ord("s"), ord("o"), ord("g")):
            v = string()
            basic(it, C.byref(v))
            v = v.value.decode("utf-8") if v.value else ""
        elif t in (ord("b"), ord("i"), ord("u")):
            v = integer()
            basic(it, C.byref(v))
            v = v.value
        elif t in (ord("a"), ord("v"), ord("r"), ord("e")):
            child = C.create_string_buffer(128)
            recurse(it, child)
            v = parse(child)
            if t == ord("v"):
                v = v[0] if v else None
        else:
            v = f"<type {t}>"
        result.append(v)
        if not nextarg(it):
            break
    return result


def call(path, interface, method, args=(), destination="org.kde.kdeconnect"):
    active_connection = connection()
    msg = new(destination.encode(), path.encode(), interface.encode(), method.encode())
    try:
        it = C.create_string_buffer(128)
        init_append(msg, it)
        for value in args:
            target = it
            variant = isinstance(value, tuple)
            if variant:
                value = value[0]
                target = C.create_string_buffer(128)
                signature = b"i" if isinstance(value, int) else b"s"
                if not open_container(it, ord("v"), signature, target):
                    raise MemoryError()
            if isinstance(value, int):
                v = integer(value)
                t = ord("i")
            else:
                v = string(value.encode())
                t = ord("s")
            if not append(target, t, C.byref(v)):
                raise MemoryError()
            if variant and not close_container(it, target):
                raise MemoryError()
        reply = send(active_connection, msg, 2500, None)
        if not reply:
            raise RuntimeError("D-Bus call timed out or failed")
        try:
            it = C.create_string_buffer(128)
            init(reply, it)
            value = parse(it)
            if err := get_error(reply):
                raise RuntimeError(f"{err.decode()}: {value}")
            return value
        finally:
            unref(reply)
    finally:
        unref(msg)


if __name__ == "__main__":
    import sys

    print(json.dumps(call(*sys.argv[1:4], args=sys.argv[4:]), ensure_ascii=True, indent=2))
