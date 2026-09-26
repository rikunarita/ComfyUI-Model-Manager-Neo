//! L1 unit tests of the delta codec (Phase 3). The end-to-end route/ws
//! contract and the cross-path (legacy ⇄ native) goldens live in the Python
//! suite (`tests/test_phase3_delta.py`); these tests pin the wire format,
//! the legacy error wording, the Appendix-C SEGFAULT class (Plan §6.2
//! Phase 3: "付録 C の SEGFAULT ケースをデルタ端到端テストに固定化"), the
//! integrity pipeline (ftSha256 / `.corrupt` / paranoid / cancel) and the
//! hostile-input guards.

use super::*;
use crate::pipeline::Progress;
use crate::safetensors_io::tmp_sibling;
use std::sync::atomic::{AtomicBool, Ordering};

struct TempDir(PathBuf);
impl TempDir {
    fn new(tag: &str) -> Self {
        let mut p = std::env::temp_dir();
        p.push(format!(
            "mmneo-delta-{tag}-{}-{:?}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.subsec_nanos())
                .unwrap_or(0)
        ));
        std::fs::create_dir_all(&p).unwrap();
        Self(p)
    }
    fn path(&self, name: &str) -> PathBuf {
        self.0.join(name)
    }
}
impl Drop for TempDir {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.0);
    }
}

/// Deterministic pseudo-random bytes (the fine-tune "drift").
fn noisy_bytes(n: usize, seed: u32) -> Vec<u8> {
    let mut x = seed | 1;
    let mut out = Vec::with_capacity(n);
    for _ in 0..n {
        x = x.wrapping_mul(1664525).wrapping_add(1013904223);
        out.push((x >> 16) as u8);
    }
    out
}

/// A raw safetensors image with an EXACT header length: the JSON is
/// space-padded (trailing spaces are valid JSON whitespace — the same trick
/// the delta padding itself uses) to `header_len` bytes.
fn st_image(header_len: usize, data: &[u8]) -> Vec<u8> {
    let base_json = r#"{"weight":{"dtype":"F32","shape":[4],"data_offsets":[0,16]}}"#;
    assert!(header_len >= base_json.len());
    let mut header = base_json.as_bytes().to_vec();
    header.resize(header_len, b' ');
    let mut out = Vec::new();
    out.extend_from_slice(&(header_len as u64).to_le_bytes());
    out.extend_from_slice(&header);
    out.extend_from_slice(data);
    out
}

fn write(path: &Path, bytes: &[u8]) {
    std::fs::write(path, bytes).unwrap();
}

fn sha_of(bytes: &[u8]) -> String {
    hex(&Sha256::digest(bytes))
}

fn roundtrip(dir: &TempDir, base_img: &[u8], ft_img: &[u8], tag: &str) -> Vec<u8> {
    let base = dir.path(&format!("{tag}-base.safetensors"));
    let ft = dir.path(&format!("{tag}-ft.safetensors"));
    let delta = dir.path(&format!("{tag}-ft_delta_base.znn"));
    let out = dir.path(&format!("{tag}-restored.safetensors"));
    write(&base, base_img);
    write(&ft, ft_img);
    let c = delta_compress(&base, &ft, &delta, &JobOpts::default(), &Hooks::default())
        .expect("delta compress");
    // legacy contract: originalBytes = the PADDED rendering length =
    // 8 + max(header lens) + data len = the longer of the two images
    assert_eq!(
        c.stats.original_bytes as usize,
        base_img.len().max(ft_img.len()),
        "stats shape"
    );
    assert_eq!(
        c.stats.compressed_bytes,
        std::fs::metadata(&delta).unwrap().len()
    );
    // sidecar committed beside the delta
    let sidecar = sidecar_path(&delta);
    let raw = std::fs::read_to_string(&sidecar).expect("sidecar exists");
    let meta = parse_sidecar(&raw);
    assert_eq!(meta.ft_sha256.as_deref(), Some(sha_of(ft_img).as_str()));

    let d = delta_decompress(
        &base,
        &delta,
        &out,
        &meta,
        &JobOpts::default(),
        &Hooks::default(),
    )
    .expect("delta decompress");
    assert_eq!(d.verified, Verified::Sha256);
    assert_eq!(
        d.stats.original_bytes as usize,
        ft_img.len(),
        "restored size = the ORIGINAL ft file"
    );
    assert_eq!(d.stats.compressed_bytes, c.stats.compressed_bytes);
    let restored = std::fs::read(&out).unwrap();
    assert_eq!(restored, ft_img, "byte-exact restoration ({tag})");
    // no leftovers
    assert!(!tmp_sibling(&delta).exists());
    restored
}

/// The Python-side sidecar reader stand-in (json → DeltaMeta).
fn parse_sidecar(raw: &str) -> DeltaMeta {
    let v: serde_json::Value = serde_json::from_str(raw).unwrap();
    DeltaMeta {
        base_pad: v["basePad"].as_u64().unwrap(),
        ft_pad: v["ftPad"].as_u64().unwrap(),
        ft_sha256: v["ftSha256"].as_str().map(str::to_owned),
    }
}

// ---------------------------------------------------------------------------
// Round-trips (K: delta 往復 byte-exact、検証付き)
// ---------------------------------------------------------------------------

#[test]
fn roundtrip_same_header_lengths() {
    let dir = TempDir::new("same");
    let data = noisy_bytes(300_000, 7);
    let mut ft_data = data.clone();
    for (i, b) in ft_data.iter_mut().enumerate().take(20_000) {
        *b ^= (i % 251) as u8; // the "fine-tune drift"
    }
    let base = st_image(64, &data);
    let ft = st_image(64, &ft_data);
    roundtrip(&dir, &base, &ft, "same");
}

#[test]
fn roundtrip_padded_headers_both_directions() {
    let dir = TempDir::new("pad");
    let data = noisy_bytes(200_000, 11);
    let mut ft_data = data.clone();
    for b in ft_data.iter_mut().take(5_000) {
        *b = b.wrapping_add(3);
    }
    // ft header LONGER (base gets padded) and SHORTER (ft gets padded)
    roundtrip(
        &dir,
        &st_image(80, &data),
        &st_image(300, &ft_data),
        "ft-longer",
    );
    roundtrip(
        &dir,
        &st_image(300, &data),
        &st_image(80, &ft_data),
        "base-longer",
    );
}

#[test]
fn roundtrip_identical_files_compresses_tiny() {
    let dir = TempDir::new("ident");
    let img = st_image(64, &noisy_bytes(500_000, 3));
    let base = dir.path("base.safetensors");
    let ft = dir.path("ft.safetensors");
    let delta = dir.path("d.znn");
    write(&base, &img);
    write(&ft, &img);
    let c = delta_compress(&base, &ft, &delta, &JobOpts::default(), &Hooks::default()).unwrap();
    // XOR of identical renderings is all-zero: huff0 crushes it
    assert!(
        c.stats.compressed_bytes * 50 < c.stats.original_bytes,
        "identical-file delta must be <2% of the rendering, got {}",
        c.stats.compressed_bytes
    );
    roundtrip(&dir, &img, &img, "ident");
}

// ---------------------------------------------------------------------------
// Plan §6.2 Phase 3: the Appendix-C SEGFAULT class, pinned end-to-end.
// The C core SEGFAULTs (NULL-plane write) whenever the final 256 KiB
// compression chunk of the 4-plane path is 1–3 bytes; delta padding makes
// EVERY remainder reachable with real files (Phase 0 BENCH §4.3 proved the
// production path hits it). The Rust codec must complete normally.
// ---------------------------------------------------------------------------

#[test]
fn segfault_class_totals_roundtrip() {
    let dir = TempDir::new("segv");
    let header_len = 64;
    for k in [1usize, 2, 3] {
        // total = 8 + header + data ≡ k (mod 256 KiB), total > 256 KiB
        let total = 262_144 + k;
        let data_len = total - 8 - header_len;
        let data = noisy_bytes(data_len, 100 + k as u32);
        let mut ft_data = data.clone();
        for b in ft_data.iter_mut().take(1_000) {
            *b = b.wrapping_add(1);
        }
        let tag = format!("segv{k}");
        roundtrip(
            &dir,
            &st_image(header_len, &data),
            &st_image(header_len, &ft_data),
            &tag,
        );
    }
    // ...and across the 1 MiB streaming boundary (the final chunk of the
    // LAST container lands on 1–3 bytes there too)
    let total = 3 * 1_048_576 + 2;
    let data_len = total - 8 - header_len;
    let data = noisy_bytes(data_len, 77);
    roundtrip(
        &dir,
        &st_image(header_len, &data),
        &st_image(header_len, &data),
        "segv-3mb",
    );
}

// ---------------------------------------------------------------------------
// Wire format (official streaming chain)
// ---------------------------------------------------------------------------

#[test]
fn output_is_the_official_streaming_chain() {
    let dir = TempDir::new("chain");
    // 2.5 MiB rendering → three containers (1+1+0.5 MiB)
    let total_target = 2 * STREAMING_CHUNK + STREAMING_CHUNK / 2;
    let header_len = 64;
    let data = noisy_bytes(total_target - 8 - header_len, 5);
    let base = dir.path("base.safetensors");
    let ft = dir.path("ft.safetensors");
    let delta = dir.path("d.znn");
    write(&base, &st_image(header_len, &data));
    write(&ft, &st_image(header_len, &data));
    delta_compress(&base, &ft, &delta, &JobOpts::default(), &Hooks::default()).unwrap();
    let bytes = std::fs::read(&delta).unwrap();

    let mut off = 0usize;
    let mut rendered = 0usize;
    let mut containers = 0usize;
    while off < bytes.len() {
        let hdr = ZnHeader::decode(&bytes[off..]).expect("container header");
        assert_eq!(&bytes[off..off + 2], b"ZN");
        assert_eq!(hdr.version, ZNN_VERSION);
        assert_eq!(hdr.byte_reorder, 220, "float32 4-plane mode");
        assert_eq!(hdr.bit_reorder, 1);
        assert_eq!(hdr.method, METHOD_HUFFMAN);
        assert_eq!(hdr.input_format, InputFormat::Byte);
        assert_eq!(hdr.delta_compressed_type, DELTA_TYPE_BYTE);
        assert_eq!(hdr.lossy, [0, 0, 0]);
        assert!(hdr.streaming, "official streaming form");
        assert_eq!(hdr.streaming_chunk_log2, DELTA_CHUNK_LOG2);
        assert_eq!(hdr.compression_chunk_log2, DEFAULT_CHUNK_LOG2);
        assert_eq!(hdr.dtype_code, dtype::FLOAT32);
        let clen = usize::try_from(hdr.comp_len_field).unwrap();
        assert!(
            clen >= HEADER_LEN && off + clen <= bytes.len(),
            "chain bounds"
        );
        let expect_len = (total_target - rendered).min(STREAMING_CHUNK);
        assert_eq!(hdr.original_len as usize, expect_len, "chunk original_len");
        off += clen;
        rendered += expect_len;
        containers += 1;
    }
    assert_eq!(containers, 3, "2.5 MiB → three streaming containers");
    assert_eq!(off, bytes.len(), "chain spans the file exactly");
}

// ---------------------------------------------------------------------------
// The legacy single-container form (files the Python path / the official
// non-streaming byte API produced) must restore natively.
// ---------------------------------------------------------------------------

#[test]
fn single_container_legacy_files_restore() {
    let dir = TempDir::new("legacy");
    let header_len = 96; // base header longer → ft padded (ftPad > 0)
    let data = noisy_bytes(400_000, 9);
    let mut ft_data = data.clone();
    for b in ft_data.iter_mut().take(2_000) {
        *b = b.wrapping_add(7);
    }
    let base_img = st_image(header_len, &data);
    let ft_img = st_image(64, &ft_data);
    let base = dir.path("base.safetensors");
    let ft = dir.path("ft.safetensors");
    write(&base, &base_img);
    write(&ft, &ft_img);

    // Build the legacy artifact BY HAND: the padded renderings, whole-file
    // XOR, ONE non-streaming container (exactly zipnn.py's is_streaming=
    // False delta output).
    let base_pad = 0u64; // base header is the longer one
    let ft_pad = (header_len - 64) as u64;
    let render = |img: &[u8], pad: u64| -> Vec<u8> {
        let (hlen, header, data) = split_raw(img).unwrap();
        let mut out = Vec::new();
        out.extend_from_slice(&(hlen + pad).to_le_bytes());
        out.extend_from_slice(header);
        out.extend_from_slice(&vec![b' '; pad as usize]);
        out.extend_from_slice(data);
        out
    };
    let base_r = render(&base_img, base_pad);
    let ft_r = render(&ft_img, ft_pad);
    assert_eq!(base_r.len(), ft_r.len());
    let xor: Vec<u8> = ft_r.iter().zip(&base_r).map(|(a, b)| a ^ b).collect();
    let header = ZnHeader {
        version: ZNN_VERSION,
        byte_reorder: 220,
        bit_reorder: 1,
        method: METHOD_HUFFMAN,
        input_format: InputFormat::Byte,
        delta_compressed_type: DELTA_TYPE_BYTE,
        lossy: [0, 0, 0],
        streaming: false, // the legacy single-container form
        streaming_chunk_log2: 0,
        compression_chunk_log2: DEFAULT_CHUNK_LOG2,
        dtype_code: dtype::FLOAT32,
        original_len: xor.len() as u64,
        comp_len_field: 0,
    };
    let params = CoreParams {
        num_buf: 4,
        bit_reorder: 1,
        byte_reorder: 220,
        chunk: DEFAULT_CHUNK,
        threshold: DEFAULT_THRESHOLD,
        threads: 0,
    };
    let artifact = codec::zipnn_core(&header.encode(), &xor, &params).unwrap();
    let delta = dir.path("legacy.znn");
    write(&delta, &artifact);

    // Legacy sidecar (no ftSha256) → verification skipped with a note
    let meta = DeltaMeta {
        base_pad,
        ft_pad,
        ft_sha256: None,
    };
    let out = dir.path("restored.safetensors");
    let d = delta_decompress(
        &base,
        &delta,
        &out,
        &meta,
        &JobOpts::default(),
        &Hooks::default(),
    )
    .expect("legacy single-container restore");
    assert_eq!(d.verified, Verified::Skipped);
    assert!(
        d.warnings
            .iter()
            .any(|w| w.contains("verification skipped"))
    );
    assert_eq!(std::fs::read(&out).unwrap(), ft_img, "byte-exact");
    assert_eq!(d.stats.original_bytes as usize, ft_img.len());
    assert_eq!(d.stats.compressed_bytes as usize, artifact.len());
}

// ---------------------------------------------------------------------------
// Legacy error wording (UI contract — Plan §4.5-6)
// ---------------------------------------------------------------------------

#[test]
fn data_size_mismatch_uses_the_legacy_wording() {
    let dir = TempDir::new("mismatch");
    let base = dir.path("base.safetensors");
    let ft = dir.path("ft.safetensors");
    write(&base, &st_image(64, &noisy_bytes(1_000, 1)));
    write(&ft, &st_image(64, &noisy_bytes(1_004, 2)));
    let delta = dir.path("d.znn");
    let e = delta_compress(&base, &ft, &delta, &JobOpts::default(), &Hooks::default())
        .expect_err("must fail");
    assert_eq!(
        e.to_string(),
        "the two models have different tensor data sizes (1000 vs 1004 bytes): \
         delta compression only works between a base and a fine-tune with the \
         exact same architecture and tensor layout"
    );
    assert!(!delta.exists());
}

#[test]
fn non_delta_container_uses_the_legacy_wording() {
    let dir = TempDir::new("notdelta");
    let base = dir.path("base.safetensors");
    write(&base, &st_image(64, &noisy_bytes(1_000, 1)));
    // a plain (byte9=0) tensor-style container
    let header = ZnHeader {
        version: ZNN_VERSION,
        byte_reorder: 220,
        bit_reorder: 1,
        method: METHOD_HUFFMAN,
        input_format: InputFormat::Byte,
        delta_compressed_type: 0,
        lossy: [0, 0, 0],
        streaming: false,
        streaming_chunk_log2: 0,
        compression_chunk_log2: DEFAULT_CHUNK_LOG2,
        dtype_code: dtype::FLOAT32,
        original_len: 8,
        comp_len_field: 0,
    };
    let params = CoreParams {
        num_buf: 4,
        bit_reorder: 1,
        byte_reorder: 220,
        chunk: DEFAULT_CHUNK,
        threshold: DEFAULT_THRESHOLD,
        threads: 0,
    };
    let artifact = codec::zipnn_core(&header.encode(), &[0u8; 8], &params).unwrap();
    let delta = dir.path("plain.znn");
    write(&delta, &artifact);
    let out = dir.path("o.safetensors");
    let e = delta_decompress(
        &base,
        &delta,
        &out,
        &DeltaMeta::default(),
        &JobOpts::default(),
        &Hooks::default(),
    )
    .expect_err("must fail");
    assert_eq!(
        e.to_string(),
        "The data wasn't compressed using delta compression and you're trying to delta-decompress it."
    );
    assert!(!out.exists());
}

#[test]
fn length_mismatches_use_the_legacy_wording() {
    let dir = TempDir::new("lenmis");
    // (a) chain SHORTER than the base rendering (truncated delta file)
    let base_img = st_image(64, &noisy_bytes(3 * STREAMING_CHUNK, 4));
    let base = dir.path("base.safetensors");
    let ft = dir.path("ft.safetensors");
    write(&base, &base_img);
    write(&ft, &base_img);
    let delta = dir.path("d.znn");
    delta_compress(&base, &ft, &delta, &JobOpts::default(), &Hooks::default()).unwrap();
    let full = std::fs::read(&delta).unwrap();
    // keep only the first container → the chain decodes less than the total
    let first_len = usize::try_from(u64::from_le_bytes(full[24..32].try_into().unwrap())).unwrap();
    let truncated = dir.path("trunc.znn");
    write(&truncated, &full[..first_len]);
    let meta = parse_sidecar(&std::fs::read_to_string(sidecar_path(&delta)).unwrap());
    let out = dir.path("o.safetensors");
    let e = delta_decompress(
        &base,
        &truncated,
        &out,
        &meta,
        &JobOpts::default(),
        &Hooks::default(),
    )
    .expect_err("truncated chain must fail");
    assert_eq!(e.to_string(), MSG_LEN_MISMATCH);
    assert!(!out.exists() && !tmp_sibling(&out).exists());

    // (b) a container declaring MORE than the base rendering expects —
    // refused BEFORE allocation (hostile-header cap, Plan §4.4.2) with the
    // legacy wording
    let mut bomb = full.clone();
    // first container header: original_len → u64::MAX
    bomb[16..24].copy_from_slice(&u64::MAX.to_le_bytes());
    let bomb_path = dir.path("bomb.znn");
    write(&bomb_path, &bomb);
    let e = delta_decompress(
        &base,
        &bomb_path,
        &out,
        &meta,
        &JobOpts::default(),
        &Hooks::default(),
    )
    .expect_err("allocation bomb must fail");
    assert_eq!(e.to_string(), MSG_LEN_MISMATCH);
}

// ---------------------------------------------------------------------------
// Integrity pipeline (Plan §4.4.3): ftSha256, .corrupt retreat, paranoid
// ---------------------------------------------------------------------------

#[test]
fn wrong_sha_retreats_to_corrupt_and_keeps_the_delta() {
    let dir = TempDir::new("corrupt");
    let data = noisy_bytes(100_000, 21);
    let base = dir.path("base.safetensors");
    let ft = dir.path("ft.safetensors");
    write(&base, &st_image(64, &data));
    write(&ft, &st_image(64, &data));
    let delta = dir.path("d.znn");
    delta_compress(&base, &ft, &delta, &JobOpts::default(), &Hooks::default()).unwrap();
    let mut meta = parse_sidecar(&std::fs::read_to_string(sidecar_path(&delta)).unwrap());
    meta.ft_sha256 = Some("0".repeat(64)); // a sidecar that does not match

    let out = dir.path("o.safetensors");
    let delta_before = std::fs::read(&delta).unwrap();
    let e = delta_decompress(
        &base,
        &delta,
        &out,
        &meta,
        &JobOpts::default(),
        &Hooks::default(),
    )
    .expect_err("must fail verification");
    let msg = e.to_string();
    assert!(msg.contains("does not match ftSha256"), "{msg}");
    assert!(msg.contains(".corrupt"), "{msg}");
    // the failed restore is a diagnostic; the delta is KEPT; dst absent
    let corrupt = corrupt_path(&out);
    assert!(corrupt.exists(), ".corrupt retreat");
    assert!(!out.exists());
    assert_eq!(std::fs::read(&delta).unwrap(), delta_before, "delta kept");
    assert!(!tmp_sibling(&out).exists());
}

#[test]
fn tampered_delta_never_restores_silently() {
    let dir = TempDir::new("tamper");
    let data = noisy_bytes(200_000, 33);
    let mut ft_data = data.clone();
    for b in ft_data.iter_mut().take(1_000) {
        *b ^= 0xFF;
    }
    let base = dir.path("base.safetensors");
    let ft = dir.path("ft.safetensors");
    write(&base, &st_image(64, &data));
    write(&ft, &st_image(64, &ft_data));
    let delta = dir.path("d.znn");
    delta_compress(&base, &ft, &delta, &JobOpts::default(), &Hooks::default()).unwrap();
    let meta = parse_sidecar(&std::fs::read_to_string(sidecar_path(&delta)).unwrap());

    // flip payload bytes far enough in to hit plane data of the container
    let mut bytes = std::fs::read(&delta).unwrap();
    let n = bytes.len();
    for i in (n / 2..n).step_by(997) {
        bytes[i] ^= 0x5A;
    }
    let tampered = dir.path("tampered.znn");
    write(&tampered, &bytes);
    let out = dir.path("o.safetensors");
    let r = delta_decompress(
        &base,
        &tampered,
        &out,
        &meta,
        &JobOpts::default(),
        &Hooks::default(),
    );
    match r {
        Err(e) => {
            // either the codec rejects the payload or the sha catches it —
            // but the restore must NOT exist as a valid file
            assert!(!out.exists(), "no silent corrupt restore ({e})");
        }
        Ok(o) => panic!(
            "tampered delta restored successfully?! verified={:?}",
            o.verified
        ),
    }
    assert!(std::fs::read(&delta).is_ok(), "original delta untouched");
}

#[test]
fn paranoid_mode_verifies_before_the_rename() {
    let dir = TempDir::new("paranoid");
    let data = noisy_bytes(150_000, 44);
    let mut ft_data = data.clone();
    for b in ft_data.iter_mut().take(500) {
        *b = b.wrapping_add(1);
    }
    let base = dir.path("base.safetensors");
    let ft = dir.path("ft.safetensors");
    write(&base, &st_image(64, &data));
    write(&ft, &st_image(80, &ft_data));
    let delta = dir.path("d.znn");
    let opts = JobOpts {
        paranoid: true,
        ..JobOpts::default()
    };
    let c = delta_compress(&base, &ft, &delta, &opts, &Hooks::default()).expect("paranoid ok");
    assert!(c.stats.compressed_bytes > 0);
    // and the artifact round-trips like any other
    let meta = parse_sidecar(&std::fs::read_to_string(sidecar_path(&delta)).unwrap());
    let out = dir.path("o.safetensors");
    delta_decompress(
        &base,
        &delta,
        &out,
        &meta,
        &JobOpts::default(),
        &Hooks::default(),
    )
    .unwrap();
    assert_eq!(std::fs::read(&out).unwrap(), st_image(80, &ft_data));
}

// ---------------------------------------------------------------------------
// Sidecar degradation (legacy files) + hostile sidecars
// ---------------------------------------------------------------------------

#[test]
fn missing_sidecar_pads_fail_with_the_legacy_wording() {
    let dir = TempDir::new("nosidecar");
    let data = noisy_bytes(100_000, 55);
    let base = dir.path("base.safetensors");
    let ft = dir.path("ft.safetensors");
    // headers of DIFFERENT lengths → non-zero pads are required
    write(&base, &st_image(64, &data));
    write(&ft, &st_image(200, &data));
    let delta = dir.path("d.znn");
    delta_compress(&base, &ft, &delta, &JobOpts::default(), &Hooks::default()).unwrap();
    std::fs::remove_file(sidecar_path(&delta)).unwrap();

    // meta = {} like the legacy reader on a missing sidecar
    let out = dir.path("o.safetensors");
    let e = delta_decompress(
        &base,
        &delta,
        &out,
        &DeltaMeta::default(),
        &JobOpts::default(),
        &Hooks::default(),
    )
    .expect_err("padded delta without its sidecar must not restore garbage");
    assert_eq!(e.to_string(), MSG_LEN_MISMATCH);
    assert!(!out.exists());
}

#[test]
fn absurd_sidecar_pad_is_a_clean_error() {
    let dir = TempDir::new("badpad");
    let data = noisy_bytes(10_000, 66);
    let base = dir.path("base.safetensors");
    write(&base, &st_image(64, &data));
    let delta = dir.path("d.znn"); // any delta-shaped file; the pad check fires first
    write(&delta, &[0u8; 64]);
    let out = dir.path("o.safetensors");
    let meta = DeltaMeta {
        base_pad: u64::MAX,
        ft_pad: 0,
        ft_sha256: None,
    };
    let e = delta_decompress(
        &base,
        &delta,
        &out,
        &meta,
        &JobOpts::default(),
        &Hooks::default(),
    )
    .expect_err("absurd pad");
    assert!(e.to_string().contains("absurdly large"), "{e}");
}

// ---------------------------------------------------------------------------
// Cancellation / guards
// ---------------------------------------------------------------------------

#[test]
fn cancel_leaves_no_partial_output() {
    let dir = TempDir::new("cancel");
    let data = noisy_bytes(2 * STREAMING_CHUNK, 88);
    let base = dir.path("base.safetensors");
    let ft = dir.path("ft.safetensors");
    write(&base, &st_image(64, &data));
    write(&ft, &st_image(64, &data));
    let delta = dir.path("d.znn");
    let flag = AtomicBool::new(true); // cancelled before the first chunk
    let hooks = Hooks {
        progress: None,
        cancel: Some(&flag),
    };
    let e = delta_compress(&base, &ft, &delta, &JobOpts::default(), &hooks).expect_err("cancelled");
    assert!(matches!(e, StError::Cancelled), "{e}");
    assert!(!delta.exists());
    assert!(!tmp_sibling(&delta).exists());
    assert!(!sidecar_path(&delta).exists());

    // decompress side too
    flag.store(false, Ordering::Relaxed);
    delta_compress(&base, &ft, &delta, &JobOpts::default(), &Hooks::default()).unwrap();
    let meta = parse_sidecar(&std::fs::read_to_string(sidecar_path(&delta)).unwrap());
    flag.store(true, Ordering::Relaxed);
    let out = dir.path("o.safetensors");
    let e = delta_decompress(&base, &delta, &out, &meta, &JobOpts::default(), &hooks)
        .expect_err("cancelled");
    assert!(matches!(e, StError::Cancelled), "{e}");
    assert!(!out.exists() && !tmp_sibling(&out).exists());
}

#[test]
fn existing_targets_are_refused() {
    let dir = TempDir::new("exists");
    let data = noisy_bytes(1_000, 99);
    let base = dir.path("base.safetensors");
    let ft = dir.path("ft.safetensors");
    write(&base, &st_image(64, &data));
    write(&ft, &st_image(64, &data));
    let delta = dir.path("d.znn");
    write(&delta, b"sentinel");
    let e = delta_compress(&base, &ft, &delta, &JobOpts::default(), &Hooks::default())
        .expect_err("dst exists");
    assert!(e.to_string().contains("target already exists"), "{e}");
    assert_eq!(std::fs::read(&delta).unwrap(), b"sentinel");

    let out = dir.path("o.safetensors");
    write(&out, b"sentinel");
    let e = delta_decompress(
        &base,
        &delta,
        &out,
        &DeltaMeta::default(),
        &JobOpts::default(),
        &Hooks::default(),
    )
    .expect_err("dst exists");
    assert!(e.to_string().contains("target already exists"), "{e}");
    assert_eq!(std::fs::read(&out).unwrap(), b"sentinel");
}

#[test]
fn malformed_inputs_are_errors_not_panics() {
    let dir = TempDir::new("hostile");
    let base = dir.path("base.safetensors");
    write(&base, &st_image(64, &noisy_bytes(4_096, 123)));
    let out = dir.path("o.safetensors");
    for (i, bytes) in [
        vec![],             // empty
        b"ZN".to_vec(),     // short
        noisy_bytes(33, 7), // garbage ≥32B
        {
            // nonsense version (9.9.9) with a full 40-byte body
            let mut v = b"ZN\x09\x09\x09".to_vec();
            v.resize(40, 0xFF);
            v
        },
    ]
    .iter()
    .enumerate()
    {
        let delta = dir.path(&format!("h{i}.znn"));
        write(&delta, bytes);
        let r = delta_decompress(
            &base,
            &delta,
            &out,
            &DeltaMeta::default(),
            &JobOpts::default(),
            &Hooks::default(),
        );
        assert!(r.is_err(), "hostile delta {i} must error");
        assert!(!out.exists());
    }
    // not-a-safetensors base
    let junk = dir.path("junk.safetensors");
    write(&junk, b"12345");
    let ft = dir.path("ft.safetensors");
    write(&ft, &st_image(64, &noisy_bytes(100, 5)));
    let delta = dir.path("d.znn");
    assert!(delta_compress(&junk, &ft, &delta, &JobOpts::default(), &Hooks::default()).is_err());
    assert!(delta_compress(&ft, &junk, &delta, &JobOpts::default(), &Hooks::default()).is_err());
}

// ---------------------------------------------------------------------------
// Progress + sidecar shape
// ---------------------------------------------------------------------------

#[test]
fn progress_counts_chunks_and_containers() {
    let dir = TempDir::new("progress");
    let total_target = 2 * STREAMING_CHUNK + 4096;
    let data = noisy_bytes(total_target - 8 - 64, 2);
    let base = dir.path("base.safetensors");
    let ft = dir.path("ft.safetensors");
    write(&base, &st_image(64, &data));
    write(&ft, &st_image(64, &data));
    let delta = dir.path("d.znn");
    let pc = Progress::new(1);
    let hc = Hooks {
        progress: Some(&pc),
        cancel: None,
    };
    delta_compress(&base, &ft, &delta, &JobOpts::default(), &hc).unwrap();
    let (done, total, phase) = pc.snapshot();
    assert_eq!((done, total), (3, 3), "2×1MiB + 4KiB → three chunks");
    assert_eq!(phase, Phase::Done);

    let meta = parse_sidecar(&std::fs::read_to_string(sidecar_path(&delta)).unwrap());
    let out = dir.path("o.safetensors");
    let pd = Progress::new(1);
    let hd = Hooks {
        progress: Some(&pd),
        cancel: None,
    };
    delta_decompress(&base, &delta, &out, &meta, &JobOpts::default(), &hd).unwrap();
    let (done, total, phase) = pd.snapshot();
    assert_eq!((done, total), (3, 3), "three streaming containers");
    assert_eq!(phase, Phase::Done);
}

#[test]
fn sidecar_json_keeps_the_legacy_key_order() {
    let m = DeltaMeta {
        base_pad: 3,
        ft_pad: 0,
        ft_sha256: Some("ab".repeat(32)),
    };
    assert_eq!(
        m.sidecar_json(),
        format!(
            "{{\"basePad\":3,\"ftPad\":0,\"ftSha256\":\"{}\"}}",
            "ab".repeat(32)
        )
    );
    let legacy = DeltaMeta {
        base_pad: 1,
        ft_pad: 2,
        ft_sha256: None,
    };
    assert_eq!(legacy.sidecar_json(), "{\"basePad\":1,\"ftPad\":2}");
    // and it parses with any JSON reader
    let p = parse_sidecar(&m.sidecar_json());
    assert_eq!(p, m);
}

// ---------------------------------------------------------------------------
// The official-toolchain method byte (zipnn.py API default AUTO=0, the delta
// CLI's --method choices) — delta containers must decode regardless, exactly
// like the official decompressor which ignores byte 7 (primary sources in
// `ZnHeader::decode_delta`). The TENSOR path keeps the strict Phase-2 gate.
// ---------------------------------------------------------------------------

#[test]
fn delta_accepts_the_official_method_defaults() {
    let dir = TempDir::new("methods");
    let data = noisy_bytes(50_000, 12);
    let base = dir.path("base.safetensors");
    let ft = dir.path("ft.safetensors");
    write(&base, &st_image(64, &data));
    write(&ft, &st_image(64, &data));

    // hand-build single-container deltas with method ∈ {0(AUTO), 1, 2(ZSTD
    // label — the official float32 byte path still wrote Huffman payloads)}
    for method in [0u8, 1, 2] {
        let base_img = st_image(64, &data);
        let render_len = base_img.len();
        let xor = vec![0u8; render_len]; // ft == base → the XOR is zeros
        let header = ZnHeader {
            version: ZNN_VERSION,
            byte_reorder: 220,
            bit_reorder: 1,
            method,
            input_format: InputFormat::Byte,
            delta_compressed_type: DELTA_TYPE_BYTE,
            lossy: [0, 0, 0],
            streaming: false,
            streaming_chunk_log2: 0,
            compression_chunk_log2: DEFAULT_CHUNK_LOG2,
            dtype_code: dtype::FLOAT32,
            original_len: render_len as u64,
            comp_len_field: 0,
        };
        let params = CoreParams {
            num_buf: 4,
            bit_reorder: 1,
            byte_reorder: 220,
            chunk: DEFAULT_CHUNK,
            threshold: DEFAULT_THRESHOLD,
            threads: 0,
        };
        let artifact = codec::zipnn_core(&header.encode(), &xor, &params).unwrap();
        let delta = dir.path(&format!("m{method}.znn"));
        write(&delta, &artifact);
        let out = dir.path(&format!("m{method}.out"));
        let d = delta_decompress(
            &base,
            &delta,
            &out,
            &DeltaMeta::default(),
            &JobOpts::default(),
            &Hooks::default(),
        );
        assert!(d.is_ok(), "method {method}: {d:?}");
        assert_eq!(std::fs::read(&out).unwrap(), st_image(64, &data));
    }

    // the TENSOR-path gate stays strict (a method=0 container is refused
    // there — Plan Appendix B.1)
    let mut strict = [0u8; 64];
    strict[..2].copy_from_slice(b"ZN");
    strict[2] = 0;
    strict[3] = 5;
    strict[4] = 4;
    strict[7] = 0; // AUTO
    strict[8] = 1; // BYTE
    assert!(ZnHeader::decode(&strict).is_err());
    assert!(ZnHeader::decode_delta(&strict).is_ok());
}
