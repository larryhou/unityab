from stream import FileStream
from typing import List, Dict
from strings import get_caculate_string
import io

MONO_BEHAVIOUR_PERSISTENT_ID = 114

class SerializeFileHeader(object):
    def __init__(self):
        self.metadata_size: int = 0
        self.file_size: int = 0
        self.version: int = 0
        self.data_offset: int = 0
        self.endianess: int = 0

class MetadataType(object):
    def __init__(self, type_tree_enabled: bool):
        self.persistent_type_id: int = -1
        self.is_stripped_type: bool = False
        self.script_type_index: int = -1
        self.script_type_hash: bytes = b''
        self.type_hash: bytes = b''
        self.nodes: List[MetadataTypeField] = []
        self.strings: Dict[int, str] = {}
        self.type_tree_enabled: bool = type_tree_enabled

    def decode(self, fs: FileStream):
        self.persistent_type_id = fs.read_sint32()
        self.is_stripped_type = fs.read_boolean()
        self.script_type_index = fs.read_sint16()
        if self.persistent_type_id == MONO_BEHAVIOUR_PERSISTENT_ID:
            self.script_type_hash = fs.read(16)
        self.type_hash = fs.read(16)
        self.nodes = []
        self.strings = {}
        type_index = -1
        if self.type_tree_enabled:
            node_count = fs.read_uint32()
            char_count = fs.read_uint32()
            for _ in range(node_count):
                node = MetadataTypeField()
                node.decode(fs)
                if type_index >= 0: assert node.index == type_index + 1
                self.nodes.append(node)
                type_index += 1
            if char_count > 0:
                string_offset = fs.position
                string_size = 0
                while string_size + 1 < char_count:
                    offset = fs.position - string_offset
                    position = fs.position
                    self.strings[offset] = fs.read_string()
                    string_size += fs.position - position
                assert fs.position - string_offset == char_count
            for node in self.nodes:  # type: MetadataTypeField
                node.name = get_caculate_string(offset=node.name_str_offset, strings=self.strings)
                node.type = get_caculate_string(offset=node.type_str_offset, strings=self.strings)
                print(vars(node))

    def __repr__(self):
        buf = io.StringIO()
        buf.write('[MetadataType] persistent_type_id={} is_stripped_type={} script_type_index={} type_hash={}\n'.format(self.persistent_type_id, self.is_stripped_type, self.script_type_index, self.type_hash))
        for node in self.nodes:
            buf.write(node.level * '    ')
            buf.write('{}:\'{}\' {}\n'.format(node.name, node.type, node.byte_size))
        buf.seek(0)
        return buf.read()

class MetadataTypeField(object):
    def __init__(self):
        self.version: int = 0  # sint16
        self.level: int = 0  # uint8
        self.is_array: bool = False
        self.type: str = ''
        self.type_str_offset: int = 0  # uint32
        self.name: str = ''
        self.name_str_offset: int = 0  # uint32
        self.byte_size: int = 0  # sint32
        self.index = -1  # sint32
        self.meta_flag = 0  # uint32

    def decode(self, fs: FileStream):
        self.version = fs.read_sint16()
        self.level = fs.read_ubyte()
        self.is_array = fs.read_boolean()
        self.type_str_offset = fs.read_uint32()
        self.name_str_offset = fs.read_uint32()
        self.byte_size = fs.read_sint32()
        self.index = fs.read_sint32()
        self.meta_flag = fs.read_uint32()

class ObjectInfo(object):
    def __init__(self):
        self.local_identifier_in_file: int = -1  # sint64
        self.byte_start: int = 0   # uint32
        self.byte_size: int = 0  # uint32
        self.type_id: int = 0  # uint32

    def decode(self, fs: FileStream):
        self.local_identifier_in_file = fs.read_sint64()
        self.byte_start = fs.read_uint32()
        self.byte_size = fs.read_uint32()
        self.type_id = fs.read_uint32()

class ScriptTypeInfo(object):
    def __init__(self):
        self.local_serialized_file_index: int = -1  # sint32
        self.local_identifier_in_file: int = -1  # sint64

    def decode(self, fs: FileStream):
        self.local_serialized_file_index = fs.read_sint32()
        fs.align(4)
        self.local_identifier_in_file = fs.read_sint64()

class ExternalInfo(object):
    def __init__(self):
        self.guid: bytes = b''
        self.type: int = -1
        self.path: str = ''

    def decode(self, fs: FileStream):
        fs.read_string()
        self.guid = fs.read(16)
        self.type = fs.read_sint32()
        self.path = fs.read_string()

class SerializeFile(object):
    def __init__(self):
        self.header: SerializeFileHeader = SerializeFileHeader()
        self.version: str = ''
        self.platform: int = 0
        self.type_tree_enabled: bool = False
        self.metadata_types: List[MetadataType] = []
        self.objects: List[ObjectInfo] = []
        self.script_types: List[ScriptTypeInfo] = []
        self.externals: List[ExternalInfo] = []

    def read(self, fs:FileStream):
        header = self.header
        header.metadata_size = fs.read_sint32()
        header.file_size = fs.read_sint32()
        header.version = fs.read_sint32()
        header.data_offset = fs.read_sint32()
        header.endianess = fs.read_boolean()
        fs.read(3)  # reserved bytes
        fs.endian = '>' if header.endianess else '<'
        print(vars(header))
        self.version = fs.read_string()
        self.platform = fs.read_uint32()
        self.type_tree_enabled = fs.read_boolean()
        print(self.version, self.platform, self.type_tree_enabled)
        self.metadata_types = []
        type_count = fs.read_uint32()
        for _ in range(type_count):
            meta_type = MetadataType(type_tree_enabled=self.type_tree_enabled)
            meta_type.decode(fs)
            self.metadata_types.append(meta_type)
            print(meta_type)
        object_count = fs.read_sint32()
        print('object', object_count)
        for _ in range(object_count):
            fs.align(4)
            obj = ObjectInfo()
            obj.decode(fs)
            self.objects.append(obj)
            print(vars(obj))

        script_type_count = fs.read_sint32()
        print('script_type', script_type_count)
        for _ in range(script_type_count):
            st = ScriptTypeInfo()
            st.decode(fs)
            self.script_types.append(st)
            print(vars(st))

        external_count = fs.read_sint32()
        print('external', external_count)
        for _ in range(external_count):
            ext = ExternalInfo()
            ext.decode(fs)
            self.externals.append(ext)
            print(vars(ext))

        fs.read_string()
        print(fs.position)






