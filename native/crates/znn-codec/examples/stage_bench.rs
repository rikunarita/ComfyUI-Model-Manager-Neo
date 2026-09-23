//! Stage-level microbench for the compress pipeline on f16-like data.
use std::hint::black_box;
use std::time::Instant;
use znn_codec::{huf, planes, reorder::ReorderKind};

fn main() {
    let path = std::env::args()
        .nth(1)
        .unwrap_or_else(|| "/tmp/f16.in".into());
    let data = std::fs::read(&path).unwrap();
    let chunk = 262_144usize;
    let iters = 20;

    // (a) split2 plain over the whole file (2-plane, no reorder)
    let mut p0 = vec![0u8; chunk / 2];
    let mut p1 = vec![0u8; chunk / 2];
    let t0 = Instant::now();
    for it in 0..iters {
        let src = &data[(it % (data.len() / chunk)) * chunk..][..chunk];
        let mut ps: [&mut [u8]; 2] = [&mut p0, &mut p1];
        planes::split(src, &mut ps, ReorderKind::None).unwrap();
        black_box(&p0);
    }
    let dt = t0.elapsed().as_secs_f64() / iters as f64;
    println!(
        "split2-plain : {:.2} ms/chunk → {:.0} MB/s",
        dt * 1e3,
        chunk as f64 / dt / 1e6
    );

    // (b) split2 bf16 (fused reorder)
    let t0 = Instant::now();
    for it in 0..iters {
        let src = &data[(it % (data.len() / chunk)) * chunk..][..chunk];
        let mut ps: [&mut [u8]; 2] = [&mut p0, &mut p1];
        planes::split(src, &mut ps, ReorderKind::Bf16).unwrap();
        black_box(&p0);
    }
    let dt = t0.elapsed().as_secs_f64() / iters as f64;
    println!(
        "split2-bf16  : {:.2} ms/chunk → {:.0} MB/s",
        dt * 1e3,
        chunk as f64 / dt / 1e6
    );

    // (c) huf on the high-entropy plane (mantissa-low bytes: heuristic abort path)
    let src0 = &data[..chunk / 2];
    let t0 = Instant::now();
    for _ in 0..iters {
        let r = huf::compress_block(black_box(src0), src0.len() + 32).unwrap();
        black_box(r.is_some());
    }
    let dt = t0.elapsed().as_secs_f64() / iters as f64;
    println!(
        "huf(plane0=hi-entropy 128K): {:.2} ms → {:.0} MB/s (result {})",
        dt * 1e3,
        (chunk / 2) as f64 / dt / 1e6,
        if huf::compress_block(src0, src0.len() + 32)
            .unwrap()
            .is_some()
        {
            "block"
        } else {
            "raw/abort"
        }
    );

    // (d) huf on the low-entropy plane (sign|exp bytes: real encode path)
    let mut p1buf = vec![0u8; chunk / 2];
    {
        let mut p0buf = vec![0u8; chunk / 2];
        let mut ps: [&mut [u8]; 2] = [&mut p0buf, &mut p1buf];
        planes::split(&data[..chunk], &mut ps, ReorderKind::None).unwrap();
    }
    let t0 = Instant::now();
    let mut outb = 0;
    for _ in 0..iters {
        let r = huf::compress_block(black_box(&p1buf), p1buf.len() + 32).unwrap();
        outb = r.map(|v| v.len()).unwrap_or(0);
    }
    let dt = t0.elapsed().as_secs_f64() / iters as f64;
    println!(
        "huf(plane1=lo-entropy 128K): {:.2} ms → {:.0} MB/s (block {outb} B)",
        dt * 1e3,
        (chunk / 2) as f64 / dt / 1e6
    );

    // (e) join2 (decompress-side interleave)
    let mut dst = vec![0u8; chunk];
    let t0 = Instant::now();
    for _ in 0..iters {
        let ps: [&[u8]; 2] = [&p0, &p1buf];
        planes::join(&ps, &mut dst, ReorderKind::None).unwrap();
        black_box(&dst);
    }
    let dt = t0.elapsed().as_secs_f64() / iters as f64;
    println!(
        "join2-plain  : {:.2} ms/chunk → {:.0} MB/s",
        dt * 1e3,
        chunk as f64 / dt / 1e6
    );
}
