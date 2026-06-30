import struct
import time
import machine

_MAGIC = 0xBEEF
_FMT = ">HHI"  # magic(2), counter(2), timestamp(4) = 8 bytes
_SIZE = 8

count = 0  # set by is_boot_looping(); readable externally for banner output


def _read():
    data = machine.RTC().memory()
    if len(data) < _SIZE:
        return None
    magic, ctr, ts = struct.unpack(_FMT, data[:_SIZE])
    if magic != _MAGIC:
        return None
    return ctr, ts


def _write(ctr, ts):
    machine.RTC().memory(struct.pack(_FMT, _MAGIC, ctr, ts))


def is_boot_looping() -> bool:
    global count
    now = time.time()
    result = _read()
    if result is None or (now - result[1]) > 60:
        count = 1
        _write(1, now)
        return False
    count = result[0] + 1
    _write(count, now)
    return count >= 3


def clear_counter() -> None:
    _write(0, 0)
