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

## 🩹 Second reliability pass (batch scan, model editor, task pool)

A second end‑to‑end audit — driven by a headless harness that runs the real
`web/manager.js` bundle against the real Python routes over HTTP + WebSocket —
found and fixed the following. Nothing here changes intended behaviour; each
item restores behaviour that was documented but silently broken.

**Batch scan (the "no results are displayed" report)**

- **`<Progress>` dropped its default slot.** The reka‑ui wrapper never rendered
  `<slot />`, so `DialogScanning`'s `{{ done }} / {{ total }}` counter was
  discarded. Combined with an indicator that is translated fully out of view at
  0 %, the scan dialog showed _nothing at all_ while a scan was running. The
  PrimeVue `ProgressBar` this replaced renders `<slot>{{ value + '%' }}</slot>`.
  The label is now drawn as an overlay centred on the track (the root needs
  `overflow-hidden` to clip the sliding indicator).
- **Stale `GET /model-info/scan` responses could rewind a running scan.** The
  dialog fetches the task state on mount, _before_ the user can press a scan
  button; when that reply landed after the `POST` that started the scan it
  described a world with no task, so it wiped the progress, fired a bogus
  "scan completed" toast and pushed the dialog back to the type‑selection step —
  where it stayed, hiding every later update. Scan state now carries a
  generation stamp, in‑flight syncs that are overtaken are discarded, and the
  progress step is never left while a scan is in flight.
- **Creating a scan task blocked the server event loop.**
  `create_scan_model_info_task` walked the whole model library with a
  synchronous `os.walk` inside the request handler (same class of bug already
  fixed for hashing/Civitai lookups). It now runs in the executor, with the
  request‑scoped setting resolved beforehand.
- **`GET /models/{folder}` blocked the event loop too** — every model list
  refresh (including the one fired when a scan completes) stat'ed every file
  inline. Also moved to the executor.

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

## 🩻 Third reliability pass (blocking I/O, PrimeVue leftovers, false failures)

A third end‑to‑end audit, again driven by a headless harness that runs the real
`web/manager.js` bundle inside jsdom against the real Python routes over
HTTP + WebSocket (with a faithful mock of `window.comfyAPI`, including
`api.fetchApi`'s 60 s response‑header timeout and the `_registered` gate that
decides whether a custom websocket event is dispatched at all). **160
assertions across 8 suites**, plus a Python‑only probe that drives the download
task lifecycle directly. Every item below was first _reproduced_, then fixed,
then re‑verified.

**Batch scan — the “no results are displayed” report (root cause)**

- **The progress step was reachable only through a successful
  `POST /model-info/scan` response.** That request cannot answer until the
  server has walked the entire model library (`create_scan_model_info_task`
  runs `os.walk(followlinks=True)` over every registered model folder before it
  replies), and ComfyUI's `api.fetchApi` aborts any request whose response
  headers have not arrived within **60 s**
  (`FETCH_RESPONSE_HEADERS_TIMEOUT_MS = 60_000`, ComfyUI_frontend
  `src/scripts/api.ts`). On a large library the promise rejects — but the
  server keeps going: aiohttp does not cancel the handler when the client
  disconnects, so the task file is written and the scan runs to completion,
  logging exactly `Send update scan information task to frontend.` and
  `Completed scan model information.` The `catch` had already parked the dialog
  on the type‑selection step and **nothing ever moved it forward again**, so the
  websocket pushes were received by the store and silently discarded.
  Reproduced: with the POST aborted, the dialog showed _no_ progress bar at all
  even after 4 scan events had arrived.
  The dialog now follows the **store** — `watch([scanning, updates])` promotes it
  to the progress step whenever a scan is known to be running, from any source
  (POST response, websocket push, or server sync) — and the `catch` reconciles
  with `GET /model-info/scan` before falling back and reports a real error
  instead of failing silently. Verified: the same aborted POST now renders
  `4 / 4` at 100 % the moment the pushes land.
- **`scan_paths` walked the same directory once per alias.** ComfyUI registers
  one directory under several model types (`text_encoders` → `[text_encoders,
clip]`, `diffusion_models` → `[unet, diffusion_models]`) and custom nodes add
  more via `add_model_folder_path()`. `scan_models` is keyed by absolute path,
  so de‑duplicating is provably a no‑op: against a fixture with three extra
  aliased paths the old and new backends returned **byte‑identical** payloads
  (same keys, order and values for both `diff` and `full`) while the number of
  `Found model:` walk hits dropped from 22 to 8.
- **`GET /model-manager/model-info` blocked the event loop too** — the Civitai /
  Hugging Face URL search performs several blocking `requests.get` round trips
  inline. Moved to the executor, like the hashing and library walks before it.

**Downloads froze the whole ComfyUI server (regression from the asyncio rewrite)**

- Upstream ran every download in a **dedicated worker thread with its own event
  loop**, so the blocking `requests` calls were harmless. `DownloadThreadPool`
  was rewritten to asyncio and now schedules the coroutine on ComfyUI's **main**
  loop, but `download_model_file_http` still called `requests.get(stream=True)`
  and iterated `iter_content()` inline. Consequences, all measured: the connect /
  response‑header phase blocked the entire server with **no socket timeout** (one
  unresponsive host hung ComfyUI outright); between chunks the loop only regained
  control once per second, starving every websocket push — including batch‑scan
  progress; a download URL served by ComfyUI itself **deadlocked permanently**.
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
findings, and the one pre‑existing `B007` in the scan loop disappeared with the
de‑duplication.

---

## 🩼 Fourth reliability pass (the scan counter that never reached 100 %)

Follow‑up to the third pass, after the report that the batch scan now displayed
progress but **stopped one short of the end** — `1/12 … 10/12, 11/12`, then the
model‑list refresh spinner appeared and went away, and the dialog stayed on
`11 / 12` forever.

**Root cause.** The counter is `scanCompleteCount / scanTotalCount`, where a
model counts as complete only when the backend sets `scan_models[path] = True`.
That assignment lives at the **end of the `try` block**, and the handler for a
model whose lookup fails only logged the error:

```python
except Exception as e:
    utils.print_error(f"Failed to download model info for {abs_model_path}: {e}")
```

A model that is **not indexed on Civitai** makes `search_by_hash` raise
`404 Client Error: Not Found for url: …/model-versions/by-hash/<sha256>` — which
is the normal case for any locally trained, renamed, re‑quantised or private
model. Such a model was therefore _never_ marked as processed:
`scanCompleteCount` could not reach `scanTotalCount`, the bar never hit 100 %,
the `data-state="complete"` styling never applied, and `complete_scan_…` arrived
carrying a map that still said `false` — so the dialog froze at `N‑1 / N` with
the scan in fact long finished. The refresh spinner from `notifyCompleted()` was
the only visible evidence that anything had ended.

Reproduced offline and deterministically (a harness knob raises the real
`requests.HTTPError(404)` for the hash lookup): the dialog stalls at `3 / 4`,
`aria-valuenow="75"`, `data-state="loading"`, and the completion payload reads
`{"…/notoncivitai.safetensors": false}`. After the fix: `4 / 4`, `100`,
`complete`, payload all `true` plus `"failed": 1`.

**A second, harder stall in the same loop.** The per‑model _prologue_ —
`get_model_preview_name()`, `os.path.isfile()`, `get_model_description_name()`
(which calls `os.listdir()`) — sat **outside** the `try`. If a model's folder
vanished mid‑scan (deleted, moved or unmounted while a multi‑hour scan was
running) the resulting `FileNotFoundError` escaped the loop **and the whole
task**: no completion event, no task‑file cleanup, and because the task file
survived, every later `GET /model-info/scan` re‑submitted the scanner and it
died the same way again. Measured on the pre‑fix commit: the dialog froze at
`4 / 5` and the backend logged `Task model_info_scan failed: [Errno 2] No such
file or directory` twice.

**Fixes** (`py/information.py`, `src/hooks/scan.ts`, locales):

- The whole per‑model body, prologue included, is now inside the `try` — one bad
  model can only ever cost that model.
- A model whose lookup failed is **counted as processed**, because the counter
  measures how many models were _attempted_, not how many lookups succeeded. The
  failure is still logged, and the progress push is sent from the handler
  (guarded, so a reporting problem can never abort the remaining scan).
- The completion event gained an additive `"failed": N` field; `models` is
  unchanged, so older frontends are unaffected.
- The frontend reports it instead of hiding it: `notifyCompleted(models, failed)`
  shows a **warning** toast — “Model information scan completed, but N model(s)
  failed. See the ComfyUI console for details.” (new `scanCompletedWithErrors`
  key, `en` + `zh`) — rather than an unconditional success.
- A `WARNING` summary line is logged next to the per‑model errors.

Marking a failed model as processed does not suppress retries: the task file is
deleted when the scan ends, and `diff` mode re‑derives “needs scanning” from the
preview/description files on disk, so the next scan attempts it again.

**The verification gap that let this through, and the guard added.** The third
pass asserted that the progress label _matched_ `^\d+ / \d+$` — which `3 / 4`
satisfies — instead of asserting that it _reaches_ the total, and the one fixture
model that 404'd was written off as “not on Civitai”. Every progress assertion
in the harness now requires `done === total`, `aria-valuenow === 100` and
`data-state === "complete"`, and two suites cover the failure paths directly:
`suite8` (Civitai 404) and `suite9` (a model folder deleted while the scan is in
flight — run against the pre‑fix commit to prove it stalls, and against the fix
to prove it completes). **180 assertions across 10 suites, 0 failures.**

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
