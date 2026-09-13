"""Harness stub of `zipnn.util_header`."""


class _E:
    def __init__(self, value):
        self.value = value


class EnumMethod:
    AUTO = _E(0)
    ZSTD = _E(1)
    HUFFMAN = _E(2)
    LZ4 = _E(3)
    SNAPPY = _E(4)

    def __new__(cls, value=None):
        return _E(value)


class EnumFormat:
    BYTE = _E(0)
    TORCH = _E(1)
    NUMPY = _E(2)

    def __new__(cls, value=None):
        return _E(value)


class EnumLossy:
    NONE = _E(0)

    def __new__(cls, value=None):
        return _E(value)
