# Security Policy

ComfyUI-Model-Manager-Neo runs inside your local ComfyUI instance: it browses,
downloads, uploads and compresses model files on your machine, talks to the
model hubs (Civitai, Hugging Face, ModelScope) with the API keys you provide,
and exposes its HTTP routes on ComfyUI's own local server. We take that
position — local software with network reach and user credentials — seriously.

## Supported Versions

The project is under active development. Only the latest release (and the
current `main` branch it is built from) receives security fixes; there are no
maintained older release lines.

## Reporting a Vulnerability

**Please do not open a public GitHub issue for a security problem.**

This repository uses GitHub's
[private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability):

1. Open the
   [Security Advisories](https://github.com/rikunarita/ComfyUI-Model-Manager-Neo/security/advisories)
   page of this repository.
2. Click **Report a vulnerability**.
3. Include the affected version or commit, step-by-step reproduction, the
   impact you observed or expect, and — if you have one — a suggested fix.

Expect an initial acknowledgement within about a week. Fixes are developed on
the `dev`/`main` branches; once a fix ships, the advisory is published (with
credit, if you would like it).

## Scope

Things we would treat as vulnerabilities include:

- Path traversal or unintended file read/write/delete through the extension's
  HTTP routes (the upload, download, rename/move, ZipNN, hygiene and preview
  paths).
- Memory-safety or parsing bugs in the Rust native core (`native/`) reachable
  from a malicious model file, `.znn.safetensors` archive, safetensors header
  or preview image. The codec denies `unsafe` by lint, carries seven
  continuous fuzz targets and verifies every restore against the SHA-256
  recorded at compression time — a new crash is still always news to us.
- Credential leakage: anything that would expose the hub API keys stored in
  the local, gitignored `private.key`, or send them anywhere other than the
  hub they belong to.
- Injection in the download/upload flows or the CI pipeline — e.g. a
  malicious model page, filename or workflow input achieving code execution.

Out of scope: vulnerabilities in ComfyUI itself (please report them
[upstream](https://github.com/comfyanonymous/ComfyUI)), issues that require
physical access to your machine, and findings in development tooling that
never ships to users.

## How This Repository Is Hardened

Security is gated in CI on every push and pull request (see the `Security`
workflow and GitHub's code-scanning tab):

- **CodeQL** — default setup with the extended query suite, covering the
  TypeScript/Vue frontend (including `.vue` single-file components), the
  Python backend, the Rust core (build mode `none`) and the GitHub Actions
  configuration itself.
- **OSV-Scanner** — audits all four dependency surfaces (`pnpm-lock.yaml`,
  `uv.lock`, `native/Cargo.lock`, `requirements.txt`) against OSV.dev; pull
  requests fail on any _newly introduced_ vulnerability.
- **Gitleaks** — secret scanning over the full git history (weekly) and every
  pull-request diff, beside GitHub's own secret scanning and push protection.
- **zizmor** — static security analysis of the CI configuration (template
  injection, unpinned actions, excessive permissions, cache poisoning); all
  third-party actions are SHA-pinned and kept current by Dependabot.
- **Ruff** (with the `S`/flake8-bandit family) and **eslint-plugin-security**
  lint the Python and TypeScript/Vue sources for security anti-patterns.
- The Rust codec additionally runs **seven fuzz targets** on a weekly long
  budget and cross-validates against the official `zipnn` package in both
  directions on every push.

Accepted-risk findings (for example unmaintained-crate advisories with no
successor, or build-tool advisories with no upstream fix) are recorded with
their reasons and review dates in `osv-scanner.toml`,
`native/osv-scanner.toml` and `.github/zizmor.yml` — nothing is silenced
without a written justification.
