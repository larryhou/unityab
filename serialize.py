from stream import FileStream
from typing import List, Dict

class SerializeFileHeader(object):
    def __init__(self):
        self.metadata_size: int = 0
        self.file_size: int = 0
        self.version: int = 0
        self.data_offset: int = 0
        self.endianess: int = 0

class MetadataType(object):
    def __init__(self):
        self.persistent_type_id: int = -1
        self.is_stripped_type: bool = False
        self.script_type_index: int = -1
        self.script_type_hash: bytes = b''
        self.type_hash: bytes = b''
        self.nodes: List[TypeTreeNode] = []
        self.strings: Dict[int, str] = {}

class TypeTreeNode(object):
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

class SerializeFile(object):
    def __init__(self):
        self.header: SerializeFileHeader = SerializeFileHeader()
        self.version: str = ''
        self.platform: int = 0
        self.type_tree_enabled: bool = False
        self.metadata_types: List[MetadataType] = []

    def read(self, fs:FileStream):
        MONO_BEHAVIOUR_PERSISTENT_ID = 114
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
        from strings import get_caculate_string
        for _ in range(type_count):
            meta_type = MetadataType()
            meta_type.persistent_type_id = fs.read_sint32()
            meta_type.is_stripped_type = fs.read_boolean()
            meta_type.script_type_index = fs.read_sint16()
            if meta_type.persistent_type_id == MONO_BEHAVIOUR_PERSISTENT_ID:
                meta_type.script_type_hash = fs.read(16)
            meta_type.type_hash = fs.read(16)
            meta_type.nodes = []
            meta_type.strings = {}
            type_index = -1
            if self.type_tree_enabled:
                node_count = fs.read_uint32()
                char_count = fs.read_uint32()
                for _ in range(node_count):
                    node = TypeTreeNode()
                    node.version = fs.read_sint16()
                    node.level = fs.read_ubyte()
                    node.is_array = fs.read_boolean()
                    node.type_str_offset = fs.read_uint32()
                    node.name_str_offset = fs.read_uint32()
                    node.byte_size = fs.read_sint32()
                    node.index = fs.read_sint32()
                    if type_index >= 0: assert node.index == type_index + 1
                    node.meta_flag = fs.read_uint32()
                    meta_type.nodes.append(node)
                    type_index += 1
                if char_count > 0:
                    string_offset = fs.position
                    string_size = 0
                    while string_size + 1 < char_count:
                        offset = fs.position - string_offset
                        position = fs.position
                        meta_type.strings[offset] = fs.read_string()
                        string_size += fs.position - position
                    assert fs.position - string_offset == char_count
                for node in meta_type.nodes:  # type: TypeTreeNode
                    node.name = get_caculate_string(offset=node.name_str_offset, strings=meta_type.strings)
                    node.type = get_caculate_string(offset=node.type_str_offset, strings=meta_type.strings)
                    print(vars(node))
            self.metadata_types.append(meta_type)
            print(vars(meta_type))




