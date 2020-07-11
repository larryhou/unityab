#!/usr/bin/env python3
import os.path as p
import os, struct
from serialize import MetadataTypeTree
from stream import FileStream
import uuid

def main():
    import argparse, sys
    arguments = argparse.ArgumentParser()
    arguments.add_argument('--file', '-f', required=True)
    arguments.add_argument('--output', '-o', default='__types')
    options = arguments.parse_args(sys.argv[1:])
    output = p.abspath(options.output)
    if not p.exists(output): os.makedirs(output)
    MONO_BEHAVIOUR_PERSISTENT_ID = 114

    stream = FileStream(file_path=options.file)
    stream.endian = '<'
    while stream.bytes_available:
        persistent_id = stream.read_uint32()
        script_hash = b'0'*16
        if persistent_id == MONO_BEHAVIOUR_PERSISTENT_ID:
            script_hash = stream.read(16)
        type_hash = stream.read(16)
        size = stream.read_uint32()
        offset = stream.position
        print(persistent_id, uuid.UUID(bytes=script_hash), uuid.UUID(bytes=type_hash), size)
        type_tree = MetadataTypeTree(True)
        type_tree.persistent_type_id = persistent_id
        type_tree.type_hash = type_hash
        type_tree.mono_hash = script_hash
        type_tree.decode_type_tree(fs=stream)
        print(type_tree)
        assert stream.position == offset + size


if __name__ == '__main__':
    main()
