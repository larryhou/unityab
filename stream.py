#!/usr/bin/env python3

import binascii
import io
import os
import struct
from typing import BinaryIO


class FileStream(object):
    def __init__(self, data: bytes = None, file_path: str = None):
        if self.open(file_path):
            pass
        elif data:
            self.fill(data)
        else:
            self.__buffer = io.BytesIO()
        self.endian = '>'
        self.__read_limit = 0
        self.__read_count = 0

    def fill(self, data: bytes):
        assert data
        self.__buffer = io.BytesIO(data)

    def open(self, file_path: str) -> bool:
        if file_path and os.path.exists(file_path):
            self.__buffer: BinaryIO = open(file_path, 'rb')
            return True
        return False

    def close(self):
        self.__buffer.close()

    @property
    def position(self) -> int:
        return self.__buffer.tell()

    @position.setter
    def position(self, position: int):
        self.seek(position, os.SEEK_SET)

    @property
    def length(self) -> int:
        position = self.__buffer.tell()
        self.__buffer.seek(0, os.SEEK_END)
        length = self.__buffer.tell()
        self.__buffer.seek(position)
        return length

    @property
    def bytes_available(self):
        return self.length - self.position

    def lock(self, size):
        self.__read_limit = size + 4
        self.__read_count = 0

    def unlock(self):
        self.__read_limit = 0

    def read(self, n: int = 1) -> bytes:
        self.__read_count += n
        if 0 < self.__read_limit <= self.__read_count:
            raise Exception('expect {} bytes'.format(self.__read_limit))
        char = self.__buffer.read(n)
        if not char: raise RuntimeError('expect more data')
        return char

    def align(self, size: int = 4):
        mode = self.position % size
        if mode > 0:
            self.seek(size - mode, os.SEEK_CUR)

    def seek(self, offset: int, whence: int = os.SEEK_SET):
        self.__buffer.seek(offset, whence)

    def append(self, data: bytes):
        position = self.__buffer.tell()
        self.seek(0, os.SEEK_END)
        self.__buffer.write(data)
        self.__buffer.seek(position)

    # write
    def write(self, data: bytes):
        self.__buffer.write(data)

    def write_boolean(self, v: bool):
        self.__buffer.write(bytes(1 if v else 0))

    def write_sbyte(self, v: int):
        self.write(struct.pack('b', v))

    def write_ubyte(self, v: int):
        self.write(struct.pack('B', v))

    def write_uint16(self, v: int):
        self.write(struct.pack('{}H'.format(self.endian), v))

    def write_sint16(self, v: int):
        self.write(struct.pack('{}h'.format(self.endian), v))

    def write_ushort(self, v: int):
        self.write_uint16(v)

    def write_short(self, v: int):
        self.write_sint16(v)

    def write_uint32(self, v: int):
        self.write(struct.pack('{}I'.format(self.endian), v))

    def write_sint32(self, v: int):
        self.write(struct.pack('{}i'.format(self.endian), v))

    def write_uint64(self, v: int):
        self.write(struct.pack('{}Q'.format(self.endian), v))

    def write_sint64(self, v: int):
        self.write(struct.pack('{}q'.format(self.endian), v))

    def write_float(self, v: float):
        self.write(struct.pack('{}f'.format(self.endian), v))

    def write_double(self, v: float):
        self.write(struct.pack('{}d'.format(self.endian), v))

    def write_hex(self, v: str):
        self.write(binascii.unhexlify(v))

    def write_sqlit_sint32(self, value):
        mask = (1 << 32) - 1
        self.write_sqlit_uint32(value & mask)

    def write_sqlit_uint32(self, value):
        assert value < (1 << 32)
        if value <= 240:
            self.write_ubyte(value)
            return
        if value <= 2287:
            self.write_ubyte((value - 240) / 256 + 241)
            self.write_ubyte((value - 240) % 256)
            return
        if value <= 67823:
            self.write_ubyte(249)
            self.write_ubyte((value - 2288) / 256)
            self.write_ubyte((value - 2288) % 256)
            return
        if value <= 16777215:
            self.write_ubyte(250)
            self.write_ubyte(value >> 0 & 0xFF)
            self.write_ubyte(value >> 8 & 0xFF)
            self.write_ubyte(value >> 16 & 0xFF)
            return
        self.write_ubyte(251)
        self.write_ubyte(value >> 0 & 0xFF)
        self.write_ubyte(value >> 8 & 0xFF)
        self.write_ubyte(value >> 16 & 0xFF)
        self.write_ubyte(value >> 24 & 0xFF)

    def write_compact_sint32(self, value):
        mask = (1 << 32) - 1
        self.write_compact_uint32(value & mask)

    def write_compact_uint32(self, value):
        assert value < (1 << 32)
        while value > 0:
            byte = value & 0x7F
            value >>= 7
            if value > 0: byte |= (1 << 7)
            self.write_ubyte(byte)

    def write_string(self, s: str, encoding: str = 'utf-8'):
        self.write(s.encode(encoding=encoding))

    # read
    def read_boolean(self) -> bool:
        return struct.unpack('?', self.__buffer.read(1))[0]

    def read_sint8(self) -> int:
        return struct.unpack('b', self.__buffer.read(1))[0]

    def read_uint8(self) -> int:
        return self.read(1)[0]

    def read_short(self) -> int:
        return struct.unpack('{}h'.format(self.endian), self.read(2))[0]

    def read_ushort(self) -> int:
        return struct.unpack('{}H'.format(self.endian), self.read(2))[0]

    def read_sint16(self) -> int:
        return self.read_short()

    def read_uint16(self) -> int:
        return self.read_ushort()

    def read_sint32(self) -> int:
        return struct.unpack('{}i'.format(self.endian), self.read(4))[0]

    def read_uint32(self) -> int:
        return struct.unpack('{}I'.format(self.endian), self.read(4))[0]

    def read_uint64(self) -> int:
        return struct.unpack('{}Q'.format(self.endian), self.read(8))[0]

    def read_sint64(self) -> int:
        return struct.unpack('{}q'.format(self.endian), self.read(8))[0]

    def read_float(self) -> float:
        return struct.unpack('{}f'.format(self.endian), self.read(4))[0]

    def read_double(self) -> float:
        return struct.unpack('{}d'.format(self.endian), self.read(8))[0]

    def read_hex(self, length: int) -> int:
        data = self.read(length)
        return binascii.hexlify(data).decode('ascii')

    def read_sqlit_sint32(self) -> int:
        data = struct.pack('>I', self.read_sqlit_uint32())
        return struct.unpack('>i', data)[0]

    def read_sqlit_uint32(self) -> int:
        byte0 = self.read_uint8()
        if byte0 < 241: return byte0
        byte1 = self.read_uint8()
        if byte0 < 249:
            return 240 + 256 * (byte0 - 241) + byte1
        byte2 = self.read_uint8()
        if byte0 == 249:
            return 2288 + 256 * byte1 + byte2
        byte3 = self.read_uint8()
        if byte0 == 250:
            return byte1 << 0 | byte2 << 8 | byte3 << 16
        byte4 = self.read_uint8()
        if byte0 >= 251:
            return byte1 << 0 | byte2 << 8 | byte3 << 16 | byte4 << 24

    def read_compact_sint32(self) -> int:
        data = struct.pack('>I', self.read_compact_uint32())
        return struct.unpack('>i', data)[0]

    def read_compact_uint32(self) -> int:
        value, shift = 0, 0
        while True:
            byte = self.read_uint8()
            value |= (byte & 0x7F) << shift
            if byte & 0x80 == 0: break
            shift += 7
        assert value < (1 << 32)
        return value

    def read_string(self, length: int = 0, encoding='utf-8') -> str:
        assert length >= 0
        if not length:
            string = b''
            while True:
                char = self.read(1)
                if char == b'\x00': break
                string += char
        else:
            string = self.read(length)  # type: bytes
        if not encoding:
            return string.decode(encoding)
        else:
            return None if not string else string.decode(encoding=encoding)

    def read_address(self) -> bytes:
        return self.read(4)

    @staticmethod
    def reverse(v: int) -> int:
        if v >= 0:
            if v < (1 << 32):
                data = struct.pack('>I', v)
                return struct.unpack('<I', data)[0]
            else:
                data = struct.pack('>Q', v)
                return struct.unpack('<Q', data)[0]
        else:
            if v >= -(1 << 31):
                data = struct.pack('>i', v)
                return struct.unpack('<i', data)[0]
            else:
                data = struct.pack('>q', v)
                return struct.unpack('<q', data)[0]
