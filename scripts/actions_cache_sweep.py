#!/usr/bin/env python3
"""Prune dead GitHub Actions cache entries for this repository.

Why this exists (all numbers measured 2026-10-03):

* Actions caches are scoped per ref and capped at 10 GB per repository on every
  plan. Eviction deletes entries in last-access order (oldest first), and any
  entry untouched for 7 days is removed.
* A ``pull_request`` run writes into the ``refs/pull/N/merge`` scope, which the
  documentation says can only be restored by re-runs of that same PR. Once the
  PR is merged the entries are dead weight -- 2.51 GiB of the 9.65 GiB this
  repository was holding came from the single already-merged PR #29.
* A release tag run (``refs/tags/v*``) is dead the same way: caches cannot be
  restored across different tag names.
* Because a restore-key fallback also refreshes ``last_accessed_at``, the dead
  entries survive eviction while live branch caches get thrown out. That is what
  removed the weekly fuzz-long cache (7 ASan nightly targets rebuilding cold).
* ``Swatinem/rust-cache`` keys end in a hash of every Cargo.toml/Cargo.lock, so
  each dependency bump leaves the previous generation behind as an entry that
  can never win an exact match again -- 2.06 GiB here.

``native.yml``/``fuzz-long.yml`` now only *write* caches from main/dev
(``save-if``), which stops the growth. This script reclaims what is already dead
and keeps the two long-lived branches inside the cap without waiting for the
7-day expiry.

Modes::

    (no flag)    sweep every dead scope plus superseded key generations
    --ref REF    delete every entry in one scope (used on `pull_request: closed`)

Local use::

    GH_TOKEN=... python3 scripts/actions_cache_sweep.py --dry-run
    GH_TOKEN=... python3 scripts/actions_cache_sweep.py --apply
"""

from __future__ import annotations

import argparse
import collections
import datetime
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

GITHUB_API = "https://api.github.com"
# Per-repository cache cap (every plan; raising it is a paid opt-in).
LIMIT_BYTES = 10 * 2**30
# REST budget: 400 cache deletes per minute per repository.
DELETES_PER_MINUTE = 400

Cache = dict[str, Any]


def resolve_token() -> str:
    for name in ("GITHUB_TOKEN", "GH_TOKEN"):
        value = os.environ.get(name)
        if value:
            return value.strip()
    raise SystemExit("no credentials: set GITHUB_TOKEN (in CI) or GH_TOKEN (locally)")


def resolve_repo(explicit: str | None) -> str:
    slug = explicit or os.environ.get("GITHUB_REPOSITORY")
    if not slug:
        raise SystemExit("no repository: set GITHUB_REPOSITORY or pass --repo OWNER/NAME")
    return slug


class GitHub:
    """Minimal REST client (stdlib only - this runs on a bare ubuntu runner)."""

    def __init__(self, repo: str, token: str) -> None:
        self.base = f"{GITHUB_API}/repos/{repo}"
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "actions-cache-sweep",
        }

    def request(self, path: str, method: str = "GET") -> tuple[int, Any]:
        # S310 triage (NEO-PLAN-2026-004): self.base is the api.github.com
        # constant and `path` is assembled from this script's own fixed REST
        # routes; file:/custom schemes are unreachable (S310's actual concern).
        req = urllib.request.Request(self.base + path, method=method, headers=self.headers)  # noqa: S310
        try:
            with urllib.request.urlopen(req) as resp:  # noqa: S310
                body = resp.read().decode()
                return resp.status, (json.loads(body) if body else None)
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode()[:400]

    def list_caches(self) -> list[Cache]:
        entries: list[Cache] = []
        page = 1
        while True:
            query = f"/actions/caches?per_page=100&page={page}&sort=created_at&direction=asc"
            status, payload = self.request(query)
            if status != 200 or not isinstance(payload, dict):
                raise SystemExit(f"listing caches failed: HTTP {status} {payload}")
            entries.extend(payload["actions_caches"])
            if page * 100 >= payload["total_count"]:
                return entries
            page += 1

    def delete_cache(self, cache_id: int) -> tuple[int, Any]:
        return self.request(f"/actions/caches/{cache_id}", method="DELETE")

    def usage(self) -> str:
        status, payload = self.request("/actions/cache/usage")
        if status != 200 or not isinstance(payload, dict):
            return f"usage unavailable (HTTP {status})"
        size = payload["active_caches_size_in_bytes"]
        pct = size / LIMIT_BYTES * 100
        # This endpoint refreshes about every 5 minutes, so immediately after a
        # sweep it still reports the pre-delete numbers.
        return f"{payload['active_caches_count']} entries, {size / 2**30:.3f} GiB ({pct:.1f}% of 10 GiB; ~5 min lag)"


def split_generation(key: str) -> tuple[str, str]:
    """Split a cache key into (everything before the last dash, the last segment).

    rust-cache keys look like ``v0-rust-<job>-<os>-<arch>-<job-hash>-<env-hash>``
    where the env hash is the generation. Splitting on the final dash is
    generator-agnostic: setup-uv and setup-node keys end in a lockfile hash the
    same way, and a key without a dash has no generation and is never stale.
    """
    head, _, generation = key.rpartition("-")
    return (head, generation) if head else (key, "")


def parse_ts(value: Any) -> datetime.datetime:
    return datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def select_victims(
    caches: list[Cache],
    *,
    only_ref: str | None,
    older_than_days: int | None,
    keep_stale: bool,
) -> dict[int, tuple[str, Cache]]:
    """Return ``{cache_id: (reason, entry)}`` for the entries that should go."""
    victims: dict[int, tuple[str, Cache]] = {}
    now = datetime.datetime.now(datetime.UTC)

    def mark(reason: str, entry: Cache) -> None:
        previous = victims.get(entry["id"])
        victims[entry["id"]] = (reason if previous is None else f"{previous[0]}+{reason}", entry)

    for entry in caches:
        ref: str = entry["ref"]
        if only_ref is not None:
            if ref == only_ref:
                mark("ref", entry)
            continue
        if ref.startswith("refs/pull/"):
            # Restorable only by re-runs of that PR; dead once it is closed.
            mark("pull", entry)
        elif ref.startswith("refs/tags/"):
            # Never restorable from another tag.
            mark("tag", entry)

    if only_ref is None and not keep_stale:
        groups: dict[tuple[str, str], list[Cache]] = collections.defaultdict(list)
        for entry in caches:
            if entry["id"] in victims:
                continue
            head, generation = split_generation(entry["key"])
            if generation:
                groups[(entry["ref"], head)].append(entry)
        for entries in groups.values():
            entries.sort(key=lambda item: parse_ts(item["created_at"]))
            # Keep the newest generation of each (scope, key family). The rest
            # can only ever be a partial-match fallback for a key that a newer
            # entry now matches exactly.
            for entry in entries[:-1]:
                mark("stale", entry)

    if only_ref is None and older_than_days is not None:
        for entry in caches:
            if entry["id"] in victims:
                continue
            if (now - parse_ts(entry["last_accessed_at"] or entry["created_at"])).days >= older_than_days:
                mark("unused", entry)

    return victims


def summarise(caches: list[Cache], victims: dict[int, tuple[str, Cache]]) -> str:
    total = sum(entry["size_in_bytes"] for entry in caches)
    lines = [f"caches now: {len(caches)} entries, {total / 2**30:.3f} GiB ({total / LIMIT_BYTES * 100:.1f}% of 10 GiB)"]
    if not victims:
        lines.append("nothing to prune")
        return "\n".join(lines)
    reclaim = 0
    for reason, entry in sorted(victims.values(), key=lambda item: -item[1]["size_in_bytes"]):
        size = entry["size_in_bytes"]
        reclaim += size
        lines.append(
            f"  [{reason:11s}] {size / 2**20:8.1f} MiB  id={entry['id']:<12} {entry['ref']:<22} {entry['key'][:58]}"
        )
    lines.append(
        f"pruning {len(victims)} entries / {reclaim / 2**30:.3f} GiB -> "
        f"{(total - reclaim) / 2**30:.3f} GiB ({(total - reclaim) / LIMIT_BYTES * 100:.1f}%)"
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", help="OWNER/NAME (default: $GITHUB_REPOSITORY)")
    parser.add_argument("--ref", help="prune exactly this scope, e.g. refs/pull/29/merge")
    parser.add_argument("--older-than-days", type=int, help="also prune entries unused for at least N days")
    parser.add_argument("--keep-stale", action="store_true", help="do not prune superseded key generations")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--apply", action="store_true", help="delete the selected entries (the default)")
    group.add_argument("--dry-run", action="store_true", help="report only, delete nothing")
    args = parser.parse_args(argv)

    gh = GitHub(resolve_repo(args.repo), resolve_token())
    caches = gh.list_caches()
    victims = select_victims(
        caches,
        only_ref=args.ref,
        older_than_days=args.older_than_days,
        keep_stale=args.keep_stale,
    )
    report = summarise(caches, victims)
    print(report)

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as handle:
            handle.write(f"### Actions cache sweep\n\n```\n{report}\n```\n")

    if args.dry_run:
        print("\n(dry-run: nothing deleted)")
        return 0
    if not victims:
        return 0
    if len(victims) > DELETES_PER_MINUTE:
        print(f"warning: {len(victims)} deletes exceeds the {DELETES_PER_MINUTE}/min REST budget", file=sys.stderr)

    failed = 0
    for cache_id in sorted(victims):
        status, payload = gh.delete_cache(cache_id)
        if status != 204:
            failed += 1
            print(f"DELETE {cache_id} -> HTTP {status} {payload}", file=sys.stderr)
    print(f"deleted={len(victims) - failed} failed={failed}")
    print(f"usage endpoint: {gh.usage()}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
