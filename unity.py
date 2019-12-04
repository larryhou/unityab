#!/usr/bin/env python3

import argparse
import enum
import sys

import lz4.block

from format import TextureFormat
from stream import FileStream
from typing import List, Dict

import serialize
import os, json

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
    SerializedFile = 0x4

class UnitySignature(object):
    UnityFS = 'UnityFS'
    UnityWeb = 'UnityWeb'
    UnityRaw = 'UnityRaw'
    UnityArchive = 'UnityArchive'

class FileNode(object):
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
        self.nodes: List[FileNode] = []

    def decode(self, fs: FileStream):
        for _ in range(fs.read_uint32()):
            node = FileNode()
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

    def get_data_offset(self):
        size = self.get_header_size()
        if not self.has_blocks_at_the_end:
            size += self.compressed_blocks_info_size
        return size

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


class UnityArchiveFile(object):
    def __init__(self, debug:bool = True):
        self.debug = debug
        self.header = ArchiveStorageHeader()
        self.blocks_info: BlocksInfo = BlocksInfo()
        self.direcory_info: DirectoryInfo = DirectoryInfo()
        self.data_offset: int = 0
        self.uncompressed_blocks_offsets: List[int] = []
        self.blocks_offsets: List[int] = []
        self.minimum_read_buffer_size: int = 0

    def print(self, *args):
        if self.debug: print(*args)

    def decode(self, file_path: str):
        fs = FileStream()
        fs.open(file_path)
        self.header.decode(fs)
        self.print(vars(self.header))
        blocks_info_offset = self.header.get_blocks_info_offset()
        fs.seek(blocks_info_offset)
        compression_type = self.header.compression_type
        if compression_type != CompressionType.NONE:
            compressed_data = fs.read(self.header.compressed_blocks_info_size)
            assert len(compressed_data) == self.header.compressed_blocks_info_size
            uncompressed_data = lz4.block.decompress(compressed_data, self.header.uncompressed_blocks_info_size)
            temp = FileStream(data=uncompressed_data)
            self.read_blocks_and_directory(temp)
        else:
            assert self.header.compressed_blocks_info_size == self.header.uncompressed_blocks_info_size
            self.read_blocks_and_directory(fs)
        import io
        buffer = io.BytesIO()
        for block in self.blocks_info.blocks:
            if block.compression_type != CompressionType.NONE:
                compressed_data = fs.read(block.compressed_size)
                uncompressed_data = lz4.block.decompress(compressed_data, block.uncompressed_size)
                assert len(uncompressed_data) == block.uncompressed_size, uncompressed_data
                buffer.write(uncompressed_data)
                # print(uncompressed_data)
            else:
                uncompressed_data = fs.read(block.uncompressed_size)
                buffer.write(uncompressed_data)
        assert fs.position == fs.length
        buffer.seek(0)
        with open('data.bin', 'wb') as fp:
            fp.write(buffer.read())
            buffer.seek(0)
        return FileStream(data=buffer.read())

    def read_blocks_and_directory(self, fs: FileStream):
        self.blocks_info.decode(fs)
        self.print(self.blocks_info.uncompressed_data_hash)
        self.print(len(self.blocks_info.blocks),vars(self.blocks_info))
        if self.header.has_blocks_and_directory_info_combined:
            self.direcory_info.decode(fs)
            self.print(vars(self.direcory_info))
        self.data_offset = fs.position
        worst_compression_ratio = 1.0
        self.uncompressed_blocks_offsets = [0]
        self.blocks_offsets = [0]
        for i in range(len(self.blocks_info.blocks)):
            block = self.blocks_info.blocks[i]
            self.uncompressed_blocks_offsets.append(0)
            self.blocks_offsets.append(0)
            self.uncompressed_blocks_offsets[i + 1] = self.uncompressed_blocks_offsets[i] + block.uncompressed_size
            self.blocks_offsets[i + 1] = self.blocks_offsets[i] + block.compressed_size
            if not block.is_streamed and self.minimum_read_buffer_size < block.compressed_size:
                self.minimum_read_buffer_size = block.compressed_size
            ratio = 1.0 * block.compressed_size / block.uncompressed_size
            if worst_compression_ratio > ratio: worst_compression_ratio = ratio
        self.minimum_read_buffer_size = int(self.minimum_read_buffer_size / worst_compression_ratio)
        self.print(self.minimum_read_buffer_size, worst_compression_ratio)

class Commands(object):
    dump = 'dump'
    save = 'save'
    type = 'type'

    @classmethod
    def get_option_choices(cls):
        choices = []
        for name, value in vars(Commands).items():
            if name == value: choices.append(name)
        return choices

def standardize(data):
    if isinstance(data, dict):
        for key, value in data.items():  # type: str, any
            if isinstance(value, bytes):
                data[key] = value.hex() if key == 'data' else value.decode('utf-8')
            else: standardize(value)
    elif isinstance(data, list):
        for n in range(len(data)):
            item = data[n]
            if isinstance(item, bytes):
                try: data[n] = item.decode('utf-8')
                except: data[n] = item.hex()
            else:
                standardize(item)

def processs(parameters: Dict[str, any]):
    import os.path as p
    serializer = parameters.get('serializer')  # type: serialize.SerializedFile
    options = parameters.get('options')
    archive = parameters.get('archive')  # type: UnityArchiveFile
    command = options.command  # type: str
    stream = parameters.get('stream')  # type: FileStream

    if command == Commands.dump:
        serializer.dump(stream)
    elif command == Commands.type:
        import uuid
        for type_tree in serializer.type_trees:
            print('{:3d} \033[33m{} \033[36m{} \033[32m{}\033[0m'.format(type_tree.persistent_type_id, type_tree.nodes[0].type, uuid.UUID(bytes=type_tree.type_hash), type_tree.script_type_index))
    elif command == Commands.save:
        file_name = p.basename(parameters.get('file_path'))
        file_name = file_name[:file_name.rfind('.')]
        for o in serializer.objects:
            type_tree = serializer.type_trees[o.type_id]
            export_path = p.join('__export/{}/{}/{}'.format(file_name, serializer.node.path, type_tree.name))
            if not options.types or type_tree.persistent_type_id in options.types:
                if not p.exists(export_path): os.makedirs(export_path)
                stream.seek(serializer.node.offset + serializer.header.data_offset + o.byte_start)
                target = serializer.deserialize(stream, meta_type=type_tree.type_dict.get(0))
                name = target.get('m_Name')  # type: bytes
                if not name: name = '{}'.format(o.local_identifier_in_file).encode('utf-8')
                if type_tree.name == 'Texture2D':
                    target['m_TextureFormat'] = TextureFormat(target['m_TextureFormat']).__repr__()
                    target['m_ForcedFallbackFormat'] = TextureFormat(target['m_ForcedFallbackFormat']).__repr__()
                    data = target['image data'].get('data', b'')
                    if not data:
                        stream_data = target.get('m_StreamData')  # type: dict
                        offset = stream_data.get('offset')
                        size = stream_data.get('size')
                        node = archive.direcory_info.nodes[1]
                        stream.seek(node.offset + offset)
                        data = stream.read(size)
                    extension = 'tex'
                    with open('{}/{}.json'.format(export_path, name.decode('utf-8')), 'w') as fp:
                        del target['image data']
                        standardize(target)
                        fp.write(json.dumps(target, ensure_ascii=False, indent=4))
                    print(target)
                elif type_tree.name == 'TextAsset':
                    print(target)
                    data = target.get('m_Script')
                    extension = 'bytes'
                else:
                    print(vars(o), target)
                    standardize(target)
                    data = json.dumps(target, ensure_ascii=False, indent=4).encode('utf-8')
                    extension = 'json'
                with open('{}/{}.{}'.format(export_path, name.decode('utf-8'), extension), 'wb') as fp:
                    fp.write(data)
                    print('  + {}'.format(fp.name))

def main():
    arguments = argparse.ArgumentParser()
    arguments.add_argument('--file', '-f', nargs='+', required=True)
    arguments.add_argument('--command', '-c', choices=Commands.get_option_choices(), default=Commands.dump)
    arguments.add_argument('--debug', '-d', action='store_true')
    arguments.add_argument('--types', '-t', nargs='+', type=int)

    options = arguments.parse_args(sys.argv[1:])
    for file_path in options.file:
        print('>>>', file_path)
        archive = UnityArchiveFile(debug=options.debug)
        try:
            stream = archive.decode(file_path=file_path)
            node = archive.direcory_info.nodes[0]
        except:
            stream = FileStream(file_path=file_path)
            node = FileNode()
            node.size = stream.length
        if archive.direcory_info.nodes:
            for node in archive.direcory_info.nodes:
                if node.flags == NodeFlags.SerializedFile:
                    print('[+] {} {:,}'.format(node.path, node.size))
                    stream.endian = '>'
                    serializer = serialize.SerializedFile(debug=options.debug, node=node)
                    serializer.decode(stream)
                    processs(parameters=locals())
        else:
            serializer = serialize.SerializedFile(debug=options.debug, node=node)
            serializer.decode(stream)
            processs(parameters=locals())


if __name__ == '__main__':
    main()
