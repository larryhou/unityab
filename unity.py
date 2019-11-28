#!/usr/bin/env python3

import argparse
import enum
import sys

import lz4.block

from stream import FileStream
from typing import List

UINT64_MAX = (1 << 64) - 1

class CompressionType(enum.IntEnum):
    NONE, LZMA, LZ4, LZ4HC, LZHAM = range(5)

class ArchiveFlags(object):
    CompressTypeMask = (1 << 6) - 1
    BlocksAndDirectoryInfoCombined = 1 << 6
    BlocksInfoAtTheEnd = 1 << 7
    OldWebPluginCompatibility = 1 << 8

class StorageBlockFlags(object):
    BlockCompressionTypeMask = (1 << 6) - 1
    BlockStreamed = 1 << 6

class NodeFlags(object):
    Default = 0
    Directory = 0x1
    Deleted = 0x2
    SerializedFile = 0x4;

class UnitySignature(object):
    UnityFS = 'UnityFS'
    UnityWeb = 'UnityWeb'
    UnityRaw = 'UnityRaw'
    UnityArchive = 'UnityArchive'

class Node(object):
    def __init__(self):
        self.offset: int = 0
        self.size: int = 0
        self.flags: int = 0
        self.path: str = ''

    @property
    def is_directory(self) -> bool:
        return (self.flags & NodeFlags.Directory) != 0

    @property
    def is_serialized_file(self) -> bool:
        return (self.flags & NodeFlags.SerializedFile) != 0

    def __repr__(self):
        return '[Node] {{offset={}, size={}, flags={:08x}, path={}}}'.format(self.offset, self.size, self.flags, self.path)

    def decode(self, fs: FileStream):
        self.offset = fs.read_uint64()
        self.size = fs.read_uint64()
        self.flags = fs.read_uint32()
        self.path = fs.read_string()

class DirectoryInfo(object):
    def __init__(self):
        self.nodes: List[Node] = []

    def decode(self, fs: FileStream):
        for _ in range(fs.read_uint32()):
            node = Node()
            node.decode(fs)
            self.nodes.append(node)

class StorageBlock(object):
    def __init__(self):
        self.uncompressed_size: int = 0
        self.compressed_size: int = 0
        self.flags: int = 0

    def decode(self, fs: FileStream):
        self.uncompressed_size = fs.read_uint32()
        self.compressed_size = fs.read_uint32()
        self.flags = fs.read_uint16()

    @property
    def compression_type(self) -> CompressionType:
        return CompressionType(self.flags & StorageBlockFlags.BlockCompressionTypeMask)

    @property
    def is_streamed(self) -> bool:
        return (self.flags & StorageBlockFlags.BlockStreamed) != 0

    def __repr__(self):
        return '[StorageBlock] {{uncompressed_size={}, compressed_size={}, flags={:08x}}}'.format(self.uncompressed_size, self.compressed_size, self.flags)

class BlocksInfo(object):
    def __init__(self):
        self.uncompressed_data_hash: bytes = b''
        self.blocks: List[StorageBlock] = []

    def decode(self, fs: FileStream):
        self.uncompressed_data_hash = fs.read(16)
        for _ in range(fs.read_uint32()):
            block = StorageBlock()
            block.decode(fs)
            self.blocks.append(block)

class ArchiveStorageHeader(object):
    def __init__(self):
        self.signature: str = ''
        self.version: int = 0
        self.unity_web_bundle_version = ''
        self.unity_web_minimum_revision = ''
        self.size: int = 0
        self.header_size: int = 0
        self.compressed_blocks_info_size: int = 0
        self.uncompressed_blocks_info_size: int = 0
        self.flags: int = 0

    @property
    def compression_type(self) -> CompressionType:
        return CompressionType(self.flags & ArchiveFlags.CompressTypeMask)

    @property
    def has_blocks_at_the_end(self) -> bool:
        return (self.flags & ArchiveFlags.BlocksInfoAtTheEnd) != 0

    @property
    def has_blocks_and_directory_info_combined(self) -> bool:
        return (self.flags & ArchiveFlags.BlocksAndDirectoryInfoCombined) != 0

    @property
    def has_old_web_plugin_compatibility(self) -> bool:
        return (self.flags & ArchiveFlags.OldWebPluginCompatibility) != 0

    def get_header_size(self) -> int:
        return self.header_size

    def get_blocks_info_offset(self) -> int:
        if self.has_blocks_at_the_end:
            return self.size - self.compressed_blocks_info_size if self.size != 0 else UINT64_MAX
        if self.signature in (UnitySignature.UnityWeb, UnitySignature.UnityRaw): return 9
        return self.get_header_size()

    def decode(self, fs: FileStream):
        offset = fs.position
        self.signature = fs.read_string()
        assert self.signature == UnitySignature.UnityFS
        self.version = fs.read_sint32()
        assert self.version != 5
        self.unity_web_bundle_version = fs.read_string()
        self.unity_web_minimum_revision = fs.read_string()
        self.size = fs.read_uint64()
        self.compressed_blocks_info_size = fs.read_uint32()
        self.uncompressed_blocks_info_size = fs.read_uint32()
        assert self.compressed_blocks_info_size < self.uncompressed_blocks_info_size, vars(self)
        self.flags = fs.read_uint32()
        self.header_size = fs.position - offset


class UnityAssetBundle(object):
    def __init__(self):
        self.header = ArchiveStorageHeader()
        self.blocks_info: BlocksInfo = BlocksInfo()
        self.direcory_info: DirectoryInfo = DirectoryInfo()

    def read(self, file_path: str):
        fs = FileStream()
        fs.open(file_path)
        self.header.decode(fs)
        print(vars(self.header))
        blocks_info_offset = self.header.get_blocks_info_offset()
        fs.seek(blocks_info_offset)
        compression_type = self.header.compression_type
        if compression_type != CompressionType.NONE:
            compressed_data = fs.read(self.header.compressed_blocks_info_size)
            assert len(compressed_data) == self.header.compressed_blocks_info_size
            uncompressed_data = lz4.block.decompress(compressed_data, self.header.uncompressed_blocks_info_size)
            fs = FileStream(data=uncompressed_data)
            self.read_blocks_and_directory(fs)
        else:
            assert self.header.compressed_blocks_info_size == self.header.uncompressed_blocks_info_size
            self.read_blocks_and_directory(fs)

    def read_blocks_and_directory(self, fs: FileStream):
        self.blocks_info.decode(fs)
        print(self.blocks_info.uncompressed_data_hash)
        print(self.blocks_info.blocks)
        if self.header.has_blocks_and_directory_info_combined:
            self.direcory_info.decode(fs)
            print(self.direcory_info.nodes)


if __name__ == '__main__':
    arguments = argparse.ArgumentParser()
    arguments.add_argument('--file', '-f', required=True)
    options = arguments.parse_args(sys.argv[1:])
    ab = UnityAssetBundle()
    ab.read(file_path=options.file)
