"""Harness stub of `zipnn.util_torch`."""


class ZipNNDtypeEnum:  # pragma: no cover - stub
    pass


def zipnn_is_floating_point(fmt, tensor, dtype):
    return str(dtype).replace("torch.", "") in (
        "float16",
        "bfloat16",
        "float32",
        "float64",
    )


def zipnn_multiply_if_max_below(*a, **k):  # pragma: no cover - stub
    raise NotImplementedError


def zipnn_get_dtype_bits(*a, **k):  # pragma: no cover - stub
    raise NotImplementedError


def zipnn_divide_int(*a, **k):  # pragma: no cover - stub
    raise NotImplementedError


def zipnn_pack_shape(*a, **k):  # pragma: no cover - stub
    raise NotImplementedError


def zipnn_unpack_shape(*a, **k):  # pragma: no cover - stub
    raise NotImplementedError
