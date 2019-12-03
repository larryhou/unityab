from stream import FileStream
from typing import List, Dict
from strings import get_caculate_string
import io, uuid

MONO_BEHAVIOUR_PERSISTENT_ID = 114

class SerializeFileHeader(object):
    def __init__(self):
        self.metadata_size: int = 0
        self.file_size: int = 0
        self.version: int = 0
        self.data_offset: int = 0
        self.endianess: int = 0

class MetadataType(object):
    def __init__(self, name:str, index:int, fields: List['TypeField'], type_tree: 'MetadataTypeTree'):
        self.fields: List[TypeField] = fields
        self.name: str = name
        self.index: int = index
        self.type_tree: MetadataTypeTree = type_tree

class MetadataTypeTree(object):
    def __init__(self, type_tree_enabled: bool):
        self.persistent_type_id: int = -1
        self.is_stripped_type: bool = False
        self.script_type_index: int = -1
        self.script_type_hash: bytes = b''
        self.type_hash: bytes = b''
        self.nodes: List[TypeField] = []
        self.strings: Dict[int, str] = {}
        self.type_tree_enabled: bool = type_tree_enabled
        self.type_dict: Dict[int, MetadataType] = {}

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
                node = TypeField()
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
            for node in self.nodes:  # type: TypeField
                node.name = get_caculate_string(offset=node.name_str_offset, strings=self.strings)
                node.type = get_caculate_string(offset=node.type_str_offset, strings=self.strings)
                # print(vars(node))

    def __repr__(self):
        buf = io.StringIO()
        buf.write('[MetadataTypeTree] persistent_type_id={} is_stripped_type={} script_type_index={} type_hash={}'.format(self.persistent_type_id, self.is_stripped_type, self.script_type_index, uuid.UUID(bytes=self.type_hash)))
        if self.persistent_type_id == MONO_BEHAVIOUR_PERSISTENT_ID: buf.write(' mono_hash={}'.format(uuid.UUID(bytes=self.script_type_hash)))
        buf.write('\n')
        for node in self.nodes:
            buf.write(node.level * '    ')
            buf.write('{}:\'{}\''.format(node.name, node.type))
            if node.is_array: buf.write('[]')
            buf.write(' {} {}\n'.format(node.byte_size, node.index))
        buf.seek(0)
        return buf.read()

class TypeField(object):
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
        self.level = fs.read_uint8()
        self.is_array = fs.read_boolean()
        self.type_str_offset = fs.read_uint32()
        self.name_str_offset = fs.read_uint32()
        self.byte_size = fs.read_sint32()
        self.index = fs.read_sint32()
        self.meta_flag = fs.read_uint32()

    def __repr__(self):
        return '{{{}:\'{}\'}}'.format(self.name, self.type)

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

    def __repr__(self):
        return '{{guid=\'{}\', type={}, path=\'{}\'}}'.format(uuid.UUID(bytes=self.guid), self.type, self.path)

class SerializeFile(object):
    def __init__(self):
        self.header: SerializeFileHeader = SerializeFileHeader()
        self.version: str = ''
        self.platform: int = 0
        self.type_tree_enabled: bool = False
        self.metadata_types: List[MetadataTypeTree] = []
        self.objects: List[ObjectInfo] = []
        self.typeinfos: List[ScriptTypeInfo] = []
        self.externals: List[ExternalInfo] = []
        self.__premitive_decoders = {
            'bool': FileStream.read_boolean,
            'SInt8': FileStream.read_sint8,
            'UInt8': FileStream.read_uint8,
            'char': FileStream.read_uint8,
            'SInt16': FileStream.read_sint16,
            'UInt16': FileStream.read_uint16,
            'short': FileStream.read_short,
            'unsigned short': FileStream.read_uint16,
            'SInt32': FileStream.read_sint32,
            'UInt32': FileStream.read_uint32,
            'int': FileStream.read_sint32,
            'unsigned int': FileStream.read_uint32,
            'SInt64': FileStream.read_sint64,
            'UInt64': FileStream.read_uint64,
            'long': FileStream.read_sint64,
            'unsigned long': FileStream.read_uint64,
            'float': FileStream.read_float,
            'double': FileStream.read_double,
        }

    @staticmethod
    def register_type_tree(type_tree: MetadataTypeTree):
        walker = []
        cursor = None
        for node in type_tree.nodes:
            if not cursor: pass
            else:
                if cursor.level == node.level:
                    _, fields = walker[-1]
                    fields.append(node)
                elif cursor.level < node.level:
                    walker.append((cursor, [node]))
                elif cursor.level > node.level:
                    for _ in range(cursor.level - node.level):
                        t, fields = walker.pop()
                        meta_type = MetadataType(name=t.type, index=t.index, fields=fields, type_tree=type_tree)
                        type_tree.type_dict[meta_type.index] = meta_type
                    _, fields = walker[-1]
                    fields.append(node)
            cursor = node
        while walker:
            t, fields = walker.pop()
            meta_type = MetadataType(name=t.type, index=t.index, fields=fields, type_tree=type_tree)
            type_tree.type_dict[meta_type.index] = meta_type

    def deserialize(self, fs: FileStream, meta_type: MetadataType):
        result = {}
        type_map = meta_type.type_tree.type_dict
        for n in range(len(meta_type.fields)):
            node = meta_type.fields[n]
            if node.is_array:
                element_type = meta_type.type_tree.nodes[node.index + 2]
                element_count = fs.read_sint32()
                if element_type.byte_size == 1:
                    result[node.name] = fs.read(element_count) if element_count > 0 else b''
                    fs.align()
                else:
                    items = []
                    if element_type.type in self.__premitive_decoders:
                        decode = self.__premitive_decoders.get(element_type.type)
                        for _ in range(element_count):
                            items.append(decode(fs))
                    elif element_type.type == 'string':
                        for _ in range(element_count):
                            size = fs.read_sint32()
                            items.append(fs.read(size) if size > 0 else b'')
                            fs.align()
                    else:
                        for m in range(element_count):
                            it = self.deserialize(fs, meta_type=type_map.get(element_type.index))
                            items.append(it)
                    result[node.name] = items
                    fs.align()
            elif node.type == 'string':
                size = fs.read_sint32()
                result[node.name] = fs.read(size) if size > 0 else b''
                fs.align()
            elif node.type in self.__premitive_decoders:
                result[node.name] = self.__premitive_decoders.get(node.type)(fs)
                if node.meta_flag & 0x4000 != 0: fs.align()
            else:
                result[node.name] = self.deserialize(fs, meta_type=type_map.get(node.index))
        return result

    def dump(self, fs: FileStream):
        for o in self.objects:
            fs.seek(self.header.data_offset + o.byte_start)
            type_tree = self.metadata_types[o.type_id]
            print(fs.position, vars(type_tree.type_dict.get(0)))
            data = self.deserialize(fs=fs, meta_type=type_tree.type_dict.get(0))
            print(data)
            print()

    def decode(self, fs:FileStream):
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
        print('type', type_count)
        for _ in range(type_count):
            type_tree = MetadataTypeTree(type_tree_enabled=self.type_tree_enabled)
            type_tree.decode(fs)
            self.metadata_types.append(type_tree)
            self.register_type_tree(type_tree=type_tree)
            print(type_tree)

        object_count = fs.read_sint32()
        print('object', object_count)
        for _ in range(object_count):
            fs.align(4)
            obj = ObjectInfo()
            obj.decode(fs)
            self.objects.append(obj)
            print(vars(obj))

        script_type_count = fs.read_sint32()
        print('typeinfo', script_type_count)
        for _ in range(script_type_count):
            st = ScriptTypeInfo()
            st.decode(fs)
            self.typeinfos.append(st)
            print(vars(st))

        external_count = fs.read_sint32()
        print('external', external_count)
        for _ in range(external_count):
            ext = ExternalInfo()
            ext.decode(fs)
            self.externals.append(ext)
            print(ext)

        fs.read_string()
        print(fs.position)






