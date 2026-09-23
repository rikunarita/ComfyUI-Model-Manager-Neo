// standalone debug: replicate the failing roundtrip with prints
use znn_codec::fse::*;
fn rt(name: &str, count: &[u32], table_log: u32) {
    let total: usize = count.iter().map(|&c| c as usize).sum();
    let max_sv = (count.len() - 1) as u32;
    let (norm, log) = match normalize_count(count, total, max_sv, table_log).expect("normalize") {
        Some(v) => v,
        None => {
            println!("{name}: RLE skip");
            return;
        }
    };
    println!("{name}: norm={norm:?} log={log}");
    let dt = build_d_table(&norm, max_sv, log).expect("dt");
    let ct = build_c_table(&norm, max_sv, log).expect("ct");
    let mut payload_src = Vec::new();
    for (s, &c) in count.iter().enumerate() {
        if s as u32 <= max_sv && c > 0 {
            for _ in 0..c.min(7) {
                payload_src.push(s as u8);
            }
        }
    }
    if payload_src.len() < 3 {
        println!("{name}: payload too small");
        return;
    }
    let comp = compress_using_ctable(&ct, &payload_src, payload_src.len() + 64)
        .expect("c")
        .expect("fits");
    let mut out = vec![0u8; payload_src.len() + 3];
    match decompress_using_d_table(&dt, &comp, &mut out) {
        Ok(n) => {
            if out[..n] != payload_src[..] {
                println!("{name}: MISMATCH n={n} src_len={}", payload_src.len());
                println!("  src: {:?}", &payload_src[..payload_src.len().min(20)]);
                println!("  out: {:?}", &out[..n.min(20)]);
            } else {
                println!("{name}: OK n={n}");
            }
        }
        Err(e) => println!("{name}: DECOMP ERR {e}"),
    }
}
fn main() {
    rt("a", &[3, 5, 4, 2, 1, 1, 0, 0, 0, 0, 0, 0, 0], 6);
    rt("b", &[1, 1], 5);
    rt("c", &[60, 30, 15, 8, 4, 2, 1, 1], 6);
    rt("d", &[1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1], 6);
    rt("e", &[2, 1], 5);
    rt("f", &[200, 40, 10, 5, 1], 6);
    rt("g", &[2, 2, 2, 2], 5);
    rt("h", &[7, 5, 3, 1, 1, 1], 6);
    rt("i", &[1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1], 6);
    rt("j", &[1, 1, 0, 0, 1, 1], 5);
}
