<div align="center">

# <img src="https://api.iconify.design/lucide/boxes.svg?color=%236366f1" width="34" height="34" align="middle" alt=""> ComfyUI‑Model‑Manager‑Neo

### Browse · Download · Upload · Drag‑and‑drop — your models, beautifully managed.

A modern, glassmorphism re‑imagining of the ComfyUI model manager, rebuilt on
**Vue 3 + Tailwind CSS v4 + reka‑ui** with a fully modern toolchain.

![License](https://img.shields.io/badge/License-GPL--3.0--only-blue.svg)
![ComfyUI](https://img.shields.io/badge/ComfyUI-Custom%20Node-8A8B98.svg)
![Vue](https://img.shields.io/badge/Vue-3.5-4FC08D.svg?logo=vuedotjs&logoColor=white)
![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-v4-38BDF8.svg?logo=tailwindcss&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-6-3178C6.svg?logo=typescript&logoColor=white)
![ESLint](https://img.shields.io/badge/ESLint-10-4B32C3.svg?logo=eslint&logoColor=white)
![Prettier](https://img.shields.io/badge/Prettier-3-F7B93E.svg?logo=prettier&logoColor=black)
![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)

<!--
  ┌──────────────────────────────────────────────────────────────────────────┐
  │  SCREENSHOTS                                                             │
  │  The images referenced below ship in `docs/screenshots/`. See             │
  │  docs/screenshots/README.md for the full per-file manifest and for how to │
  │  re-capture each view from a live ComfyUI window.                         │
  └──────────────────────────────────────────────────────────────────────────┘
-->

![Hero overview](docs/screenshots/hero.gif)

</div>

---

**Contents**

- [Why Neo?](#why-neo) · [Screenshots](#screenshots) · [Installation](#installation) ·
  [Features](#features)
- [Model search & discovery](#search) · [ZipNN lossless compression](#zipnn) ·
  [What changed from the original](#what-changed) ·
  [Removed feature: batch scan](#removed-feature)
- [Documentation](#documentation) · [Development](#development) ·
  [Credits & Attribution](#credits) · [License](#license)

---

<a id="why-neo"></a>

## <img src="https://api.iconify.design/lucide/sparkles.svg?color=%23f59e0b" width="28" height="28" align="middle" alt=""> Why Neo?

**ComfyUI‑Model‑Manager‑Neo** takes the excellent original manager and rebuilds
the experience from the ground up:

- <img src="https://api.iconify.design/lucide/layers.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> **Glassmorphism UI** — a translucent, blurred, elevation‑aware interface
  that follows ComfyUI's own light/dark palette automatically.
- <img src="https://api.iconify.design/lucide/puzzle.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> **PrimeVue‑free** — the entire PrimeVue dependency was removed and replaced
  with lightweight, headless **[reka-ui]** primitives + **Tailwind CSS v4** +
  **[Lucide]** icons (shadcn‑vue style components you can read and tweak).
- <img src="https://api.iconify.design/lucide/upload-cloud.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> **Upload to Hugging Face / ModelScope** — publish any local model straight to a
  HF repo or a ModelScope model repo (creates the repo if needed, private
  option, live progress).
- <img src="https://api.iconify.design/lucide/package-plus.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> **ZipNN lossless compression** — compress / decompress safetensors models in
  place (`.znn.safetensors`) with confirmation, progress and an inverted icon on
  compressed models; whole folders batch-compress into sealed
  `<name>_DeltaZNN` bundles, and fine-tunes shrink to tiny **delta files**
  against their base.
- <img src="https://api.iconify.design/lucide/list-checks.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> **Multi-select** — tick cards to add several models to the workflow or
  delete them in one go. Folders can be ticked too: "Add to
  workflow" expands them recursively, "Delete" removes them wholesale.
- <img src="https://api.iconify.design/lucide/star.svg?color=%23eab308" width="16" height="16" align="middle" alt=""> **Stars** — every model and folder card carries a star toggle at its top-right
  (also in the model-detail action row and the selection bar); starred entries
  show a filled yellow star and always sort first.
- <img src="https://api.iconify.design/lucide/folder-plus.svg?color=%2322c55e" width="16" height="16" align="middle" alt=""> **Create folders** — the folder view offers an "Add Folder" button that
  creates arbitrarily named (sub-)folders inside the open directory.
- <img src="https://api.iconify.design/lucide/link.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> **Direct‑link downloads** — paste a raw `.safetensors`/`.ckpt`/`.gguf` URL,
  pick the target folder, optionally choose a custom sub‑folder.
- <img src="https://api.iconify.design/lucide/zap.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> **`hf_xet` acceleration** — Hugging Face transfers use the chunked,
  deduplicated Xet protocol when available.
- <img src="https://api.iconify.design/lucide/workflow.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> **First‑class node‑graph integration** — drag a model onto the canvas to
  spawn or fill a node, drag embeddings into text areas, load workflows embedded
  in preview images.
- <img src="https://api.iconify.design/lucide/monitor-smartphone.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> **Responsive** — designed for desktop, mobile and multi‑screen setups.
- <img src="https://api.iconify.design/lucide/wrench.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> **Modern toolchain** — Vite 8 (Rolldown), TypeScript 6, ESLint 10 flat
  config, Prettier, husky + lint‑staged. Deterministic, lint‑clean builds.

> [!NOTE]
> Neo is a **fork** of [`hayden-cn/ComfyUI-Model-Manager`](https://github.com/hayden-cn/ComfyUI-Model-Manager)
> and is distributed under the same **GPL‑3.0** license. All credit for the
> original architecture belongs to its author — see [Credits](#credits).

---

<a id="screenshots"></a>

## <img src="https://api.iconify.design/lucide/camera.svg?color=%238b5cf6" width="28" height="28" align="middle" alt=""> Screenshots

> [!TIP]
> The images below are **placeholders**. Prepare the files listed in the
> `docs/screenshots/` checklist at the top of this README and they will render
> automatically. Capture them from a live ComfyUI instance running this
> extension (dark theme recommended, ~1600 px wide for consistency).

### Flat “Models” view — search, sort and resize the grid

![Flat models grid](docs/screenshots/view-flat.png)

The manager window in **Flat** layout: a grid of glass model cards with preview,
type and size chips, the search bar, and the type / sort / card‑size selectors.

### Folder (explorer) view — navigate your directory tree

![Folder explorer view](docs/screenshots/view-folders.png)

The **Folder** layout one level deep, with the breadcrumb trail (each crumb
carries the tiny folder glyph; the trail takes no space at the root and opens
up only as the path gets deeper) and the animated glass folder cards.

### Model detail, editing, and the Hugging Face upload

|                                                                                                                    |                                                                                                  |
| ------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------ |
| ![Model info](docs/screenshots/model-info.png)                                                                     | ![Edit mode](docs/screenshots/model-edit.png)                                                    |
| _Model info: preview, base‑info table (note the trailing `/` on **Directory**), Description and Information tabs._ | _Edit mode: type dropdown, folder picker button, file name that accepts a `folder/name` prefix._ |

|                                                                                 |                                                                                          |
| ------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| ![Hugging Face upload](docs/screenshots/hf-upload.png)                          | ![Japanese UI](docs/screenshots/ja-model-info.png)                                       |
| _Upload to Hugging Face, step 3: repo id, private‑on‑create, destination path._ | _The same window in **日本語** — the UI ships complete English / 中文 / 日本語 bundles._ |

A 10‑second tour (open → folder view → hover a folder → back → open a model) is
[`docs/screenshots/hero.gif`](docs/screenshots/hero.gif); dragging a card onto a
live canvas is best captured from a real ComfyUI window — see
[`docs/screenshots/README.md`](docs/screenshots/README.md).

---

<a id="installation"></a>

## <img src="https://api.iconify.design/lucide/rocket.svg?color=%2322c55e" width="28" height="28" align="middle" alt=""> Installation

Neo runs as a ComfyUI custom node. Pick one method:

**1 · Git clone (recommended for updates)**

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/rikunarita/ComfyUI-Model-Manager-Neo.git
```

**2 · Manual download**

Download the
[repository archive](https://github.com/rikunarita/ComfyUI-Model-Manager-Neo/archive/refs/heads/main.zip),
extract it into `ComfyUI/custom_nodes/`, and make sure the folder is named
`ComfyUI-Model-Manager-Neo`.

**3 · ComfyUI Manager**

If the fork is published to the registry, search for
**“ComfyUI‑Model‑Manager‑Neo”** in [ComfyUI-Manager] and install it from there.

Then **restart ComfyUI**. Python dependencies (`huggingface_hub`, `hf_xet`,
`modelscope_hub`, `markdownify`) are installed automatically on first launch. The prebuilt web
bundle ships in [`web/`](web), so no Node.js is required to _run_ the extension.

Open it from the top‑bar **“Model Manager Neo”** button, the sidebar, or the
`Extensions → Model Manager Neo` menu command.

> [!TIP]
> Neo is under active development — functional and daily‑drivable, but the
> interfaces may still evolve. Feedback and issues are welcome.

---

<a id="features"></a>

## <img src="https://api.iconify.design/lucide/list-checks.svg?color=%233b82f6" width="28" height="28" align="middle" alt=""> Features

<details open>
<summary><b>Browse &amp; organise</b></summary>

- Two layouts: **Flat** grid (the default view) and **Folder** explorer,
  switchable at any time.
- Real‑time search (supports `*` wildcards and multi‑token “AND” matching).
- Sort by name, size, date created, date modified or **recently used**
  (opening a model or adding it to the graph records the use).
- Adjustable card size (presets + fully custom dimensions).
- Toggle visibility of hidden (`.`‑prefixed) files without restarting.
- Image **and video** previews, plus glass folder artwork with hover
  open/close animations and a glass no‑preview fallback.
- Type‑root folder cards carry the **aggregate size of their type** (a
  lightweight capacity dashboard), and models whose recorded SHA256 matches
  another file in the library raise a red **duplicate warning** in the detail
  window.
- Model cards filed below the type root show their **sub-directory** above the
  name (flat and folder view alike).
- **Smart collections** — save the flat view's current search + type filter as
  a named, per‑user collection and re‑apply it with one click. Save and apply
  live in a single pill button `[💾 Collections ▾]`: the floppy segment opens
  the save dialog (with its own click / keyboard target), the rest opens the
  menu that applies or switches saved collections.
- **Hygiene scan** — a local‑only sweep (no network, no hashing) for orphaned
  previews / notes, models without previews and empty folders, with bulk
  cleanup behind the usual confirmation.

</details>

<details>
<summary><b>Node graph integration</b></summary>

- Drag a model thumbnail onto the canvas to **add a loader node**.
- Drag onto an existing node to **fill a matching input** (exact when ambiguous).
- Drag an **embedding** into a text area to append `(embedding:name:1.0)`.
- Drag a preview image onto the graph to **load an embedded workflow**.
- **Add** / **Copy** buttons to place a node or copy it to ComfyUI's clipboard.

</details>

<details>
<summary><b>Download</b></summary>

- Paste a **Civitai**, **Hugging Face**, **ModelScope** (`www.modelscope.ai`)
  or **direct file** URL.
- Page URLs on Civitai's mirror host `civitai.red` are treated exactly like
  **Civitai** (the stored model page keeps the pasted host).
- Resolve multiple files/versions per page and pick the one you want.
- Direct links require an explicit target type, with an optional custom
  sub‑folder.
- Optional preview images — the **whole gallery** a model page offers is kept,
  and the image selected at download time becomes the card's primary preview;
  edit mode reorders / removes single gallery entries — and editable Markdown
  description per download.
- **Free‑space guard**: the download dialog shows the target volume's free
  space and the backend refuses tasks whose announced size cannot fit.
- Pause / resume / delete tasks; progress, speed and size update live.
- Hugging Face downloads use `huggingface_hub` (+ `hf_xet` when available).

</details>

<details>
<summary><b>Upload</b></summary>

- **From local file** into any model folder (registered as a live task with
  progress in the Download List).
- **To Hugging Face or ModelScope**: pick the platform in the wizard's first
  step (each hub presents itself as a logo tile); authenticated via the matching token, creates the repository if it
  doesn't exist (public/private), choose the destination path, and watch
  progress. ModelScope always talks to the international `www.modelscope.ai`
  domain, and its logo backs the "open model page" button like the others.
  The optional **related assets** switch also uploads every `<model name>.*`
  sidecar (preview images, Markdown notes) next to the model — notes are
  committed as the repository's `README.md` by default. Selected
  **folders** upload as a batch (every model inside, sub‑folders preserved)
  from the folder view's selection bar.

</details>

<details>
<summary><b>Model info &amp; maintenance</b></summary>

- Inspect file info and read everything recorded about a model in the
  read‑only **Information** table: the notes' YAML front‑matter parsed into
  author, base model, every hash (`AutoV1` … `SHA256_12`), format & precision,
  the model platform, a model‑page link and all preview URLs (unknown keys
  verbatim at the end), or the safetensors `__metadata__` block, verbatim, for
  models without one.
- Rename, move between folders/types, or **permanently delete** a model together
  with its previews and notes. Cancelling an edit that holds unsaved changes
  asks for confirmation first.
- Read, edit and save Markdown notes stored beside the model; the Information
  table itself is editable behind an explicit warning (it rewrites the notes'
  front‑matter on save).
- Change or remove a model's preview image — in edit mode the thumbnail
  wearing the blue ring is the one save promotes to the card's primary
  preview: tile clicks and the ‹ / › arrows move the ring, and entering edit
  always starts from the current primary no matter which page read mode was
  viewing (paging in read mode never re-designates the primary). The dashed
  tile at the end of the gallery strip adds local image files.
- The **Open model page** action wears the logo of the model's source hub
  (Civitai, Hugging Face or ModelScope) as its button background, so a model's
  origin is recognisable at a glance.
- The **Download to local** action streams the stored file to the browser as an
  attachment, saved under exactly its library name; the whole detail action row
  (ZipNN, star, hub page, identify, graph actions, local download, edit,
  delete) shares one button size inside a single inline scroll row.
- Model information (safetensors metadata, the full safetensors **tensor
  layout** as a collapsible **folder tree** (dotted tensor names grouped per
  segment, folder icon per level, collapsed by default; name / dtype / shape
  per tensor, Hugging Face‑viewer style), Markdown notes, preview) is loaded
  on demand when a model is opened — there is no separate library‑wide scan
  step.

</details>

<details>
<summary><b>Settings &amp; i18n</b></summary>

- API keys for **Civitai**, **Hugging Face** and **ModelScope**, stored locally
  in `private.key` (with `CIVITAI_API_KEY` / `HF_TOKEN` / `MODELSCOPE_API_TOKEN`
  environment fallbacks). Keys migrate out of ComfyUI user settings on first
  run.
- Exclude model types from the model list; include/exclude hidden files.
- ZipNN automation: auto‑compress models unused for N days, auto‑compress
  after a download completes, and pause downloads while a prompt executes.
- UI language follows ComfyUI's locale — **English**, **中文** and **日本語**
  bundled in full; region/script subtags (`ja-JP`, `zh-Hant-TW`, …) fold onto
  their base language.

</details>

---

<a id="search"></a>

## <img src="https://api.iconify.design/lucide/search.svg?color=%2314b8a6" width="28" height="28" align="middle" alt=""> Model search & multi‑platform discovery

The **Create Download Task** window accepts more than page URLs: anything that
does **not** start with `https://` is treated as a model‑name query and searched
in parallel across three platforms — **Hugging Face** (left column, through
`huggingface_hub`'s `HfApi.list_models`), **ModelScope** (middle, through
`modelscope_hub`) and **Civitai** (right, public REST API). The `https://`
prefix is checked character by character while you type, so the field flips
between search mode and URL mode in real time; results refresh with a short
debounce and each column reports its own errors instead of failing the whole
search.

- Every result row shows the publishing user's / organisation's **avatar** in a
  rounded frame: Hugging Face resolves organisation and personal avatars
  through the API (`/api/organizations/{name}` and `/api/users/{name}`), and
  ModelScope through `GET https://www.modelscope.ai/api/v1/models/{owner}/{repo}`
  (the owner's `Organization` block carries the avatar and the display name).
  An initials badge appears when the hub publishes none, plus the all‑time
  download count.
- The model id is split into two deep links: the **owner name** opens the
  user / organisation page, the **repository name** opens the model page —
  both underline on hover and open in the browser; clicking anywhere else on
  the row resolves that model straight into the download editor.
- Plain **`username/repo-name`** input is supported, and **one Enter always
  resolves**: an exact match among the results first, then the bare repository
  id as a Hugging Face repository, then the top row of the first non-empty
  column; with no results yet, Enter runs the name search immediately.
- Every column pages: scrolling it to the bottom reveals a **“∨ Show more”**
  button whenever a next page exists, and one click appends that column's next
  page (Hugging Face by download-order offset, ModelScope by page number,
  Civitai through the API's own cursor).
- Platforms can be hidden per user in **Settings → Model Manager Neo →
  Search** (one boolean per platform).
- Each platform's **sort order** is selectable in the same settings section
  (every value its API accepts); the defaults are Hugging Face trending,
  ModelScope likes and Civitai highest rated.

Civitai downloads additionally carry the safety net the official CLI
popularised, adapted to the manager's task system:

- **Download plan (dry run)** — before starting, the editor shows the resolved
  destination path, the announced size, the published SHA256 and whether the
  platform API key is configured.
- **SHA256 verification** — completed Civitai downloads are hashed and compared
  against the published SHA256; a mismatch deletes the file and fails the task.
- **Layout routing** — a version file whose own type maps to another model
  folder (a bundled VAE, …) is filed into that folder instead of the selected
  one.
- **Base‑model warning** — when the version's base model is foreign to the base
  models recorded in the destination folder's library.
- **Executable‑format warning** — pickle / archive payloads can execute code
  when loaded; the editor says so before you download.
- **Hub accounts (whoami)** — for every platform with a configured key
  (Hugging Face, ModelScope, Civitai) the download dialog shows the connected
  account through that hub's whoami endpoint, and 401 failures explain exactly
  where to create a key and how to resume.

Finally, enlarging a preview of a Civitai‑origin model opens the lightbox with
the image on the left and its parsed **generation metadata** on the right
(prompt, negative prompt, sampler, steps, CFG scale, seed, clip skip, size,
base model and the resource recipe), fetched per image from the Civitai API.

And the model detail window's **identify by hash** asks the Civitai catalog
which model version a local file is (a reverse lookup by hash): the hashes
already recorded in the Markdown sidecar are tried first, and only when none
of them hits is the file hashed in a single pass (`SHA256` / `AutoV2` /
`AutoV1` / `CRC32`, plus `BLAKE3` when available). A hit opens the resolved
model / version with its base model, trigger words, file list and the same
`civitai download` command the official CLI prints on a hit; a miss says no
matching model version was found.

---

<a id="zipnn"></a>

## <img src="https://api.iconify.design/lucide/package-plus.svg?color=%230ea5e9" width="28" height="28" align="middle" alt=""> ZipNN lossless compression

Large `.safetensors` checkpoints eat disk space fast.
Neo can compress and decompress them **in place, losslessly**, using the
[ZipNN](https://github.com/zipnn/zipnn) format — the same tensor-aware scheme the
official ZipNN project uses, so the results stay interchangeable with the wider
ZipNN ecosystem.

### How it works

Model weights are mostly floating-point numbers, and floating-point numbers are
mostly _redundant_: the exponent bytes of a well-behaved weight tensor repeat
over and over. ZipNN exploits exactly that. For every tensor it:

- **splits** the value into its byte planes and re-orders the sign / exponent /
  mantissa bits so like bytes land together, then
- **Huffman-codes** each plane with the FiniteStateEntropy (FSE) codec.

Tensors that are _not_ floating point (integer indices, masks, …) are copied
through untouched, and a floating-point tensor whose compressed form would not
actually be smaller is **left as-is** rather than padded. Each compressed tensor
is stored as a `uint8` vector, and the file records the original `dtype` and
`shape` of every one of them in a single `znn_compressed_vectors` metadata entry.
Nothing is approximated or dropped — decompression reproduces the original file
**bit for bit**.

The compressed model is written next to the original as
`<name>.znn.safetensors` — the exact suffix the official ZipNN tooling (and
loaders patched with `zipnn_safetensors()`) expect, so a patched ComfyUI loader
reads a Neo-compressed model transparently. Realistic checkpoints typically land
around **60–80 %** of their original size (random-ish data compresses far less;
low-entropy weights compress much more).

### Using it

Open any `.safetensors` model. In the gap between the preview and the info table
sits the **ZipNN artwork itself as the button** — the shipped SVG draws its own
glass plate (with a dark-mode variant), lifts and brightens on hover, and
explains itself in a tooltip and to screen readers. Pressing it:

1. asks for a confirmation that is deliberately _not_ styled as "Danger"
   (compression is reversible and never deletes the original until the
   compressed file is fully written and verified);
2. replaces the button with a **live progress bar** while the work runs on the
   CPU pool (tensor by tensor), so the rest of ComfyUI stays responsive;
3. on success, swaps the original for `<name>.znn.safetensors` — previews and
   Markdown notes follow the rename, and the grid refreshes itself.

Opening a **compressed** model shows the same artwork with its colours
**inverted** and the action flipped to _decompress_, behind the same
confirmation, restoring the plain `.safetensors`. Its info table changes too:
the single _File Size_ row is replaced by **Original File Size**, **Compressed
File Size** and **% of Original Size** — the pre-compression size is recorded
in the file's metadata at compression time, so the breakdown survives the
rename (files compressed by the official ZipNN CLI, which does not write that
key, simply keep the plain _File Size_ row).

The same artwork also sits on the **top-right corner of every model and folder
card** (next to the star toggle): one click compresses (or decompresses,
inverted) with the identical confirmation and progress behaviour, without
opening the model at all. While any task runs - single, batch or delta - the
button shows a **circular progress ring**.

### Batch compression (whole folders)

ZipNN's official tooling compresses whole paths; Neo wires that into the
manager. Select folders ("Select files") and press the **ZipNN artwork button
in the bottom bar** — or use the corner button on a folder card — and every
`.safetensors` model inside the folder tree is compressed (previews and notes
follow their models) and **moved into the bundle folder
`<name>_DeltaZNN`** — the original folder disappears once it empties. A
`*_DeltaZNN` bundle is sealed:

- only ZipNN content (`*.znn.*` models, `*.znn` delta files) may ever be placed
  inside one (uploads, downloads and moves of plain models into it are
  refused);
- selecting a bundle folder together with a non-bundle folder is impossible —
  the bundle side is deselected automatically with a warning toast;
- the bundle's ZipNN button is **inverted**; pressing it **batch-decompresses**
  the bundle and moves everything back to the folder it was named after (the
  emptied bundle folder is removed);
- delta folders (`<base>_DeltaZNN`, see below) are bundles too: their inverted
  button restores every fine-tune inside them in one go;
- model-type **root folders** (`checkpoints`, ...) get their bundle **inside
  themselves** (`<root>_DeltaZNN`) — a sibling of a type root would fall
  outside ComfyUI's folder mapping and vanish from both the loader and the
  manager; the direction is auto-detected: compress while plain models exist,
  decompress when only bundles remain;
- bundles created by older versions (`<name>_ZNN`) are still recognised and
  decompress back to their original name;
- while a task runs the button becomes a circular ring with the **percentage
  inside the circle**.

Several folders run as a queue: one confirmation, sequential tasks, one
progress state at a time.

### Delta compression (fine-tunes against a base)

A fine-tuned model shares most of its bytes with its base, and ZipNN can store
only the **difference**: select exactly two plain `.safetensors` models and
press **ZipNN delta compress** in the bottom bar. A small dialog lets you pick
which selection is the **base** and which the **fine-tune** (the official
byte-level delta API with header-length alignment is used under the hood, so
base and fine-tune may carry different metadata).
The result — typically a few percent of the fine-tune's size — is written to
**`<base>_DeltaZNN/<ft>_delta_<base>.znn`** and the redundant fine-tune file is
removed. Decompressing a delta (its card button, inverted) restores the
fine-tuned model **byte-exactly** beside the base and retires the now-empty
delta folder. Restoration needs the base model, and ZipNN verifies that both
sides have the same byte length when the delta is created.

### Bundled, so it just works

<details>
<summary><b>Why ZipNN is vendored</b></summary>

ZipNN's Python side is trivial, but its compressor is a C extension
(`zipnn_core`, built on FiniteStateEntropy). **PyPI ships no Linux wheels for
it** — only a macOS-arm64 wheel and a source tarball — so a plain
`pip install zipnn` compiles from source and dies on any machine without a C
compiler and the Python headers (`Python.h`). That is a very common way to run
ComfyUI, and the failure is cryptic (`error: [Errno 2] No such file or
directory: 'x86_64-pc-linux-gnu-gcc'`).

Neo therefore **vendors the whole library** under [`third_party/`](third_party/)
and ships **prebuilt `zipnn_core` binaries** for Linux x86_64 (CPython 3.10 –
3.15). On those platforms the first compression simply puts the bundled package
and the matching binary on `sys.path` — **no compiler, no pip, no network, no
waiting**. Only where no prebuilt binary matches (macOS, Windows, an uncommon
architecture, or a brand-new CPython) does Neo fall back to a **single** clean
build from the bundled C sources — never a cascade of pip strategies.

See [`third_party/README.md`](third_party/README.md) for the layout, the
platform/glibc coverage, the licences (ZipNN is MIT; FiniteStateEntropy is
BSD-2-Clause OR GPL-2.0), and how to rebuild or add binaries.

</details>

> [!NOTE]
> Compression needs the model's tensors in memory, so it runs on the CPU pool
> and is bounded by RAM, not VRAM. It is **lossless and reversible**: the plain
> `.safetensors` is only removed after the `.znn.safetensors` file has been
> written and closed, and a failed run cleans up its partial output.

---

<a id="what-changed"></a>

## <img src="https://api.iconify.design/lucide/git-compare.svg?color=%23a855f7" width="28" height="28" align="middle" alt=""> What changed from the original

This section makes the fork's differences explicit, as required by the GPL‑3.0
license. Functionality is preserved and extended. Two things were _removed_: the
PrimeVue dependency itself, and the batch‑scan feature — see
[Removed feature: batch scan](#removed-feature).

### <img src="https://api.iconify.design/lucide/palette.svg?color=%23d946ef" width="22" height="22" align="middle" alt=""> Interface

| Area              | Original                                                | **Neo**                                                                                                                                                                                                                                               |
| ----------------- | ------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Component library | PrimeVue 4                                              | **reka‑ui** (headless) + shadcn‑vue‑style wrappers                                                                                                                                                                                                    |
| Styling           | Tailwind CSS v3 + PrimeVue theme                        | **Tailwind CSS v4** with scoped `--mm-*` design tokens                                                                                                                                                                                                |
| Icons             | PrimeIcons                                              | **Lucide** (`@lucide/vue`) via an icon map                                                                                                                                                                                                            |
| Look & feel       | Standard PrimeVue surfaces                              | **Glassmorphism** (blur, elevation, micro‑interactions), auto dark mode                                                                                                                                                                               |
| Dialogs           | PrimeVue `Dialog`/`ContextMenu`                         | reka‑ui dialogs, per‑dialog size/position, drag‑to‑move, anchored context menus                                                                                                                                                                       |
| Model detail tabs | Description + Metadata (raw safetensors `__metadata__`) | Description + **Information**: a read‑only table parsing the notes' YAML front‑matter (author, base model, hashes, format & precision, model platform, model‑page link, every preview URL, unknown keys verbatim), raw `__metadata__` as the fallback |

### <img src="https://api.iconify.design/lucide/package.svg?color=%23f97316" width="22" height="22" align="middle" alt=""> Packages

- **Removed:** `primevue`, `@primevue/themes`, `lodash`, `dayjs`, `js-yaml`.
- **Added / replaced:** `reka-ui`, `@lucide/vue`, `es-toolkit` (← lodash),
  `date-fns` (← dayjs), `yaml` (← js-yaml), `vue-sonner` (toasts),
  `class-variance-authority`, `clsx`, `tailwind-merge`.
- **Upgraded:** Vite 5 → **8** (Rolldown), TypeScript 5 → **6**, Vue i18n 9 →
  **11**, markdown‑it 14 → **15**, `@vueuse/core` 11 → **14**.
- **Python:** added `huggingface_hub` + `hf_xet` + `modelscope_hub`; asyncio
  task pool replacing the old thread pool.

### <img src="https://api.iconify.design/lucide/sliders-horizontal.svg?color=%2306b6d4" width="22" height="22" align="middle" alt=""> Toolbar / button roles

The manager header was redesigned into explicit, icon‑driven actions:
**flat ⇄ folder layout toggle**, **hygiene scan**, **show/hide hidden files**,
**refresh**, **download list**, and **upload to Hugging Face / ModelScope**.

### <img src="https://api.iconify.design/lucide/folder-open.svg?color=%23f59e0b" width="22" height="22" align="middle" alt=""> Glass asset pack (folder icons & no‑preview art)

The interface draws on a hand‑made glassmorphism asset pack in `assets/`:

- **Folder cards** show `Folder-Icons/close-folder_beside-fit.svg` at rest.
  Resting the pointer on a card for **at least one second** plays
  `folder-opening-animation.svg` (SMIL morph: 0.2 s delay + 1.35 s); staying
  away for a full second plays `folder-closing-animation.svg`, after which
  the card settles back onto the static icon. Casual pass‑overs never make
  the folder flap. The SVGs are inlined into the bundle (`?raw` + data URI),
  so every card owns its SVG document: no extra requests, and the gradient
  ids inside the artwork can never collide between the many cards on screen.
- **Breadcrumb trails** prefix every segment with the tiny
  `close-folder_all-fit.svg` glyph (14 px) — the variant that reads best at
  small sizes.
- **Models without a preview** use the glass `NOPREVIEW-Icon/NO-PREVIEW.svg`
  as their default artwork: the model list points straight at
  `GET /model-manager/no-preview.svg` (served verbatim as `image/svg+xml` —
  vector art is never rasterised), and the preview routes serve real preview
  files or answer 404.
- **Model‑hub logos** live in `AIModelHub-Logos/` (`civitai-icon.svg`,
  `hf-icon.svg`): the **Open model page** button wears the logo of the
  platform recorded in the model's notes (`website`) as its background, in the
  detail action row and in the card hover column alike.

### <img src="https://api.iconify.design/lucide/hammer.svg?color=%2365a30d" width="22" height="22" align="middle" alt=""> Toolchain

The lint / format pipeline is a conventional, fully‑configured
**ESLint 10 flat config** + **Prettier** setup, complemented by
[Fallow](https://fallow.tools) for dead‑code and duplication analysis (see
[Development](#development)).

---

<a id="removed-feature"></a>

## <img src="https://api.iconify.design/lucide/trash-2.svg?color=%23ef4444" width="28" height="28" align="middle" alt=""> Removed feature: batch scan

The **“Batch scan model information”** feature has been removed. It was
redundant: the model detail window reads that model's `__metadata__` straight
from the safetensors header together with the Markdown notes stored beside the
file, and a model without a preview carries the bundled glass `NO-PREVIEW.svg`
artwork right in the grid. A library‑wide walk that hashed every model and
queried Civitai by hash was a second, far slower route to the same information
— plus a modal dialog, a global store, websocket events, a task file on disk
and its own settings, all of which had to be maintained.

The two settings that outlived the scan drive the **model list** today (which
types are loaded into the grid, and whether `.`‑prefixed files are shown),
under the settings category **Model List**. They keep their historical
`ModelManager.Scan.*` ID strings because that ID is the key ComfyUI persists
each user's value under — renaming it would orphan every existing
installation's saved setting.

> [!NOTE]
> **What this gives up:** the only way to _bulk backfill_ previews and
> descriptions from Civitai by file hash. A model whose information was never
> fetched keeps its placeholder preview until the preview/notes are set by hand
> (the model editor's gallery strip: add local image files through its dashed
> tile, or reorder / remove entries), or until it is re‑downloaded
> through _Create Download Task_, which does carry a preview. Reading a model's
> information is unaffected — that always comes from disk, on demand. Individual
> models can still be identified against the Civitai catalog on demand with the
> hash reverse-lookup button of the detail window.

<a id="documentation"></a>

## <img src="https://api.iconify.design/lucide/book-open.svg?color=%237c3aed" width="28" height="28" align="middle" alt=""> Documentation

Step‑by‑step usage guides, each complete and self‑contained:

- [`docs/USAGE-EN.md`](docs/USAGE-EN.md) — English
- [`docs/USAGE-JA.md`](docs/USAGE-JA.md) — 日本語
- [`docs/USAGE-ZN.md`](docs/USAGE-ZN.md) — 中文

They cover installation, both layouts, card interactions and drag‑to‑graph, the
model editor (folder picker, folder‑prefixed names, previews, descriptions),
downloads and the task list, the hub upload (Hugging Face / ModelScope) phases
and completion messages, ZipNN compression, settings and locales, plus a
troubleshooting table.
The screenshots they embed live in [`docs/screenshots/`](docs/screenshots/) with
a per‑file manifest in
[`docs/screenshots/README.md`](docs/screenshots/README.md).

<a id="development"></a>

## <img src="https://api.iconify.design/lucide/terminal.svg?color=%230ea5e9" width="28" height="28" align="middle" alt=""> Development

You only need Node.js to **build** the web bundle; running the extension inside
ComfyUI needs nothing but Python.

```bash
corepack enable          # uses the pinned pnpm version
pnpm install
```

| Script                                  | Purpose                                                                 |
| --------------------------------------- | ----------------------------------------------------------------------- |
| `pnpm dev`                              | Vite dev server (writes `web/manager-dev.js` for hot reload in ComfyUI) |
| `pnpm build`                            | Production build into `web/`                                            |
| `pnpm build:clean`                      | Remove `web/` then rebuild                                              |
| `pnpm rebuild`                          | Remove `node_modules/` **and** `web/`, reinstall, then rebuild          |
| `pnpm typecheck`                        | `vue-tsc --noEmit` type checking                                        |
| `pnpm lint` / `pnpm lint:fix`           | ESLint (flat config)                                                    |
| `pnpm format` / `pnpm format:check`     | Prettier (with the Tailwind plugin)                                     |
| `python -m mypy --config-file mypy.ini` | Backend static types, clean                                             |
| `pnpm fallow`                           | Fallow full pipeline: dead code + duplication + health                  |
| `pnpm fallow:dead` (`:type-aware`)      | unused files/exports/types/deps, cycles — optional TS semantic pass     |
| `pnpm fallow:dupes`                     | AST clone detection (`mild` mode, see `.fallowrc.json`)                 |
| `pnpm fallow:health`                    | complexity hotspots, refactor targets, 0–100 health score               |
| `pnpm fallow:fix:dry` / `fallow:fix`    | preview / apply automatic cleanup (always dry-run first)                |
| `pnpm fallow:audit`                     | PR-style gate: only findings introduced by the current change           |

> [!WARNING]
> `pnpm dev` **deletes the whole `web/` directory** before writing
> `manager-dev.js` (see the `dev()` plugin in `vite.config.ts`). That removes the
> committed production bundle — `web/manager.js` and `web/style-*.css` — from the
> working tree, so `git status` shows them as deleted. Committing in that state
> would ship an extension whose UI no longer loads. Always run `pnpm build`
> before committing, and never commit a tree where `web/manager.js` is missing.

A **husky** `pre-commit` hook runs **lint-staged** (ESLint `--fix` + Prettier) on
staged files.

### Fallow (codebase intelligence)

[Fallow](https://fallow.tools) (Rust, no AI inside the analyzer) complements the
linters: it reads the repository as one dependency graph and reports unused
files/exports/types/dependencies, circular imports, clone groups and
complexity hotspots. `.fallowrc.json` pins the entry point (`src/main.ts`),
keeps the committed `web/` bundle, vendored `third_party/`, docs and assets out
of the graph, and turns the private-type-leak and unresolved-import checks on.
The tree is kept at **zero unused exports, zero duplication**; the single
remaining finding is the deliberate `pnpm-workspace.yaml` override pinning
`@comfyorg/comfyui-desktop-bridge-types` (a transitive type package of
`@comfyorg/comfyui-frontend-types`). `pnpm fallow:fix:dry` previews every
automatic removal before `pnpm fallow:fix` applies it.

### Lint & format stack

ESLint 10 flat config wiring together `typescript-eslint`, `eslint-plugin-vue`
(via `vue-eslint-parser`), `eslint-plugin-import-x` (alias‑aware import
ordering), `eslint-plugin-tailwindcss` (class hygiene) and `eslint-config-prettier`
(must stay last). Prettier handles formatting and Tailwind class sorting via
`prettier-plugin-tailwindcss`.

### Project structure

```
├─ __init__.py            # ComfyUI entry: installs deps, registers routes
├─ py/                    # Python backend (aiohttp routes, HF/Civitai, tasks)
│  ├─ manager.py          #   model CRUD + folder listing
│  ├─ download.py         #   download tasks (http + huggingface_hub + modelscope_hub)
│  ├─ upload.py           #   local file upload (path-validated)
│  ├─ upload_hf.py        #   upload to Hugging Face (shared hub pipeline)
│  ├─ upload_modelscope.py#   upload to ModelScope
│  ├─ compress.py         #   ZipNN compress / decompress (vendored core)
│  ├─ information.py      #   Civitai/HF/ModelScope page resolution, preview serving
│  ├─ search.py           #   multi-platform model-name search + avatar proxy
│  ├─ identify.py         #   Civitai hash reverse-lookup
│  ├─ auth.py · config.py · thread.py · utils.py
├─ third_party/           # vendored ZipNN (Python pkg + prebuilt zipnn_core + C src)
├─ src/                   # Vue 3 frontend
│  ├─ components/         #   app components + ui/ (reka-ui wrappers)
│  ├─ hooks/              #   store, models, download, config, dialog, …
│  ├─ utils/ · types/ · locales/
│  ├─ style.css           #   Tailwind v4 entry + design tokens
│  └─ main.ts             #   registers the ComfyUI extension
└─ web/                   # prebuilt bundle served to ComfyUI (committed)
```

---

<a id="credits"></a>

## <img src="https://api.iconify.design/lucide/heart-handshake.svg?color=%23ec4899" width="28" height="28" align="middle" alt=""> Credits & Attribution

ComfyUI‑Model‑Manager‑Neo exists only because
**[`ComfyUI-Model-Manager`](https://github.com/hayden-cn/ComfyUI-Model-Manager)**
by **[hayden‑cn](https://github.com/hayden-cn)** existed first. Every structural
idea in this fork — the model‑folder abstraction, the resumable download task
system with its websocket progress protocol, the Civitai / Hugging Face page
parsers, the drag‑a‑card‑onto‑the‑graph integration, the model editor's form
plumbing, even the little affordances like the card‑size presets — is hayden‑cn's
design. Neo changes the skin, the dependencies and a great many bugs; it did not
have to invent the body. Reading the original remains the fastest way to
understand _why_ this codebase is shaped the way it is, and the honest
attribution for the architecture is: **theirs**.

This fork is a derivative work used and modified in accordance with the
**GNU General Public License v3.0**. Modifications in Neo (the UI rebuild,
PrimeVue removal, Hugging Face upload, ZipNN compression, package
modernisation, toolchain, the reliability and security hardening, the
batch‑scan removal and the Japanese localisation) are provided under the same
GPL‑3.0 license. Per the license, the original copyright notice and the full
license text are preserved in [`LICENSE`](LICENSE).

### <img src="https://api.iconify.design/lucide/bot.svg?color=%236366f1" width="22" height="22" align="middle" alt=""> Built with Qwen Studio

A large part of this fork was built with **[Qwen Studio]**. The ZipNN
integration — vendoring the library, producing the prebuilt `zipnn_core`
binaries, and the tensor-by-tensor compress/decompress port — the glassmorphism
UI rebuild, the Hugging Face upload flow, the reliability and security passes,
and much of the debugging were all developed in close collaboration with Qwen
Studio. Its careful, iterative engineering is a big reason Neo is as robust as
it is, and this project is grateful for that contribution.

If this fork is useful to you, the upstream repository deserves the star: the
work standing on its shoulders is what makes any of the above possible.

Built with these excellent projects: [reka-ui], [Tailwind CSS], [Lucide],
[VueUse], [es-toolkit], [vue-sonner], [huggingface_hub], [hf_xet],
[modelscope_hub], and [ZipNN].

---

<a id="license"></a>

## <img src="https://api.iconify.design/lucide/scale.svg?color=%2394a3b8" width="28" height="28" align="middle" alt=""> License

**GPL‑3.0‑only** — see [`LICENSE`](LICENSE) for the full text.

<div align="center">

**If Neo saves you time, consider starring the repo <img src="https://api.iconify.design/lucide/star.svg?color=%23eab308" width="16" height="16" align="middle" alt=""> and thanking the
[original author](https://github.com/hayden-cn/ComfyUI-Model-Manager).**

</div>

<!-- Link references -->

[reka-ui]: https://reka-ui.com
[Tailwind CSS]: https://tailwindcss.com
[Lucide]: https://lucide.dev
[VueUse]: https://vueuse.org
[es-toolkit]: https://es-toolkit.dev
[vue-sonner]: https://vue-sonner.vercel.app
[huggingface_hub]: https://github.com/huggingface/huggingface_hub
[hf_xet]: https://github.com/huggingface/xet-core
[modelscope_hub]: https://github.com/modelscope/modelscope_hub
[ZipNN]: https://github.com/zipnn/zipnn
[Qwen Studio]: https://chat.qwen.ai/
[ComfyUI-Manager]: https://github.com/ltdrdata/ComfyUI-Manager
