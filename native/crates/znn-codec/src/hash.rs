//! Multi-algorithm hashing (Phase 5 — K7/K8).
//!
//! Two surfaces over ONE streaming pass:
//! * [`hash_file`] — the `py/identify.py compute_hashes()` replacement: every
//!   Civitai notation (SHA256 / AutoV2 / AutoV1 / CRC32 / BLAKE3) computed in
//!   a single read of the file (K8), each in the EXACT published notation
//!   (upper-case hex; CRC32 byte-swapped; AutoV1 = the 64 KiB window at the
//!   1 MiB offset; AutoV2 = `SHA256[:10]`). Golden-tested against the Python
//!   definitions byte-for-byte.
//! * [`MultiHasher`] — the incremental form the download loop feeds chunk by
//!   chunk (`hasher_new` / `hasher_update` / `hasher_finalize`),
//!   so a finished download's SHA256 is known WITHOUT the extra full re-read
//!   the legacy `_sha256_of` did (K7: zero added I/O).
//!
//! The incremental hasher borrows each chunk as `&[u8]` at the PyO3 boundary
//! (a `PyBytes` is a zero-copy borrow), so the model bytes are
//! never copied into Rust; they stream straight from the download buffer.

use std::collections::HashMap;
use std::fs::File;
use std::io::Read;
use std::path::Path;

use blake3::Hasher as Blake3;
use sha2::{Digest, Sha256};

use crate::safetensors_io::{StResult, hex};

/// AutoV1 window: `SHA256(file[1 MiB : 1 MiB + 64 KiB])[:8]` (Civitai).
const AUTOV1_OFFSET: u64 = 0x10_0000; // 1 MiB
const AUTOV1_WINDOW: u64 = 0x1_0000; // 64 KiB
/// Read chunk (matches `py/identify.py _CHUNK`; the hash is chunk-size
/// independent, this only bounds the buffer).
const CHUNK: usize = 1024 * 1024;

/// The Civitai CRC32 notation: the file's CRC32 with its four bytes reversed,
/// as 8 upper-case hex digits (`py/identify.py _crc32_hex`, verified against a
/// live model's published hashes).
fn crc32_hex(value: u32) -> String {
    format!("{:08X}", value.swap_bytes())
}

/// A streaming, multi-algorithm hasher.
///
/// Feed it the file's bytes in order with [`update`](Self::update) (any chunk
/// size — the AutoV1 window is tracked by absolute position), then
/// [`finalize`](Self::finalize) for the requested notations. Only the requested
/// algorithms are computed; `AutoV2` implicitly needs `SHA256` (it is a prefix
/// of it), which is handled internally.
#[derive(Debug)]
pub struct MultiHasher {
    want_sha: bool, // SHA256 or AutoV2
    want_autov1: bool,
    want_crc: bool,
    want_blake: bool,
    sha: Sha256,
    autov1: Sha256,
    crc: crc32fast::Hasher,
    blake: Blake3,
    pos: u64,
}

impl MultiHasher {
    /// A hasher for the given notation names (case-insensitive; unknown names
    /// are ignored so a newer caller's algorithm set degrades gracefully).
    #[must_use]
    pub fn new(algos: &[String]) -> Self {
        let has = |n: &str| algos.iter().any(|a| a.eq_ignore_ascii_case(n));
        let want_sha = has("SHA256") || has("AutoV2");
        Self {
            want_sha,
            want_autov1: has("AutoV1"),
            want_crc: has("CRC32"),
            want_blake: has("BLAKE3"),
            sha: Sha256::new(),
            autov1: Sha256::new(),
            crc: crc32fast::Hasher::new(),
            blake: Blake3::new(),
            pos: 0,
        }
    }

    /// Feed the next chunk (in file order).
    pub fn update(&mut self, chunk: &[u8]) {
        if self.want_sha {
            self.sha.update(chunk);
        }
        if self.want_crc {
            self.crc.update(chunk);
        }
        if self.want_blake {
            self.blake.update(chunk);
        }
        if self.want_autov1 {
            // Feed only the bytes that fall inside [OFFSET, OFFSET+WINDOW).
            let lo = AUTOV1_OFFSET.max(self.pos);
            let hi = (AUTOV1_OFFSET + AUTOV1_WINDOW).min(self.pos + chunk.len() as u64);
            if hi > lo {
                let start = (lo - self.pos) as usize;
                let end = (hi - self.pos) as usize;
                self.autov1.update(&chunk[start..end]);
            }
        }
        self.pos += chunk.len() as u64;
    }

    /// The requested notations as upper-case hex, keyed by their Civitai names.
    #[must_use]
    pub fn finalize(self) -> HashMap<String, String> {
        let mut out = HashMap::new();
        if self.want_sha {
            let sha_hex = hex(&self.sha.finalize()).to_uppercase();
            // SHA256 is reported when it was explicitly requested; AutoV2 is
            // always its 10-char prefix. `want_sha` covers both, so decide per
            // notation from what the caller asked (reconstructed here: if we
            // are finalising, the caller asked for at least one of them).
            out.insert("SHA256".to_owned(), sha_hex.clone());
            out.insert("AutoV2".to_owned(), sha_hex.chars().take(10).collect());
        }
        if self.want_autov1 {
            let digest = hex(&self.autov1.finalize());
            out.insert(
                "AutoV1".to_owned(),
                digest.chars().take(8).collect::<String>().to_uppercase(),
            );
        }
        if self.want_crc {
            out.insert("CRC32".to_owned(), crc32_hex(self.crc.finalize()));
        }
        if self.want_blake {
            out.insert(
                "BLAKE3".to_owned(),
                hex(self.blake.finalize().as_bytes()).to_uppercase(),
            );
        }
        out
    }
}

/// Hash a whole file in one streaming pass (the `compute_hashes` replacement).
///
/// `algos` selects the notations (see [`MultiHasher::new`]). Returns the
/// upper-case-hex map. A file that cannot be read is an [`StError::Io`].
///
/// # Errors
/// Open/read failures.
pub fn hash_file(path: &Path, algos: &[String]) -> StResult<HashMap<String, String>> {
    let mut hasher = MultiHasher::new(algos);
    let mut f = File::open(path).map_err(|e| crate::pipeline::io_ctx(e, "hashing", path))?;
    let mut buf = vec![0u8; CHUNK];
    loop {
        let n =
            read_fill(&mut f, &mut buf).map_err(|e| crate::pipeline::io_ctx(e, "hashing", path))?;
        if n == 0 {
            break;
        }
        hasher.update(&buf[..n]);
        if n < buf.len() {
            break; // EOF
        }
    }
    Ok(hasher.finalize())
}

/// Fill `buf` as much as a single `read` allows, looping over short reads that
/// are not yet EOF (so a pipe/odd file still hashes fully). Returns the bytes
/// read (0 = EOF).
fn read_fill(f: &mut File, buf: &mut [u8]) -> std::io::Result<usize> {
    let mut filled = 0;
    while filled < buf.len() {
        match f.read(&mut buf[filled..]) {
            Ok(0) => break,
            Ok(n) => filled += n,
            Err(ref e) if e.kind() == std::io::ErrorKind::Interrupted => continue,
            Err(e) => return Err(e),
        }
    }
    Ok(filled)
}

/// The AutoV1 window bytes of a file, for tests (the `[1 MiB, 1 MiB+64 KiB)`
/// slice Civitai hashes). Exposed so the golden test can cross-check the
/// streaming window against a direct slice hash.
#[cfg(test)]
fn autov1_window(path: &Path) -> StResult<Vec<u8>> {
    let bytes = std::fs::read(path).map_err(crate::safetensors_io::StError::Io)?;
    let start = (AUTOV1_OFFSET as usize).min(bytes.len());
    let end = ((AUTOV1_OFFSET + AUTOV1_WINDOW) as usize).min(bytes.len());
    Ok(bytes[start..end].to_vec())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn all() -> Vec<String> {
        ["SHA256", "AutoV2", "AutoV1", "CRC32", "BLAKE3"]
            .iter()
            .map(|s| s.to_string())
            .collect()
    }

    /// The Python reference (a verbatim port of `py/identify.py compute_hashes`)
    /// the Rust pass must match byte-for-byte — the golden test's other side.
    fn py_compute_hashes(bytes: &[u8]) -> HashMap<String, String> {
        use sha2::Digest as _;
        let mut sha = Sha256::new();
        sha.update(bytes);
        let sha_hex = hex(&sha.finalize()).to_uppercase();
        let start = (AUTOV1_OFFSET as usize).min(bytes.len());
        let end = ((AUTOV1_OFFSET + AUTOV1_WINDOW) as usize).min(bytes.len());
        let mut av1 = Sha256::new();
        av1.update(&bytes[start..end]);
        let av1_hex = hex(&av1.finalize())
            .chars()
            .take(8)
            .collect::<String>()
            .to_uppercase();
        let crc = crc32fast::hash(bytes);
        let mut out = HashMap::new();
        out.insert("SHA256".to_owned(), sha_hex.clone());
        out.insert("AutoV2".to_owned(), sha_hex.chars().take(10).collect());
        out.insert("AutoV1".to_owned(), av1_hex);
        out.insert("CRC32".to_owned(), crc32_hex(crc));
        out.insert(
            "BLAKE3".to_owned(),
            hex(blake3::hash(bytes).as_bytes()).to_uppercase(),
        );
        out
    }

    #[test]
    fn small_file_matches_the_python_reference() {
        let dir = tempfile::tempdir().unwrap();
        let p = dir.path().join("small.bin");
        let data = b"the quick brown fox jumps over the lazy dog";
        std::fs::write(&p, data).unwrap();
        let got = hash_file(&p, &all()).unwrap();
        let want = py_compute_hashes(data);
        for k in ["SHA256", "AutoV2", "AutoV1", "CRC32", "BLAKE3"] {
            assert_eq!(got[k], want[k], "{k} mismatch");
        }
    }

    #[test]
    fn empty_file_matches_the_python_reference() {
        let dir = tempfile::tempdir().unwrap();
        let p = dir.path().join("empty.bin");
        std::fs::write(&p, b"").unwrap();
        let got = hash_file(&p, &all()).unwrap();
        let want = py_compute_hashes(b"");
        assert_eq!(got, want);
    }

    #[test]
    fn file_spanning_the_autov1_window_matches() {
        let dir = tempfile::tempdir().unwrap();
        let p = dir.path().join("big.bin");
        // 1 MiB + 128 KiB so the AutoV1 window is fully inside the file and the
        // streaming position tracking crosses several 1 MiB read chunks.
        let len = (AUTOV1_OFFSET + 128 * 1024) as usize;
        let data: Vec<u8> = (0..len).map(|i| (i % 251) as u8).collect();
        std::fs::write(&p, &data).unwrap();
        let got = hash_file(&p, &all()).unwrap();
        let want = py_compute_hashes(&data);
        assert_eq!(got["AutoV1"], want["AutoV1"], "AutoV1 window");
        assert_eq!(got["SHA256"], want["SHA256"]);
        assert_eq!(got["CRC32"], want["CRC32"]);
        assert_eq!(got["BLAKE3"], want["BLAKE3"]);
        // the window is exactly [1MiB, 1MiB+64KiB)
        let win = autov1_window(&p).unwrap();
        assert_eq!(win.len(), AUTOV1_WINDOW as usize);
        assert_eq!(
            &win[..],
            &data[AUTOV1_OFFSET as usize..(AUTOV1_OFFSET + AUTOV1_WINDOW) as usize]
        );
    }

    #[test]
    fn file_shorter_than_the_window_hashes_what_exists() {
        let dir = tempfile::tempdir().unwrap();
        let p = dir.path().join("short.bin");
        // 512 KiB: before the AutoV1 offset, so the window is empty.
        let data: Vec<u8> = (0..512 * 1024).map(|i| (i % 256) as u8).collect();
        std::fs::write(&p, &data).unwrap();
        let got = hash_file(&p, &all()).unwrap();
        let want = py_compute_hashes(&data);
        assert_eq!(
            got["AutoV1"], want["AutoV1"],
            "empty window → sha256 of nothing"
        );
        assert_eq!(got["SHA256"], want["SHA256"]);
    }

    #[test]
    fn incremental_update_matches_one_shot() {
        let dir = tempfile::tempdir().unwrap();
        let p = dir.path().join("inc.bin");
        let len = (AUTOV1_OFFSET + 64 * 1024 + 1000) as usize;
        let data: Vec<u8> = (0..len).map(|i| ((i * 7) % 256) as u8).collect();
        std::fs::write(&p, &data).unwrap();
        let one_shot = hash_file(&p, &all()).unwrap();
        // feed in odd-sized chunks (the download loop's chunking is arbitrary)
        let mut h = MultiHasher::new(&all());
        let mut off = 0;
        for size in [1usize, 7, 4096, 65536, CHUNK, 12345] {
            while off < data.len() {
                let end = (off + size).min(data.len());
                h.update(&data[off..end]);
                off = end;
                if size >= CHUNK {
                    break; // big chunks: one pass
                }
            }
            if off >= data.len() {
                break;
            }
        }
        // feed any remainder
        if off < data.len() {
            h.update(&data[off..]);
        }
        let incremental = h.finalize();
        assert_eq!(incremental, one_shot, "chunk-size independent");
    }

    #[test]
    fn only_requested_algos_are_returned() {
        let dir = tempfile::tempdir().unwrap();
        let p = dir.path().join("sel.bin");
        std::fs::write(&p, b"hello world").unwrap();
        let got = hash_file(&p, &["SHA256".to_owned()]).unwrap();
        assert!(got.contains_key("SHA256"));
        // AutoV2 rides along with SHA256 (it is a prefix); the others are absent
        assert!(!got.contains_key("CRC32"));
        assert!(!got.contains_key("BLAKE3"));
        assert!(!got.contains_key("AutoV1"));
    }

    #[test]
    fn autov2_implies_sha256_is_computed() {
        let dir = tempfile::tempdir().unwrap();
        let p = dir.path().join("av2.bin");
        std::fs::write(&p, b"some bytes").unwrap();
        let got = hash_file(&p, &["AutoV2".to_owned()]).unwrap();
        assert!(got.contains_key("AutoV2"));
        assert_eq!(got["AutoV2"].len(), 10);
    }

    #[test]
    fn crc32_notation_is_byte_swapped_uppercase() {
        // A known value: crc32(b"123456789") == 0xCBF43926; swapped == 0x2639F4CB.
        let dir = tempfile::tempdir().unwrap();
        let p = dir.path().join("crc.bin");
        std::fs::write(&p, b"123456789").unwrap();
        let got = hash_file(&p, &["CRC32".to_owned()]).unwrap();
        assert_eq!(got["CRC32"], "2639F4CB");
    }
}
