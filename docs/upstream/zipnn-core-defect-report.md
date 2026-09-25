# Upstream defect report draft — zipnn C core (`zipnn_core`)

> **Status**: draft committed 2026-09-23 (Neo Phase 1, Plan §6.2 "推奨" item).
> The Neo maintainer's GitHub token is a fine-grained PAT scoped to their own
> repositories, so filing this on `zipnn/zipnn` requires a token with
> `public_repo` reach (or manual submission). The body below is ready to paste
> verbatim; reproduction was performed against the C core as vendored in
> ComfyUI-Model-Manager-Neo (`third_party/zipnn-core`, extension version
> 0.5.4-era sources, prebuilt `zipnn_core.cpython-311-x86_64-linux-gnu.so`),
> Debian 12, glibc 2.36, x86_64, CPython 3.11.2.

---

## Title

`zipnn_core`: deterministic SIGSEGV on 4-plane dtypes when the final chunk is 1–3 bytes, plus silent heap-overflow writes on all non-divisible chunk lengths

## Body

### Summary

The C extension (`csrc/zipnn_core.c` + `csrc/data_manipulation_dtype32.c`) has
two classes of memory-safety defects reachable through the normal
`ZipNN.compress()` / `delta_compress_files()` Python paths:

1. **Deterministic SIGSEGV** (signal 11, 100 % reproducible) when compressing
   data whose final 256 KiB chunk is 1, 2 or 3 bytes long on any 4-plane
   dtype (float32 / float / delta-file mode). The process dies without a
   Python exception — unrecoverable for the host application (e.g. ComfyUI).
2. **Silent heap corruption** (1–3 byte out-of-bounds writes past plane
   buffers + up to 3 bytes of out-of-bounds reads) on _every_ non-divisible
   chunk length for the 2-plane and 4-plane paths. Usually absorbed by
   allocator slack, but it is UB: under glibc hardening / different allocators
   / unlucky layouts it aborts (`free(): invalid size`, `double free or
corruption`) — we observed exactly such aborts when many odd-length cases
   run in one long-lived process.

### Root cause

`handle_split_mode_220()` (and `split_bytearray_dtype16`, mode 10) size the
plane buffers as `q + (b < remainder)` with `q = total_len / num_buf`, but the
interleave loop then writes **all four planes for every 4-byte group**,
including the final partial group:

```c
for (size_t i = 0; i < total_len; i += 4) {   // last iteration reads src[i..i+3]
  *dst1++ = src[i];                            // OOB when i+1..3 >= total_len
  *dst2++ = src[i + 1];
  *dst3++ = src[i + 2];
  *dst4++ = src[i + 3];
}
```

For `total_len % 4 == r ∈ {1,2,3}` this performs up to 3 out-of-bounds reads
and 1–3 out-of-bounds plane writes; when `q == 0` (final chunk shorter than
4 bytes), the zero-sized planes were never allocated (`allocate_4chunk_buffs`
leaves them `NULL`) and the loop writes through NULL → SIGSEGV. The 2-plane
path (`split_bytearray_dtype16`, odd `total_len`) has the same shape: one OOB
read (`src[len]`) plus two 1-byte OOB plane writes (the post-loop
`*dst0 = src[len-1]` fix-up writes at `plane0[half+1]`, one past its
`half+1`-byte allocation).

The decompressor never reads the overflow bytes (its `decompLen` math matches
the in-bounds `q + (b < rem)` plane sizes), which is why the corruption is
usually silent and round-trips still succeed.

### Reproduction (100 %)

```python
import zipnn, os
z = zipnn.ZipNN(input_format="byte", bytearray_dtype="float32", threads=1)
data = os.urandom(262144 + 1)      # final chunk = 1 byte
open("/tmp/crash.bin", "wb").write(data)
z.compress("/tmp/crash.bin", "/tmp/crash.znn", delete_original=False)
# → SIGSEGV (signal 11) inside zipnn_core.zipnn_core; no Python exception
```

Crashing lengths (float32/delta paths, chunk 256 KiB): every
`total % 262144 ∈ {1, 2, 3}` with `total ≥ 262144 + 1`, plus single-chunk
inputs of length 1–3. Verified matrix (22 cases): 8/8 documented crash
configurations reproduce with signal 11; `+64/+65/+66/+67` (final chunk ≥ 4 B)
survive but exercise the silent OOB writes (`+65/+66/+67` are odd/≡2/≡3 mod 4).

The production delta path reaches it directly:
`py/compress.py delta_compress_files` → xor/bsdiff buffers whose length is
`max(size_a, size_b)` — any pair differing by 1–3 bytes (mod 256 KiB) kills the
host process.

Silent-corruption variant (no crash, heap poisoned):

```python
z16 = zipnn.ZipNN(input_format="byte", bytearray_dtype="bfloat16", threads=1)
for i in range(200):
    z16.compress(path_i, out_i, ...)   # odd-length inputs in one process
# → eventually: free(): invalid size / munmap_chunk(): invalid pointer
```

### Suggested fix

Bound the interleave by the plane sizes — e.g. iterate whole groups only up to
`total_len - remainder`, then copy the `remainder` trailing bytes to planes
`0..remainder-1` individually (which is exactly what the subsequent
`switch (remainder)` block intends to do but currently does with additional
OOB writes), and skip `NULL`/zero-length planes everywhere. The decompressor
already defines the correct in-bounds layout (`decompLen` = `q + (b < rem)`),
so the fix is format-compatible: existing archives decode unchanged, and fixed
encoders produce byte-identical _payloads_ for divisible lengths.

### Impact

- Host-process kill without exception (data loss risk for unsaved work in
  interactive apps; ComfyUI process death).
- Silent heap corruption → non-deterministic aborts later in unrelated code.
- We implemented a memory-safe Rust port of the same format (byte-identical
  output on 9,880 differential test cases) and handle every crashing length
  as a clean success or error.

Happy to provide the full 22-case reproduction matrix, the differential test
harness, or a patch.

---

_Filed from ComfyUI-Model-Manager-Neo Phase 1 (Agent/Plan.md Appendix C;
evidence: `scripts/bench/results/c_defects.json`,
`scripts/l2/results/golden_diff.json`)._
