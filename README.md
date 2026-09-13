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
  │  The images referenced below ship in `docs/screenshots/` and are rendered │
  │  by the verification harness from the real production bundle             │
  │  (`pnpm capture`, see docs/screenshots/README.md for the full manifest    │
  │  and for which two shots are better taken from a live ComfyUI window).    │
  └──────────────────────────────────────────────────────────────────────────┘
-->

![Hero overview](docs/screenshots/hero.gif)

</div>

---

**Contents**

- [Why Neo?](#why-neo) · [Screenshots](#screenshots) · [Installation](#installation) ·
  [Features](#features)
- [What changed from the original](#what-changed) · [Removed feature: batch scan](#removed-feature)
- [First reliability pass](#pass-1) · [Second reliability pass](#pass-2) ·
  [Third reliability pass](#pass-3) · [Fourth reliability pass](#pass-4) ·
  [Fifth reliability pass](#pass-5) · [Sixth reliability pass](#pass-6) ·
  [Seventh reliability pass](#pass-7) ·
  [Eighth reliability pass](#pass-8) ·
  [Ninth reliability pass](#pass-9) ·
  [Tenth pass](#pass-10)
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
- <img src="https://api.iconify.design/lucide/upload-cloud.svg?color=%23f59e0b" width="16" height="16" align="middle" alt=""> **Upload to Hugging Face** — publish any local model straight to a HF repo
  (creates the repo if needed, private option, live progress) — _new in Neo_.
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
carries the tiny folder glyph) and the animated glass folder cards.

### Model detail, editing, and the HuggingFace upload

|                                                                                                   |                                                                                                  |
| ------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| ![Model info](docs/screenshots/model-info.png)                                                    | ![Edit mode](docs/screenshots/model-edit.png)                                                    |
| _Model info: preview, base‑info table (note the trailing `/` on **Directory**), Description tab._ | _Edit mode: type dropdown, folder picker button, file name that accepts a `folder/name` prefix._ |

|                                                                                |                                                                                          |
| ------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------- |
| ![HuggingFace upload](docs/screenshots/hf-upload.png)                          | ![Japanese UI](docs/screenshots/ja-model-info.png)                                       |
| _Upload to HuggingFace, step 3: repo id, private‑on‑create, destination path._ | _The same window in **日本語** — the UI ships complete English / 中文 / 日本語 bundles._ |

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
`markdownify`) are installed automatically on first launch. The prebuilt web
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
- Sort by name, size, date created or date modified.
- Adjustable card size (presets + fully custom dimensions).
- Toggle visibility of hidden (`.`‑prefixed) files without restarting.
- Image **and video** previews, plus glass folder artwork with hover
  open/close animations and a glass no‑preview fallback.

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

- Paste a **Civitai**, **Hugging Face** or **direct file** URL.
- Resolve multiple files/versions per page and pick the one you want.
- Direct links require an explicit target type, with an optional custom
  sub‑folder.
- Optional preview image and editable Markdown description per download.
- Pause / resume / delete tasks; progress, speed and size update live.
- Hugging Face downloads use `huggingface_hub` (+ `hf_xet` when available).

</details>

<details>
<summary><b>Upload</b></summary>

- **From local file** into any model folder (registered as a live task with
  progress in the Download List).
- **To Hugging Face** _(new in Neo)_: authenticated via your HF token, creates
  the repository if it doesn't exist (public/private), choose the destination
  path, and watch progress.

</details>

<details>
<summary><b>Model info &amp; maintenance</b></summary>

- Inspect file info and safetensors metadata.
- Rename, move between folders/types, or **permanently delete** a model together
  with its previews and notes.
- Read, edit and save Markdown notes stored beside the model.
- Change or remove a model's preview image.
- Model information (safetensors metadata, Markdown notes, preview) is loaded on
  demand when a model is opened — there is no separate library‑wide scan step.

</details>

<details>
<summary><b>Settings &amp; i18n</b></summary>

- API keys for **Civitai** and **Hugging Face**, stored locally in `private.key`
  (with `CIVITAI_API_KEY` / `HF_TOKEN` environment fallbacks). Keys migrate out
  of ComfyUI user settings on first run.
- Exclude model types from the model list; include/exclude hidden files.
- UI language follows ComfyUI's locale — **English**, **中文** and **日本語**
  bundled in full; region/script subtags (`ja-JP`, `zh-Hant-TW`, …) fold onto
  their base language.

</details>

---

<a id="what-changed"></a>

## <img src="https://api.iconify.design/lucide/git-compare.svg?color=%23a855f7" width="28" height="28" align="middle" alt=""> What changed from the original

This section makes the fork's differences explicit, as required by the GPL‑3.0
license. Functionality is preserved and extended. Two things were _removed_: the
PrimeVue dependency itself, and the batch‑scan feature — see
[Removed feature: batch scan](#removed-feature).

### <img src="https://api.iconify.design/lucide/palette.svg?color=%23d946ef" width="22" height="22" align="middle" alt=""> Interface

| Area              | Original                         | **Neo**                                                                         |
| ----------------- | -------------------------------- | ------------------------------------------------------------------------------- |
| Component library | PrimeVue 4                       | **reka‑ui** (headless) + shadcn‑vue‑style wrappers                              |
| Styling           | Tailwind CSS v3 + PrimeVue theme | **Tailwind CSS v4** with scoped `--mm-*` design tokens                          |
| Icons             | PrimeIcons                       | **Lucide** (`@lucide/vue`) via an icon map                                      |
| Look & feel       | Standard PrimeVue surfaces       | **Glassmorphism** (blur, elevation, micro‑interactions), auto dark mode         |
| Dialogs           | PrimeVue `Dialog`/`ContextMenu`  | reka‑ui dialogs, per‑dialog size/position, drag‑to‑move, anchored context menus |

### <img src="https://api.iconify.design/lucide/package.svg?color=%23f97316" width="22" height="22" align="middle" alt=""> Packages

- **Removed:** `primevue`, `@primevue/themes`, `lodash`, `dayjs`, `js-yaml`.
- **Added / replaced:** `reka-ui`, `@lucide/vue`, `es-toolkit` (← lodash),
  `date-fns` (← dayjs), `yaml` (← js-yaml), `valibot` (runtime schema
  validation), `vue-sonner` (toasts), `class-variance-authority`, `clsx`,
  `tailwind-merge`, `tw-animate-css`.
- **Upgraded:** Vite 5 → **8** (Rolldown), TypeScript 5 → **6**, Vue i18n 9 →
  **11**, markdown‑it 14 → **15**, `@vueuse/core` 11 → **14**.
- **Python:** added `huggingface_hub` + `hf_xet`; asyncio task pool replacing the
  old thread pool.

### <img src="https://api.iconify.design/lucide/sliders-horizontal.svg?color=%2306b6d4" width="22" height="22" align="middle" alt=""> Toolbar / button roles

The manager header was redesigned into explicit, icon‑driven actions:
**flat ⇄ folder layout toggle**, **show/hide hidden files**, **refresh**,
**download list**, and **upload to Hugging Face**.

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
  as their **default** artwork: the model list points straight at
  `GET /model-manager/no-preview.svg` (served verbatim as `image/svg+xml`,
  vector art is never rasterised). The preview routes themselves carry **no
  fallback chain any more** — they serve real preview files or answer 404 —
  and the old flat `no-preview.png` raster is gone.

### <img src="https://api.iconify.design/lucide/hammer.svg?color=%2365a30d" width="22" height="22" align="middle" alt=""> Toolchain

Biome was trialled and then **removed** in favour of a conventional,
fully‑configured **ESLint 10 flat config** + **Prettier** pipeline (see
[Development](#development)).

---

<a id="removed-feature"></a>

## <img src="https://api.iconify.design/lucide/trash-2.svg?color=%23ef4444" width="28" height="28" align="middle" alt=""> Removed feature: batch scan

The **“Batch scan model information”** feature has been **removed entirely**. It
was redundant: opening a model already loads, on demand and for exactly the model
you are looking at, everything the scan used to backfill in bulk.

- `DialogModelDetail` requests `GET /model-manager/model/{type}/{index}/{filename}`
  as soon as it mounts. That returns the model's `__metadata__` (read straight
  from the safetensors header) and the Markdown notes stored beside the file.
- The preview is served by `GET /model-manager/preview/{type}/{index}/{filename}`,
  which resolves whichever preview file exists (`.webp` / `.png` / `.jpg` / video,
  as `name.ext` or `name.preview.ext`). A model without one carries the bundled
  glass `NO-PREVIEW.svg` URL straight in the model list, so the route has no
  fallback chain and answers a plain 404 for anything that does not exist.

A library‑wide walk that hashed every model and queried Civitai by hash was a
second, far slower route to the same information — plus a modal dialog, a global
store, two websocket events, a task file on disk and its own settings, all of
which had to be maintained. All of it is gone.

**Frontend**

- Deleted `src/components/DialogScanning.vue` and `src/hooks/scan.ts`.
- `App.vue`: removed the `scanning` toolbar button, `openModelScanning()` and the
  `DialogScanning` import; `utils/iconMap.ts`: removed the
  `mdi mdi-folder-search-outline` mapping and its `FolderSearch` import.
- Dropped ten scan‑only keys from `en.json` / `zh.json`
  (`batchScanModelInformation`, `modelInformationScanning`, `scanModelInformation`,
  `selectedAllPaths`, `scanFullInformation`, `scanMissInformation`,
  `scanCompleted`, `scanCompletedWithErrors`, `setting.scanAll`,
  `setting.scanMissing`).

**Backend**

- `py/information.py`: removed the `GET` and `POST /model-manager/model-info/scan`
  routes, `create_scan_model_info_task`, `download_model_info`,
  `get_scan_model_info_task_list`, `get_scan_information_task_filepath`,
  `SCAN_TASK_ID` and the scan's own `DownloadThreadPool` (along with the now
  unused `functools` / `thread` imports).
- Removed `ModelSearcher.search_by_hash` and its three implementations — the scan
  was the only caller. `_resolve_model_type` stays: `search_by_url` uses it.
- `py/utils.py`: removed `recursive_search_files` and `calculate_sha256` (and the
  `hashlib` import) — both existed only for the scan.
- The `update_scan_information_task` / `complete_scan_information_task` websocket
  events no longer exist, and no `downloads/scan_information.task` file is written.

**Deliberately kept** — these say “scan” but are _not_ part of the batch scan:

- `ModelManager.Scan.excludeScanTypes` and `ModelManager.Scan.IncludeHiddenFiles`
  drive the **model list** (which types are loaded into the grid, and whether
  `.`‑prefixed files are shown) and the toolbar's show/hide‑hidden‑files toggle.
  **These two setting ID strings are intentionally unchanged**: the ID is the key
  ComfyUI persists the user's value under, so renaming it would silently orphan
  every existing installation's saved setting. A harness assertion now pins all
  seven IDs so they cannot drift.
- Everything _around_ those IDs was still de‑scan‑ned, because none of it is
  persisted: the settings category is now **Model List** (was “Scan”), the label
  is **“Exclude model types (separate with commas)”** (was “Exclude scan types”),
  the i18n keys are `setting.modelList` / `setting.excludeModelTypes`, the
  TypeScript identifier is `configSetting.excludeModelTypes`, and the backend
  setting group in `py/config.py` is `model_list` (so `manager.py` now resolves
  `model_list.include_hidden_files`). Verified end to end: with
  `IncludeHiddenFiles` off the list is `[alpha, beta, gamma]`, with it on
  `[.hidden, alpha, beta, gamma]`.
- `ModelManager.scan_models()` / `os.scandir` — builds the model **list** (“scan”
  here means “enumerate a folder”, as it did upstream). Left as‑is on purpose:
  renaming it would churn code that has nothing to do with the removed feature.
- `scan_model_download_task_list()` — lists **download tasks**. Same reasoning.
- Tailwind's “source scan” wording in `src/style.css` — unrelated.
- `ui/tree`, `ui/progress`, `useModelFolder`, and the `selectModelType` /
  `selectSubdirectory` / `selectedSpecialPath` / `noModelsInCurrentPath` strings —
  shared with the Upload and Hugging Face Upload dialogs and the model editor.

> [!NOTE]
> **What this gives up:** the only way to _bulk backfill_ previews and
> descriptions from Civitai by file hash. A model whose information was never
> fetched keeps its placeholder preview until the preview/notes are set by hand
> (model editor → **Preview** → _Network_ / _Local_), or until it is re‑downloaded
> through _Create Download Task_, which does carry a preview. Reading a model's
> information is unaffected — that always came from disk, on demand.

<a id="pass-1"></a>

## <img src="https://api.iconify.design/lucide/shield-check.svg?color=%2314b8a6" width="28" height="28" align="middle" alt=""> First reliability pass (Tailwind layers, dialog stack, Python hardening)

Neo was audited end‑to‑end and hardened. Highlights:

**Frontend**

- Restored the Tailwind **theme layer** so standard utilities (`p-*`, `text-*`,
  `size-*`, `gap-*`, …) are actually emitted — previously every theme‑dependent
  class was silently dropped from the stylesheet.
- Excluded build output from Tailwind's source scan → **deterministic** CSS
  (no more “garbage” utilities pulled from the bundled `web/manager.js`).
- Rebuilt the dialog stack to honour **per‑dialog** `defaultSize`, `min/max`
  sizes, `resizeAllow` and `modal`; non‑modal by default again so the canvas
  stays interactive (drag‑to‑graph works); dialogs no longer close on
  Escape/outside click; header drag‑to‑move restored.
- Fixed the flat grid crash on first paint (`chunk()` with a non‑positive column
  count), the “None” preview not deleting existing previews, custom sub‑folders
  being dropped/doubled on download, the embedding drag inserting the file
  _extension_ instead of the name, an unanchored right‑click menu, the
  indeterminate progress bar, and several icon/i18n gaps.
- `<GlobalLoading/>` is rendered again (the global spinner was dead).

**Backend (Python)**

- **Critical:** removed `hf_hub_download(resume_download=…)`, deleted in
  `huggingface_hub` 1.x — every Hugging Face download was failing with a
  `TypeError`.
- Persist the joined sub‑folder into the task so completed downloads land in the
  chosen folder (not the type root).
- Correct progress payloads, recursive HF file‑tree sizes, HF `tree`/`blob` URL
  filtering, preview URL construction, and Python 3.13‑safe `mimetypes` usage.
- `is_installed()` now parses requirement specifiers, so pip no longer re‑runs on
  every startup.
- **Security:** local uploads validate the target path (blocks arbitrary writes
  and path traversal); model paths are traversal‑checked.

All changes preserve existing behaviour and are covered by the checks in
[Development](#development).

---

<a id="pass-2"></a>

## <img src="https://api.iconify.design/lucide/clipboard-check.svg?color=%2314b8a6" width="28" height="28" align="middle" alt=""> Second reliability pass (progress slot, model editor, task pool)

A second end‑to‑end audit — driven by a headless harness that runs the real
`web/manager.js` bundle against the real Python routes over HTTP + WebSocket —
found and fixed the following. Nothing here changes intended behaviour; each
item restores behaviour that was documented but silently broken.

**Blocking I/O in request handlers**

- **`GET /models/{folder}` blocked the event loop** — every model list refresh
  stat'ed every file inline. Moved to the executor, with the request‑scoped
  hidden‑files setting resolved beforehand.

**Model editor**

- **Every `<Button>` defaulted to `type="submit"`.** reka‑ui's `Primitive` does
  not add a type, and the HTML default is `submit`; PrimeVue's Button injects
  `type="button"`. Inside `ModelContent`'s `<form>` that meant each icon button
  submitted the form — pressing the pencil set `editable = true` and then
  immediately ran the save handler, which set it back to `false`. **The model
  editor could not be opened at all.** `Button` now defaults to `type="button"`
  (explicit `type="submit"`/`"reset"` still win). The same latent hazard was
  removed from the hand‑written `<button>` elements that can end up inside that
  form (`ResponseInput`'s clear button, `ModelPreview`'s carousel arrows) and,
  for hygiene, from `ResponseBreadcrumb` / `DownloadTaskItem`.
- **Entering edit mode erased the model type.** A `watch(editable, …)` that
  upstream never had reset `type` to `''`, so saving a move/rename sent
  `type: ""` and the backend rejected it, and the Create Download Task dialog
  lost the type resolved from the search.
- **Renaming and moving a model were silently ignored.** `updateModel` only
  compared `subFolder` and `pathIndex`, so changing just the file name — or the
  model _type_ at the same path index — sent no request at all; the editor
  simply closed as if the change had been saved. All five fields are compared
  now, and a move across types refreshes both folders.
- **Civitai model types are resolved again.** `_resolve_model_type` had been
  deleted and the type hardcoded to `""`. It is restored, hardened to only
  return a type ComfyUI actually has a folder for (so categories such as
  "Wildcards" degrade to empty instead of an unusable value).

**Layout & task pool**

- **The folder view broke after a layout/hidden‑files toggle.** Both call
  `dialog.closeAll()`, which unmounts the explorer; `watch(initialized, …)`
  lacked `immediate`, so on every mount after the first it never fired and the
  explorer rendered a single `root` card with no breadcrumb.
- **`DownloadThreadPool` lost its duplicate‑submit guard** in the
  thread‑pool → asyncio rewrite. Resuming a task that was still running started
  a _second_ download writing to the same `<task>.download` file. `submit()`
  returns `"Existing"` again, and the asyncio lock is created lazily inside the
  running loop (Python 3.9 bound it at import time, outside any loop).

---

<a id="pass-3"></a>

## <img src="https://api.iconify.design/lucide/bug.svg?color=%2314b8a6" width="28" height="28" align="middle" alt=""> Third reliability pass (blocking I/O, PrimeVue leftovers, false failures)

A third end‑to‑end audit, again driven by a headless harness that runs the real
`web/manager.js` bundle inside jsdom against the real Python routes over
HTTP + WebSocket (with a faithful mock of `window.comfyAPI`, including
`api.fetchApi`'s 60 s response‑header timeout and the `_registered` gate that
decides whether a custom websocket event is dispatched at all), plus a
Python‑only probe that drives the download task lifecycle directly. Every item
below was first _reproduced_, then fixed, then re‑verified.

**Blocking I/O in request handlers**

- **`GET /model-manager/model-info` blocked the event loop** — the Civitai /
  Hugging Face URL search behind _Create Download Task_ performs several
  blocking `requests.get` round trips inline (for Hugging Face: the model info
  **and** the recursive file tree). Moved to the executor.

**Downloads froze the whole ComfyUI server (regression from the asyncio rewrite)**

- Upstream ran every download in a **dedicated worker thread with its own event
  loop**, so the blocking `requests` calls were harmless. `DownloadThreadPool`
  was rewritten to asyncio and now schedules the coroutine on ComfyUI's **main**
  loop, but `download_model_file_http` still called `requests.get(stream=True)`
  and iterated `iter_content()` inline. Consequences, all measured: the connect /
  response‑header phase blocked the entire server with **no socket timeout** (one
  unresponsive host hung ComfyUI outright); between chunks the loop only regained
  control once per second, starving every other websocket push and request; a download URL served by ComfyUI itself **deadlocked permanently**.
  Probe result on the unmodified backend: `GET /download/task` two seconds into a
  transfer **timed out**; after the fix it answers in 0.00 s while the transfer
  runs. The Hugging Face branch already used `run_in_executor`; the plain HTTP
  branch was missed and now offloads the same way, marshalling progress back with
  `asyncio.run_coroutine_threadsafe` exactly like the HF `tqdm` hook.
- **The response must be closed from inside the worker thread.** Closing it in a
  loop‑side `finally` ran concurrently with the thread's `iter_content()` and
  blocked the event loop on urllib3's read lock — measured at **8 s of total
  server unresponsiveness after every pause**.
- **Pausing never reached the UI.** `pause_model_download_task` cancels the task,
  so the download coroutine never reached its own “paused” push; the Download
  List kept showing the pause button and a live speed read‑out for a task that
  had already stopped, until a manual refresh. The state is now pushed from the
  pause handler. Verified end to end: pause → resume → complete, size frozen
  while paused, growing again after resume, and exactly **one** task per file
  (the duplicate‑submit guard holds).

**“Upload to Hugging Face” reported a false failure for every real model**

- `POST /hf/upload` only answers once the whole file has been transferred, so it
  always outlives the same 60 s client timeout: the UI showed a red
  `Error / Fetch timeout` toast and hid the progress bar while the server carried
  on and uploaded the file successfully. `py/upload_hf.py` emitted
  `hf_upload_complete` — and **nothing listened for it**. Completion is now driven
  by the websocket events; a client abort is only ignored once the server has
  acknowledged the upload (first progress push), so a genuine failure still
  reports. Verified: with a 12 s server‑side upload and a 4 s client timeout the
  bar stays up throughout and the success toast arrives on completion.
- The bar sat motionless at 0 % for the entire transfer (`huggingface_hub`
  exposes no per‑chunk callback, so only 0 % and 100 % are ever sent). It now
  renders **indeterminate** until a real percentage exists.

**One click created two download tasks**

- The Create Download Task button carried both `type="submit"` **and**
  `@click="createDownTask(currentModel)"`, inside `ModelContent`'s
  `<form @submit.prevent>`. Every click therefore created two tasks: the second
  failed with `File already exists: …` (observed), or — when they raced — two
  tasks downloaded the same file into different `<task>.download` files and both
  moved onto the same model path. The first one also used the **unedited** model,
  discarding every change made in the editor (preview choice, description,
  type / sub‑folder). Upstream had only `type="submit"`; that is restored.

**PrimeVue was removed, but its icons and CSS variables were not**

Nine places still rendered raw PrimeIcons markup. Nothing defines `.pi-*` any
more (the built stylesheet contains **zero** such rules and no icon font), so
every one of them was an empty, invisible box:

- `<GlobalLoading/>`'s spinner — the overlay dimmed the screen with **no spinner**
  in it, so long operations gave no feedback at all.
- `DialogCreateTask`'s **search button** — invisible; only the Enter key still
  started a Civitai / Hugging Face / direct‑link search.
- `hooks/config.ts`'s `iconButton` — the **API‑key edit and delete controls in
  ComfyUI's settings panel** were invisible 16 px gaps. ComfyUI's settings dialog
  lives outside this extension's Vue app, so the Lucide icon is mounted with Vue's
  low‑level `render()`.
- `ResponseSelect`'s prefix — `<i :class="prefixIcon">` (the sort‑order indicator
  in both model views). A dynamic `:class` binding, which is why the class‑name
  linter never saw it.
- The `Box` empty‑state icons in `DialogManager` / `DialogCreateTask` /
  `DialogHfUpload`, the `CheckCircle` on the direct‑file banner, and the two
  `Info` icons in `ModelDescription`.
- `ModelDescription` also styled itself with **undefined PrimeVue variables**
  (`--p-form-field-border-color`, `--p-form-field-focus-border-color`,
  `--p-surface-500/700`, `--p-dialog-background`). Those declarations are invalid
  at computed‑value time, so the description textarea had **no border and no
  focus ring**, and the rendered markdown lost its heading rules, blockquote bar
  and code background. All mapped onto the `--mm-*` tokens.
- The right‑click menu built an `icon` for every item and never rendered it.

**Confirm dialogs ignored their own options**

- Every caller passes `icon: 'pi pi-info-circle'` and
  `acceptProps: { severity: 'danger' }` / `rejectProps: { outlined: true }`, and
  `GlobalConfirm` discarded all of them — so “Delete this model?”, “Delete this
  download task?” and “Delete API key?” looked **exactly like Cancel**. The icon
  resolves through the Lucide map and `severity: 'danger'` now maps to the
  `destructive` button variant.

**Credentials were one `git add .` away from being committed**

- `.gitignore` contained `private.keypackage-lock.json` — two patterns
  concatenated onto one line, so **neither was ignored**. `private.key` is the
  pickle holding the user's Civitai and Hugging Face tokens, and it showed up as
  untracked in every checkout. Split apart; `git check-ignore` now confirms both.

**Prose was leaking into the shipped stylesheet**

- Tailwind v4 auto‑detects source files across the whole project, so ordinary
  English words in `README.md` and in Python comments became class candidates:
  the build really did emit global `.paused{animation-play-state:paused}` and
  `.contents{display:contents}` rules into the stylesheet this extension injects
  into ComfyUI's page. `src/style.css` now turns automatic detection off
  (`source(none)`) and declares `@source '../src'` + `@source '../index.html'`,
  the only places real class names live. The stylesheet is a pure function of
  the sources again, and the generated selector set is unchanged apart from the
  four utilities this pass stopped using (the two `--p-form-field-*` borders,
  `text-4xl` and the prose‑derived `contents`) — **nothing was added**.

**The linter was configured to hide exactly this bug class**

- `eslint-plugin-tailwindcss` whitelisted `^(pi|md|mdi)(-.+)?$` with the comment
  _“PrimeIcons classes rendered by the ComfyUI host stylesheet”_ — the host does
  not ship PrimeIcons. The entry is removed and the rule verified to flag a
  re‑introduced `pi pi-box`, so a future leftover fails `pnpm lint`.

All of the above was verified with `pnpm typecheck`, `pnpm lint`,
`pnpm format:check`, a clean `pnpm build`, and the harness suites. The Python
changes were additionally checked with `ruff` (`E9,F82,F811,F841,B,PLE`): no new
findings.

<a id="pass-4"></a>

## <img src="https://api.iconify.design/lucide/gem.svg?color=%238b5cf6" width="28" height="28" align="middle" alt=""> Fourth reliability pass (glassmorphism completion, scoped preflight, last bug fixes)

A UI-wide audit against live screenshots found the one thing the earlier
passes could not see: **the browser's own stylesheet was painting half the
interface**. Neo intentionally ships without Tailwind's preflight (the ComfyUI
host page must stay untouched), and the dialogs teleport to `<body>`, outside
the `#comfyui-model-manager` scope that normalises border colours. Every
native `<button>`/`<input>`/`<textarea>` without an explicit background or
border therefore kept the **UA face** — an opaque grey slab with a light
outline under a dark colour-scheme — which is exactly the "grey box, white
ring" look on toolbar icons, tabs, checkboxes, toast buttons and the
select/input fields. Colour-less `border` utilities also fell back to
Tailwind v4's `currentColor` default, drawing **white table grids** inside the
model-info dialog.

**Design contract now enforced everywhere**

- _Grey push buttons_ (`secondary`, `ghost`, `outline`) render on a
  **translucent foreground tint** (`bg-mm-fg/5…/9`) with a **hairline border**
  (`border-mm-fg/10…/15`), `backdrop-blur` and a density-matched neutral glass
  shadow (`--mm-shadow-glass-1/2`).
- _Coloured push buttons_ (`default`, `destructive`) render as a **skeleton of
  their own colour** (`bg-mm-accent/16`, `bg-mm-danger/14`) with a hairline of
  the same colour and a **shadow tinted with the lightened colour**
  (`--mm-shadow-accent-*`, `--mm-shadow-danger-*`, built with `color-mix` so
  they follow the host palette).
- _Non-push controls_ (select/input triggers, dropdown tabs, tabs list,
  checkbox, slider, progress, badges, chips, toast buttons) each got their own
  translucent treatment; hover/selected tints (`--mm-surface-hover`,
  `--mm-surface-selected`) are now pure translucent mixes instead of opaque
  surface fills, so glass stays see-through.
- Neutral elevation tokens are **theme-aware** (soft slate shadows in light
  mode, deep black ones under `.dark-theme`); hard-coded `bg-gray-*`,
  `text-gray-*`, `bg-green-50`… panels were mapped onto the `--mm-*` tokens.
- A **scoped preflight** (`@layer base`, `:where(#comfyui-model-manager,
.mm-scope) :where(button, input, textarea, select)`) resets UA faces, fonts
  and borders at zero specificity; every teleported root (dialog, alert-dialog,
  sheet, dropdown, select, tooltip) carries the new `.mm-scope` marker so the
  reset reaches `<body>`-level portals. Utilities still override it, so no
  component lost its explicit styling.

**Bug fixes in this pass** (behaviour-preserving, each reproduced first)

- `DialogCreateTask`: a failed preview download re-threw inside
  `createDownTask`, whose promise nobody awaits — the failure surfaced as an
  **unhandled promise rejection** after the toast had already reported it. The
  submit now aborts cleanly.
- `useModels.remove`: a failed `DELETE` never settled the returned promise, so
  callers awaiting it hung forever; the error toast still shows.
- `py/information.py`: `version["images"]` raised `KeyError` for Civitai
  versions without images, and `markdownify(None)` raised `TypeError` when the
  API sent an explicit JSON `null` description — both aborted the whole
  search. Both are guarded now.

**Verification harness (new, `harness/`)**

Two suites drive the **real** code, not mocks of it:

- `pnpm verify:py` — imports the actual extension package against stubbed
  ComfyUI modules (`folder_paths`, `server`, `comfy.utils`) and exercises every
  route over real HTTP: listing + hidden-file toggle, info read, edit /
  rename / preview set & remove / delete, direct-link download **into a
  sub-folder**, pause / resume / delete of a throttled download, local upload
  plus its path-traversal and folder-validation guards, preview serving and
  the Hugging Face token guards. 37 assertions.
- `pnpm verify:e2e` — serves the committed production bundle
  (`web/manager.js` + stylesheet) from that same backend, loads it in headless
  Chromium behind a faithful `window.comfyAPI` mock, and asserts behaviour
  (open manager, flat ⇄ folder, model detail, tabs, confirm dialog, download
  dialogs, light/dark) **and the glass contract** (translucency `0 < alpha < 1`,
  1px borders, `backdrop-filter`, non-empty shadows, zero console errors).
  26 assertions; screenshots land in `harness/shots/` (git-ignored).

All of the above passes `pnpm typecheck`, `pnpm lint`, `pnpm format:check` and
a clean `pnpm build` on the committed bundle.

<a id="pass-5"></a>

## <img src="https://api.iconify.design/lucide/life-buoy.svg?color=%23f97316" width="28" height="28" align="middle" alt=""> Fifth reliability pass (download creation & HuggingFace upload lifecycle)

Two user-reported failures were reproduced in the harness first, then fixed:

**"Create Download Task does nothing"**

- The direct-link model-type selector offered a **hard-coded catalogue of all
  16 ComfyUI model types**. Choosing one the running ComfyUI has no folder for
  ("GLIGEN", "Classifiers", …) only failed at task-creation time with
  `PathIndex 0 is not in <type>` — from the user's side the Download click
  appeared dead. The list is now built from the folders that **actually
  exist** (pretty labels kept), so every offered target is placeable.
- A failed **browser-side preview fetch** (CORS, hotlink protection, offline
  CDN) aborted the whole submission. The raw preview URL is now handed to the
  backend as a fallback string: `save_model_preview()` downloads it
  server-side, where CORS does not exist, and degrades to "no preview" if
  that fails too. The task is always created. (`py` probe `P08b` covers the
  URL-preview path.)
- While reproducing this, `PUT /model-manager/model/…` turned out to run its
  preview download + PIL re-encode **inline in the handler**, freezing the
  event loop (deadlocking outright when the preview URL points back at
  ComfyUI). It now runs in the executor, like the other blocking handlers.

**"HuggingFace upload: no progress, and closing the window cancels it"**

- `POST /hf/upload` used to answer only after the **whole transfer**, inside
  the request handler. ComfyUI's `api.fetchApi` aborts header-slow requests
  after 60 s and aiohttp cancels handlers whose client goes away — closing
  the dialog (or just exceeding the timeout on a multi-GB file) killed the
  coroutine that reports progress and completion.
- The upload now runs as a **background task on the shared download pool**;
  the handler validates, emits the initial progress event and returns a
  `taskId` immediately. Completion/failure travel as `hf_upload_complete` /
  `hf_upload_error` websocket events, so no client behaviour can cancel a
  running upload any more.
- The upload state moved into a module-level store (`hooks/hfUpload`): the
  progress bar keeps running while the dialog is closed, **re-appears when the
  dialog is re-opened**, and the success/error toast is raised exactly once,
  even with the dialog closed.

The harness gained a websocket bridge (the stub server forwards every
`send_json` push to the page, like ComfyUI's socket does) and two regression
scenarios: `E13` (direct-link task creation end-to-end) and `E14` (HF upload
progress survives closing the dialog and completes). Current totals:
`pnpm verify:py` 37 assertions, `pnpm verify:e2e` 26 assertions, plus
`typecheck` / `lint` / `format:check` / clean `build`.

<a id="pass-6"></a>

## <img src="https://api.iconify.design/lucide/rocket.svg?color=%2322c55e" width="28" height="28" align="middle" alt=""> Sixth reliability pass (HF upload acceptance, preview defaults, view & hover defaults)

- **HuggingFace upload accepted again**: `huggingface_hub` validates
  `path_or_fileobj` with `isinstance(..., (str, bytes, io.BufferedIOBase))`,
  so the progress‑reporting wrapper introduced in the fifth pass was
  rejected with `ValueError: path_or_fileobj must be either an instance of
str, bytes or io.BufferedIOBase` before any transfer started. `_ProgressFile`
  now subclasses `io.BufferedIOBase` (verified against the real library's
  `CommitOperationAdd`), and the harness fake enforces the very same
  validation so this class of regression fails `pnpm verify:e2e` instead of
  production.
- **`NO-PREVIEW.svg` is the default, not a fallback**: preview‑less models
  carry the dedicated `GET /model-manager/no-preview.svg` URL in the model
  list (and download tasks map their `no-preview` sentinel to it). The
  preview routes lost their substitute‑artwork fallbacks and the
  `except: abs_path = extension_uri` catch‑all; unknown previews are a plain
  404 now.
- **The flat grid is the initial view** (`ModelManager.UI.Flat` defaults to
  `true`; a persisted user setting still wins).
- **Folder hover animations are gated**: the opening morph starts after the
  pointer rested on a folder for ≥ 1 s, the closing morph after it stayed
  away for ≥ 1 s.

Harness totals after this pass: `pnpm verify:py` 40 assertions,
`pnpm verify:e2e` 36 assertions (including the 1 s hover gates, the default
flat view, the default no‑preview artwork and the BufferedIOBase acceptance),
plus `typecheck` / `lint` / `format:check` / clean `build`.

<a id="pass-7"></a>

## <img src="https://api.iconify.design/lucide/git-commit-horizontal.svg?color=%23ef4444" width="28" height="28" align="middle" alt=""> Seventh reliability pass (honest HuggingFace completions)

Re‑uploading a model whose identical content already sits at the destination
looked like a broken upload: HuggingFace accepts the request, transfers
nothing (`Upload 0 LFS files`), skips the empty commit
(`No files have been modified since last commit`) and returns a `CommitInfo`
built from the **existing** HEAD — which this extension used to report as a
plain successful upload, with no transfer progress to show either.

- `run_upload` now records the repository HEAD sha before the transfer and
  compares it with the returned commit oid. Equal oids mean the Hub skipped
  the commit, and the completion event carries `skipped: true`.
- The UI raises an explicit warning toast — _"An identical file already
  exists at '<path>' in '<repo>' — HuggingFace skipped the empty commit"_ —
  instead of a silent success; real commits still toast success and new
  content still streams accurate percentages through the `_ProgressFile`
  wrapper (the documented trade‑off: binary‑IO payloads use the classic LFS
  transfer, not Xet).
- The harness fake reproduces the Hub's skip semantics (second upload of the
  same `(repo, path)` returns the existing head sha), and `E14g` asserts the
  warning toast, so a future regression to silent no‑ops fails
  `pnpm verify:e2e`.

- **Dependency pin `huggingface_hub>=0.34.0,<1.31.0`** (resolves to 1.30.0):
  the `hf` CLI distribution ("CLI extracted from the huggingface_hub library")
  is version‑paired with the library (`hf` X requires
  `huggingface_hub==X`), and the 1.31 line additionally changed upload
  streaming internals (`SliceFileObj.__iter__`) relative to the field‑proven
  1.30 line. Environments that keep the `hf` CLI beside this extension
  therefore stay on the 1.30 line. The pin is **enforced at startup**:
  `is_installed()` now evaluates version ranges, so an out‑of‑range
  installation (e.g. 1.31.x) triggers a correcting `pip install` instead of
  being accepted silently. Verified against the real 1.30.0 wheel
  (`CommitOperationAdd` acceptance, `repo_info`, skip semantics).

Harness totals after this pass: `pnpm verify:py` 40 assertions,
`pnpm verify:e2e` 37 assertions, plus `typecheck` / `lint` / `format:check` /
clean `build`.

<a id="pass-8"></a>

## <img src="https://api.iconify.design/lucide/link.svg?color=%23f97316" width="28" height="28" align="middle" alt=""> Eighth reliability pass (pre-flight duplicate detection for HuggingFace uploads)

Re‑uploading unchanged content made the Hub refuse an empty commit
(`Upload 0 LFS files` + `No files have been modified since last commit`),
which from the outside still looked like a broken upload even with the
seventh pass's post‑hoc warning: the extension first paid for a hash pass, a
preupload and an LFS batch round‑trip that could never produce a commit.

- `run_upload` now runs a **pre-flight check** before any transfer: it hashes
  the local file and compares the digest with the sha256 of the matching
  entry in the remote tree (`model_info(..., files_metadata=True)`). An
  exact match short‑circuits the upload — no transfer attempt, no confusing
  Hub round‑trips.
- The completion event then carries the **blob URL** of the file that already
  lives in the repository, and the UI toast links it: _"An identical file
  already exists in '<repo>': https://huggingface.co/<repo>/blob/main/<path> —
  HuggingFace skips empty commits, so nothing was transferred. Use a
  different destination path to create a new commit."_
- Any pre-flight failure degrades to "go", so a real upload is never blocked
  by the check itself; the seventh pass's oid comparison stays as a backstop
  for races (file changed between check and transfer).
- Harness: the fake Hub now serves a real sha256 tree (`model_info`), `E14g`
  asserts the linked skip toast and `E14h` asserts that a duplicate upload
  performs **zero** transfer reads.

Harness totals after this pass: `pnpm verify:py` 40 assertions,
`pnpm verify:e2e` 38 assertions, plus `typecheck` / `lint` / `format:check` /
clean `build`.

<a id="pass-9"></a>

## <img src="https://api.iconify.design/lucide/scroll-text.svg?color=%230891b2" width="28" height="28" align="middle" alt=""> Ninth reliability pass (upload honesty, stacking order, panel‑scoped loading, editing reach, Japanese)

A user‑reported failure (“uploading to an existing private repository prints
`Upload 0 LFS files` and the upload never starts”) was reproduced against the
**real** `huggingface_hub` 1.30.0 pointed at a local Hub emulator that replays
the reported HTTP trace byte for byte, then root‑caused and fixed; the same
audit fixed the popup stacking, the loading overlay and the editing reach.

**HuggingFace upload**

- **A zero‑byte commit was reported as a plain “Success”.** When the Hub already
  holds the exact bytes, the LFS batch answer carries no upload action
  (`Upload 0 LFS files`) yet a **new commit is still created** — so the old
  HEAD‑comparison never noticed, the progress bar never moved once, and a
  bare success toast appeared next to it. `_ProgressFile` now counts the bytes
  it actually hands to the transfer; a commit that moved none is reported as
  `deduplicated`, and the UI explains it with a link to the committed file.
- **The local hash pass was invisible.** Hashing a multi‑gigabyte checkpoint
  takes minutes during which nothing was sent and nothing was shown — the real
  reason an upload “never starts”. The hash pass is now a named phase
  (`Preparing…` / `Hashing…` / `Uploading…`) with live percentages, and the
  pre‑flight duplicate check compares **sizes first** so an unrelated file no
  longer pays for a full hash.
- **`_ProgressFile` mis‑detected its phase for files ≤ 512 B** (`from_fileobj`
  starts with `read(512)`, so the sample read already hit EOF and the hashing
  pass was mistaken for the transfer). Phase now flips on the first _true_ EOF.
- **huggingface_hub 1.30.0 crashes on a spec‑legal LFS batch answer.**
  `_validate_batch_actions` reads `response.get("actions", {}).get("upload")`,
  which raises `AttributeError` when the Hub answers `"actions": null` (the
  git‑-lfs way of saying “already in storage”). Verified against the real
  library; the upload now retries **once** through the file‑path route, which
  takes the `hf_xet` code path and never calls the batch endpoint.

**Popup stacking order**

- z‑indexes were scattered literals (`z-50` … `z-2800`, `9999`) plus three
  ad‑hoc inline `:style="{ zIndex: 2600 }"` patches. Everything teleported to
  `<body>` at Tailwind's default `z-50` — the **folder‑path picker**, the dialog
  overlay/content defaults, `SelectContent`, `SheetContent`/`SheetOverlay` —
  painted _behind_ the 2400+ dialog windows, i.e. at the very back. A single
  `--mm-z-*` scale in `style.css` (2400 dialog / 2700 nested / 2800 popover /
  2900 confirm / 3000 toast) is now the only source of truth, and every `ui/*`
  wrapper defaults to it.
- **Toasts were `position: static`.** `Sonner` runs `unstyled` and deliberately
  does not import vue‑sonner's stylesheet — which silently dropped the toaster's
  `position: fixed`, offsets **and z‑index** with it. Measured consequences: the
  toast container gave `#comfyui-model-manager` a real 70 px height (pushing the
  host page down), painted at `z-index: auto` underneath every dialog, and each
  toast overflowed its 356 px slot by 37 px because `box-sizing` fell back to the
  UA `content-box`. Positioning and box model are restored with scoped CSS only;
  the library stylesheet stays unimported so the host `<html>` is never polluted.

**Loading overlay**

- The viewport‑wide `fixed inset-0`, `z-index: 9999` scrim is gone. The overlay
  (`PanelLoading`) now renders **inside the topmost window only**, so a refresh
  dims and blurs that one panel while the canvas, the top bar and every other
  window stay visible and usable.
- `useLoading` had a live leak: a second `show()` for a target whose 200 ms grace
  timer was still pending orphaned the first timer, whose later firing left the
  global counter at 1 — the overlay then **never went away**. Pending shows for
  the same target are now a no‑op, and the counter can no longer go negative.

**Editing reach**

- The **Directory** row renders as a directory, with its trailing separator
  (`…/models/unet/`), in both the download editor and the saved‑model detail.
  The folder Tree keeps keying on the plain path through a dedicated
  `folderKey`, so display and selection cannot drift.
- The file‑name field accepts a **folder prefix** (`sub/name.safetensors`); `/`
  is no longer rejected as an illegal character (empty / `.` / `..` segments
  still are, and the backend re‑checks traversal). Missing directories are
  created on save.
- Editing a description no longer requires clicking an invisible full‑size
  overlay on top of the rendered markdown (which also swallowed the markdown's
  own links): an explicit **Edit** icon button opens the textarea.

**Japanese**

- `src/locales/ja.json` added; all three bundles carry the same 150 leaf keys
  (mechanically asserted), `Comfy.Locale` / `navigator.language` region and
  script subtags are normalised, and ~40 strings that were hard‑coded English
  (toast summaries, empty states, validation messages, model‑type labels, the
  API‑key dialog) moved into i18n. Note for future translators: vue‑i18n treats
  `|` as its plural separator, so a literal pipe must be written `{'|'}` —
  leaving it raw makes `t()` throw and silently disables the validator.

**Verification**

- `pnpm verify:py` 40 → **46 assertions** (folder‑prefix rename landing in a new
  sub‑folder, traversal still refused, missing `pathIndex` validated, a task
  without a description completing — the last one proven by a negative control:
  reverting the one‑line guard fails it).
- `pnpm verify:e2e` 38 → **64 assertions**: measured z‑index _and_ hit‑testing
  for menu / tooltip / nested picker / confirm / toasts, the panel‑scoped
  loading scrim (present inside the panel, absent over the host, gone when the
  request settles), the trailing‑slash Directory row, a real folder‑prefix
  rename moving the file on disk, the description Edit icon, and the Japanese
  bundle rendering under `?locale=ja`.
- `pnpm capture` / `pnpm capture --video` render every documentation image from
  the shipped bundle (see [Documentation](#documentation)).

<a id="documentation"></a>

## <img src="https://api.iconify.design/lucide/book-open.svg?color=%237c3aed" width="28" height="28" align="middle" alt=""> Documentation

Step‑by‑step usage guides, each complete and self‑contained:

- [`docs/USAGE-EN.md`](docs/USAGE-EN.md) — English
- [`docs/USAGE-JA.md`](docs/USAGE-JA.md) — 日本語
- [`docs/USAGE-ZN.md`](docs/USAGE-ZN.md) — 中文

They cover installation, both layouts, card interactions and drag‑to‑graph, the
model editor (folder picker, folder‑prefixed names, previews, descriptions),
downloads and the task list, the HuggingFace upload phases and completion
messages, settings and locales, plus a troubleshooting table. The screenshots
they embed live in [`docs/screenshots/`](docs/screenshots/) with a per‑file
manifest in [`docs/screenshots/README.md`](docs/screenshots/README.md).

Two further reference documents:

- [`docs/SPEC-ANSWERS.md`](docs/SPEC-ANSWERS.md) — the top‑bar button's
  customisation surface, the API‑key lifecycle, every ComfyUI setting this
  extension registers, and exactly how (and how many) preview images are stored.
- [`docs/OPTIMIZATION-REPORT.md`](docs/OPTIMIZATION-REPORT.md) — a no‑change
  audit of backend/frontend hot spots and standards‑catch‑up candidates, each
  with cost, benefit and risk.

<a id="pass-10"></a>

## <img src="https://api.iconify.design/lucide/sparkles.svg?color=%23f43f5e" width="28" height="28" align="middle" alt=""> Tenth pass (feedback surfaces, galleries, and the optimisation backlog)

**Toasts became the first-class feedback channel.** Every mutating operation now
reports its outcome — layout and hidden-file toggles, node add/copy, workflow
load, model update, pause/resume/delete of tasks, API-key save/remove, card-size
save/reset, local-upload start, model-info load failure — and the toasts
themselves were rebuilt: denser glass (22 px blur + saturation), a severity icon,
a tinted left bar and outer glow per severity, and a **manual dismiss button**
with a translated `aria-label`.

![toast stack](docs/screenshots/toast-stack.png)

**Previews are kept in full and can actually be looked at.** A model's whole
gallery is stored now (`<base>.<ext>`, `<base>.preview.<ext>`,
`<base>.preview<N>.<ext>`), the model list returns it as an array, the preview
area carries permanent **`<` / `>` buttons and an `i / n` counter** in both view
and edit mode, and tapping the preview opens a **full-screen lightbox**
(arrow keys and Escape work too). Saving with the "default" source keeps every
stored preview instead of silently deleting the extras.

![lightbox](docs/screenshots/lightbox.png)

**Environment-provided API keys are adopted.** With an empty `private.key`, a
token present in `HF_TOKEN` / `CIVITAI_API_KEY` is written into `private.key`
once (only the keys actually present in the environment), so it behaves exactly
like a key entered through the UI. `private.key` also moved from pickle to
**JSON with 0600 permissions**, removing a deserialization code-execution
surface.

**The optimisation backlog was executed** (everything except the single-chunk
bundle, which ComfyUI's injection model forbids): preview re-encode memoisation
with `ETag`/304, zero-stat model walks, cached folder tables, separated I/O and
CPU executors, an **aiohttp streaming downloader** (pause/resume/delete/Range
semantics unchanged, connect/read timeouts added), SVG artwork served over HTTP
with cache headers (the bundle lost 52 KB of inlined data URIs), per-card
ResizeObservers removed, debounced search, lazy locale bundles, `tw-animate-css`
replaced by nine hand-rolled keyframe classes, and the `huggingface_hub` pin
lifted to `<1.32.0` **after verifying 1.31.0 against all four emulated upload
scenarios**. `mypy` now checks the backend clean, a GitHub Actions workflow runs
the whole gate, and `eslint`'s `projectService` was trialled and rejected (it
OOMs ESLint on ≤2 GB machines — recorded in `eslint.config.js`).

Verification after this pass: `verify:py` **53 assertions**, `verify:e2e`
**75 assertions**, `mypy` clean, `typecheck` / `lint` / `format:check` / `build`
clean.

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
| `pnpm verify:py`                        | Python route/lifecycle probe (`harness/py_probe.py`, 53 assertions)     |
| `pnpm verify:e2e`                       | Headless-Chromium E2E + glass-contract audit (`harness/e2e.mjs`, 75)    |
| `python -m mypy --config-file mypy.ini` | Backend static types (C-3), clean                                       |

The harness needs `aiohttp` / `pillow` / `pyyaml` (ComfyUI provides them at
runtime, so they live in [`harness/requirements-dev.txt`](harness/requirements-dev.txt),
not in the runtime list): `pip install -r requirements.txt -r harness/requirements-dev.txt`.
| `pnpm capture` | Render the docs screenshots from the real bundle (`harness/capture.mjs`) |
| `pnpm capture --video` | Same, plus a recorded `hero.webm` / `hero.gif` tour |

> [!WARNING]
> `pnpm dev` **deletes the whole `web/` directory** before writing
> `manager-dev.js` (see the `dev()` plugin in `vite.config.ts`). That removes the
> committed production bundle — `web/manager.js` and `web/style-*.css` — from the
> working tree, so `git status` shows them as deleted. Committing in that state
> would ship an extension whose UI no longer loads. Always run `pnpm build`
> before committing, and never commit a tree where `web/manager.js` is missing.

A **husky** `pre-commit` hook runs **lint-staged** (ESLint `--fix` + Prettier) on
staged files.

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
│  ├─ download.py         #   download tasks (http + huggingface_hub)
│  ├─ upload.py           #   local file upload (path-validated)
│  ├─ upload_hf.py        #   upload to Hugging Face
│  ├─ information.py      #   Civitai/HF search by URL, preview serving
│  ├─ auth.py · config.py · thread.py · utils.py
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
system with its websocket progress protocol, the Civitai / HuggingFace page
parsers, the drag‑a‑card‑onto‑the‑graph integration, the model editor's form
plumbing, even the little affordances like the card‑size presets — is hayden‑cn's
design. Neo changes the skin, the dependencies and a great many bugs; it did not
have to invent the body. Reading the original remains the fastest way to
understand _why_ this codebase is shaped the way it is, and the honest
attribution for the architecture is: **theirs**.

This fork is a derivative work used and modified in accordance with the
**GNU General Public License v3.0**. Modifications in Neo (the UI rebuild,
PrimeVue removal, Hugging Face upload, package modernisation, toolchain, the
reliability/security passes above, the batch‑scan removal and the Japanese
localisation) are provided under the same GPL‑3.0 license. Per the license, the
original copyright notice and the full license text are preserved in
[`LICENSE`](LICENSE).

If this fork is useful to you, the upstream repository deserves the star: the
work standing on its shoulders is what makes any of the above possible.

Built with these excellent projects: [reka-ui], [Tailwind CSS], [Lucide],
[VueUse], [es-toolkit], [valibot], [vue-sonner], [huggingface_hub], [hf_xet].

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
[valibot]: https://valibot.dev
[vue-sonner]: https://vue-sonner.vercel.app
[huggingface_hub]: https://github.com/huggingface/huggingface_hub
[hf_xet]: https://github.com/huggingface/xet-core
[ComfyUI-Manager]: https://github.com/ltdrdata/ComfyUI-Manager
