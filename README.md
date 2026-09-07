<div align="center">

# 🗂️ ComfyUI‑Model‑Manager‑Neo

### Browse · Download · Upload · Drag‑and‑drop — your models, beautifully managed.

A modern, glassmorphism re‑imagining of the ComfyUI model manager, rebuilt on
**Vue 3 + Tailwind CSS v4 + reka‑ui** with a fully modern toolchain.

![License](https://img.shields.io/badge/License-GPL--3.0-only-blue.svg)
![ComfyUI](https://img.shields.io/badge/ComfyUI-Custom%20Node-8A8B98.svg)
![Vue](https://img.shields.io/badge/Vue-3.5-4FC08D.svg?logo=vuedotjs&logoColor=white)
![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-v4-38BDF8.svg?logo=tailwindcss&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-6-3178C6.svg?logo=typescript&logoColor=white)
![ESLint](https://img.shields.io/badge/ESLint-10-4B32C3.svg?logo=eslint&logoColor=white)
![Prettier](https://img.shields.io/badge/Prettier-3-F7B93E.svg?logo=prettier&logoColor=black)
![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)

<!--
  ┌──────────────────────────────────────────────────────────────────────────┐
  │  🖼️  IMAGES TO PREPARE (this fork intentionally ships NO upstream images)  │
  │  Create a `docs/screenshots/` folder and drop the files listed below.      │
  │  Each placeholder in this README already points at its final path, so the  │
  │  picture appears automatically once you add the file. Suggested capture:   │
  │  a real ComfyUI window running this extension, dark theme, ~1600px wide.   │
  │                                                                            │
  │    1. docs/screenshots/hero.gif            – 8‑10s looping overview        │
  │    2. docs/screenshots/view-flat.png       – Flat "Models" grid            │
  │    3. docs/screenshots/view-folders.png    – Folder (explorer) view        │
  │    4. docs/screenshots/node-graph.gif      – drag a card onto the canvas   │
  │    5. docs/screenshots/download.png        – Create Download Task dialog   │
  │    6. docs/screenshots/hf-upload.png       – Upload to HuggingFace dialog  │
  │    7. docs/screenshots/model-info.png      – Model info (preview + tabs)   │
  │    8. docs/screenshots/scan.png            – Batch scan dialog             │
  │    9. docs/screenshots/settings.png        – ComfyUI settings (API keys)   │
  └──────────────────────────────────────────────────────────────────────────┘
-->

![Hero overview](docs/screenshots/hero.gif)

</div>

---

## ✨ Why Neo?

**ComfyUI‑Model‑Manager‑Neo** takes the excellent original manager and rebuilds
the experience from the ground up:

- 🎨 **Glassmorphism UI** — a translucent, blurred, elevation‑aware interface
  that follows ComfyUI's own light/dark palette automatically.
- 🧩 **PrimeVue‑free** — the entire PrimeVue dependency was removed and replaced
  with lightweight, headless **[reka-ui]** primitives + **Tailwind CSS v4** +
  **[Lucide]** icons (shadcn‑vue style components you can read and tweak).
- ⬆️ **Upload to Hugging Face** — publish any local model straight to a HF repo
  (creates the repo if needed, private option, live progress) — _new in Neo_.
- 🔗 **Direct‑link downloads** — paste a raw `.safetensors`/`.ckpt`/`.gguf` URL,
  pick the target folder, optionally choose a custom sub‑folder.
- ⚡ **`hf_xet` acceleration** — Hugging Face transfers use the chunked,
  deduplicated Xet protocol when available.
- 🖱️ **First‑class node‑graph integration** — drag a model onto the canvas to
  spawn or fill a node, drag embeddings into text areas, load workflows embedded
  in preview images.
- 📱 **Responsive** — designed for desktop, mobile and multi‑screen setups.
- 🧰 **Modern toolchain** — Vite 8 (Rolldown), TypeScript 6, ESLint 10 flat
  config, Prettier, husky + lint‑staged. Deterministic, lint‑clean builds.

> [!NOTE]
> Neo is a **fork** of [`hayden-cn/ComfyUI-Model-Manager`](https://github.com/hayden-cn/ComfyUI-Model-Manager)
> and is distributed under the same **GPL‑3.0** license. All credit for the
> original architecture belongs to its author — see [Credits](#-credits--attribution).

---

## 📸 Screenshots

> [!TIP]
> The images below are **placeholders**. Prepare the files listed in the
> `docs/screenshots/` checklist at the top of this README and they will render
> automatically. Capture them from a live ComfyUI instance running this
> extension (dark theme recommended, ~1600 px wide for consistency).

### Flat “Models” view — search, sort and resize the grid

![Flat models grid](docs/screenshots/view-flat.png)

_What to capture:_ the manager dialog in **Flat** layout showing a grid of model
cards with previews, the search bar, and the type / sort / card‑size selectors.

### Folder (explorer) view — navigate your directory tree

![Folder explorer view](docs/screenshots/view-folders.png)

_What to capture:_ the **Folder** layout with the breadcrumb trail and folder
cards, ideally one level deep inside a model type.

### Drag a model straight onto the graph

![Drag onto node graph](docs/screenshots/node-graph.gif)

_What to capture:_ a 4–6 s clip dragging a model card from the manager onto the
ComfyUI canvas, spawning a loader node with the model already selected.

---

## 🚀 Installation

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

## 🧭 Features

<details open>
<summary><b>Browse &amp; organise</b></summary>

- Two layouts: **Flat** grid and **Folder** explorer, switchable at any time.
- Real‑time search (supports `*` wildcards and multi‑token “AND” matching).
- Sort by name, size, date created or date modified.
- Adjustable card size (presets + fully custom dimensions).
- Toggle visibility of hidden (`.`‑prefixed) files without restarting.
- Image **and video** previews.

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
- **Batch scan** to fetch missing (or refresh all) information & previews by
  hash from Civitai.

</details>

<details>
<summary><b>Settings &amp; i18n</b></summary>

- API keys for **Civitai** and **Hugging Face**, stored locally in `private.key`
  (with `CIVITAI_API_KEY` / `HF_TOKEN` environment fallbacks). Keys migrate out
  of ComfyUI user settings on first run.
- Exclude model types from scanning; include/exclude hidden files.
- UI language follows ComfyUI's locale — **English** and **中文** bundled.

</details>

---

## 🆚 What changed from the original

This section makes the fork's differences explicit, as required by the GPL‑3.0
license. Functionality is preserved and extended; nothing was removed except the
PrimeVue dependency itself.

### 🎨 Interface

| Area              | Original                         | **Neo**                                                                         |
| ----------------- | -------------------------------- | ------------------------------------------------------------------------------- |
| Component library | PrimeVue 4                       | **reka‑ui** (headless) + shadcn‑vue‑style wrappers                              |
| Styling           | Tailwind CSS v3 + PrimeVue theme | **Tailwind CSS v4** with scoped `--mm-*` design tokens                          |
| Icons             | PrimeIcons                       | **Lucide** (`@lucide/vue`) via an icon map                                      |
| Look & feel       | Standard PrimeVue surfaces       | **Glassmorphism** (blur, elevation, micro‑interactions), auto dark mode         |
| Dialogs           | PrimeVue `Dialog`/`ContextMenu`  | reka‑ui dialogs, per‑dialog size/position, drag‑to‑move, anchored context menus |

### 📦 Packages

- **Removed:** `primevue`, `@primevue/themes`, `lodash`, `dayjs`, `js-yaml`.
- **Added / replaced:** `reka-ui`, `@lucide/vue`, `es-toolkit` (← lodash),
  `date-fns` (← dayjs), `yaml` (← js-yaml), `valibot` (runtime schema
  validation), `vue-sonner` (toasts), `class-variance-authority`, `clsx`,
  `tailwind-merge`, `tw-animate-css`.
- **Upgraded:** Vite 5 → **8** (Rolldown), TypeScript 5 → **6**, Vue i18n 9 →
  **11**, markdown‑it 14 → **15**, `@vueuse/core` 11 → **14**.
- **Python:** added `huggingface_hub` + `hf_xet`; asyncio task pool replacing the
  old thread pool.

### ⚙️ Toolbar / button roles

The manager header was redesigned into explicit, icon‑driven actions:
**batch scan**, **flat ⇄ folder layout toggle**, **show/hide hidden files**,
**refresh**, **download list**, and **upload to Hugging Face**.

### 🛠️ Toolchain

Biome was trialled and then **removed** in favour of a conventional,
fully‑configured **ESLint 10 flat config** + **Prettier** pipeline (see
[Development](#-development)).

---

## 🩺 Reliability pass (this revision)

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
  _extension_ instead of the name, an unanchored right‑click menu, a leaked scan
  event listener, the indeterminate progress bar, and several icon/i18n gaps.
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
[Development](#-development).

---

## 🔧 Development

You only need Node.js to **build** the web bundle; running the extension inside
ComfyUI needs nothing but Python.

```bash
corepack enable          # uses the pinned pnpm version
pnpm install
```

| Script                              | Purpose                                                                 |
| ----------------------------------- | ----------------------------------------------------------------------- |
| `pnpm dev`                          | Vite dev server (writes `web/manager-dev.js` for hot reload in ComfyUI) |
| `pnpm build`                        | Production build into `web/`                                            |
| `pnpm build:clean`                  | Remove `web/` then rebuild                                              |
| `pnpm typecheck`                    | `vue-tsc --noEmit` type checking                                        |
| `pnpm lint` / `pnpm lint:fix`       | ESLint (flat config)                                                    |
| `pnpm format` / `pnpm format:check` | Prettier (with the Tailwind plugin)                                     |

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
│  ├─ manager.py          #   model CRUD + scanning
│  ├─ download.py         #   download tasks (http + huggingface_hub)
│  ├─ upload.py           #   local file upload (path-validated)
│  ├─ upload_hf.py        #   upload to Hugging Face
│  ├─ information.py      #   Civitai/HF search, previews, batch scan
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

## 🙏 Credits & Attribution

ComfyUI‑Model‑Manager‑Neo is a derivative work of
**[`ComfyUI-Model-Manager`](https://github.com/hayden-cn/ComfyUI-Model-Manager)**
by **[hayden‑cn](https://github.com/hayden-cn)**, used and modified here in
accordance with the **GNU General Public License v3.0**. The original project's
architecture — model scanning, the download task system, Civitai/Hugging Face
search, node‑graph drag integration and the overall design — is their work, and
this fork is deeply grateful for it.

Modifications in Neo (UI rebuild, PrimeVue removal, Hugging Face upload,
package modernisation, toolchain, and the reliability/security pass above) are
provided under the same GPL‑3.0 license. Per the license, the original copyright
notice and the full license text are preserved in [`LICENSE`](LICENSE).

Built with these excellent projects: [reka-ui], [Tailwind CSS], [Lucide],
[VueUse], [es-toolkit], [valibot], [vue-sonner], [huggingface_hub], [hf_xet].

---

## 📄 License

**GPL‑3.0‑only** — see [`LICENSE`](LICENSE) for the full text.

<div align="center">

**If Neo saves you time, consider starring the repo ⭐ and thanking the
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
