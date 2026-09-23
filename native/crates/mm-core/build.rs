//! Embeds the current git commit into `MM_CORE_COMMIT_HASH` so
//! `mm_core.core_version()` can report `"x.y.z+commit"` (Plan §4.2.2).
//!
//! Resolution order: the `MM_CORE_COMMIT` environment variable (settable by
//! CI / `scripts/build-native.sh`), then `git rev-parse --short=9 HEAD`,
//! then the literal `"unknown"` (source tarballs without git metadata).

use std::{process::Command, str};

fn main() {
    println!("cargo:rerun-if-changed=build.rs");
    // Authoritative freshness channel: every artifact-producing invocation
    // (scripts/build-native.sh, the CI workflows) exports MM_CORE_COMMIT, and
    // this directive makes cargo re-run the script whenever that value moves.
    println!("cargo:rerun-if-env-changed=MM_CORE_COMMIT");
    // Best-effort fallback for bare local builds: re-run when HEAD moves
    // (branch switch / checkout). NOTE: a NEW COMMIT ON THE SAME BRANCH does
    // not change the .git/HEAD file, so this watch alone goes stale on
    // incremental builds — that is fine for local development and the reason
    // the env var above exists (all shipped artifacts set it).
    println!("cargo:rerun-if-changed=../../../.git/HEAD");
    println!("cargo:rustc-env=MM_CORE_COMMIT_HASH={}", commit_hash());
}

fn commit_hash() -> String {
    if let Ok(value) = std::env::var("MM_CORE_COMMIT") {
        if !value.is_empty() {
            return value;
        }
    }
    if let Ok(output) = Command::new("git")
        .args(["rev-parse", "--short=9", "HEAD"])
        .output()
    {
        if output.status.success() {
            if let Ok(hash) = str::from_utf8(&output.stdout) {
                let hash = hash.trim();
                if !hash.is_empty() {
                    return hash.to_owned();
                }
            }
        }
    }
    "unknown".to_owned()
}
