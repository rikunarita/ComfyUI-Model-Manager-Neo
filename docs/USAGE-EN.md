# ComfyUI‑Model‑Manager‑Neo — Usage Guide (English)

> Sister documents: [日本語](USAGE-JA.md) · [中文](USAGE-ZN.md)
> Screenshots referenced below live in [`docs/screenshots/`](screenshots/) and are
> reproducible with `pnpm capture` (see [Screenshots](#screenshots)).

ComfyUI‑Model‑Manager‑Neo is a custom node that adds a model browser, downloader,
uploader and editor to ComfyUI. It never leaves the ComfyUI process: the backend
is a set of `aiohttp` routes inside the ComfyUI server, and the frontend is a
single bundled Vue 3 app injected into the page.

---

## Contents

1. [Installation](#1-installation)
2. [Opening the manager](#2-opening-the-manager)
3. [The two layouts](#3-the-two-layouts)
4. [Model cards](#4-model-cards)
5. [Model detail & editing](#5-model-detail--editing)
6. [Downloading models](#6-downloading-models)
7. [Uploading to HuggingFace](#7-uploading-to-huggingface)
8. [Upload from a local file](#8-upload-from-a-local-file)
9. [Settings](#9-settings)
10. [Languages](#10-languages)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. Installation

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/rikunarita/ComfyUI-Model-Manager-Neo.git
```

Restart ComfyUI. The Python dependencies (`huggingface_hub`, `hf_xet`,
`markdownify`) are installed automatically on first launch, and the prebuilt web
bundle ships inside the repository, so **Node.js is not required to run it**.

Manual install: download the repository archive, extract it into
`ComfyUI/custom_nodes/` and make sure the folder is named
`ComfyUI-Model-Manager-Neo`.

## 2. Opening the manager

There are four entry points; they all do the same thing:

| Entry point                            | Where                                                        |
| -------------------------------------- | ------------------------------------------------------------ |
| **“Model Manager Neo” top‑bar button** | the ComfyUI top bar (next to the settings gear)              |
| **Legacy menu button**                 | the old‑style menu container, if your frontend still has one |
| **Extensions menu**                    | `Extensions → Model Manager Neo`                             |
| **Command palette**                    | the `Comfy.ModelManager.Open` command                        |

The manager is a **non‑modal window**: it floats above ComfyUI but the canvas
stays fully interactive, so you can drag models onto the graph while browsing.
Windows are draggable by their title bar, resizable from any edge/corner, and
maximisable with the ⤢ button. Several windows can be open at once; clicking one
brings it to the front.

> The loading indicator is **scoped to the panel it belongs to** — while a
> request is in flight only that window is dimmed and blurred; the canvas, the
> top bar and every other window stay usable.
>
> ![panel-scoped loading](screenshots/loading-panel.png)

## 3. The two layouts

Switch with the first header button (grid ⇄ folder icon), or preselect the
default in **Settings → Model Manager Neo → UI → Flat Layout**.

### Flat layout

A single grid of every model of every type, with a toolbar:

- **Search** — multi‑token “AND” matching; `*` works as a wildcard
  (`*anime*` matches anything containing `anime`). Tokens match the file name
  _or_ the sub‑folder.
- **Type filter** — `All` or one model type.
- **Sort** — Name / Largest / Latest created / Latest modified.
- **Card size** — Extra Large / Large / Medium / Small, or **Custom Size**
  (a dialog with width/height sliders, persisted in ComfyUI settings).

![flat layout](screenshots/view-flat-dialog.png)

### Folder layout

A file‑manager style tree with a breadcrumb trail (each crumb carries a tiny
folder glyph). Double‑click a folder to enter it, use the breadcrumb or the ↑
button to go back. Right‑click a model for the context menu (**Open**).

![folder layout](screenshots/view-folders-dialog.png)

Both layouts share the **show/hide hidden files** header button (files and
folders whose name starts with `.`).

## 4. Model cards

![model card anatomy](screenshots/view-flat.png)

- **Preview** — image or looping video; models without a preview show the glass
  **NO PREVIEW** artwork.
- **Chips** (top right) — model type and file size, scaled with the card.
- **Folder cards** — a hand‑drawn glass folder that opens after the pointer
  rests on it for a second and closes a second after it leaves.
- **Hover actions** (flat layout, large cards) — **Add node**, **Copy node**,
  **Load workflow from preview**.
- **Drag to the graph** — drag any card onto the canvas:
  - onto empty canvas: creates the matching loader node with the model selected
  - onto an existing node: fills the matching combo input
  - an _embedding_ dragged onto a text area appends `(embedding:name:1.0)`
  - dragging a **preview image** loads a workflow embedded in it
- **Double‑click / single click** — opens the model detail window.
- **Tooltip** — hovering a card shows its absolute path.

## 5. Model detail & editing

![model detail](screenshots/model-info.png)

The window shows the preview (with a carousel when several previews exist), a
base‑info table, and two tabs.

| Row                                 | Meaning                                                                |
| ----------------------------------- | ---------------------------------------------------------------------- |
| Model Type                          | the ComfyUI model folder group                                         |
| **Directory**                       | the absolute directory **with a trailing `/`** — e.g. `…/models/unet/` |
| File Name                           | name without extension                                                 |
| File Size / Created At / Updated At | filesystem facts                                                       |

### Reading

- **Description** tab — rendered Markdown stored in a `*.md` file next to the
  model. Links open in a new tab.
- **Metadata** tab — the `__metadata__` block read straight from the safetensors
  header (nothing is cached or scanned in the background).

### Editing

Press the **pencil** to enter edit mode (the window turns into a form):

![edit mode](screenshots/model-edit.png)

- **Model Type** — dropdown of the types your ComfyUI actually has folders for.
- **Directory** — read‑only field plus the **folder button**, which opens a
  nested folder‑picker dialog with a tree of every base path and sub‑folder:

  ![folder picker](screenshots/folder-picker.png)

- **File name** — accepts a **folder prefix**. Typing
  `subfolder/my-model` files the model into `…/models/unet/subfolder/` on save
  (missing folders are created). `\ : * ? " < > |` and empty / `.` / `..`
  segments are rejected, and the backend re‑checks path traversal server‑side.
- **Preview** — `Default` (carousel) / `Network` (paste an image or video URL) /
  `Local` (drag & drop or pick a file; images are converted to WebP, videos keep
  their format) / `None` (removes every preview file).
- **Description** — press the **Edit (pencil) icon** next to the hint text to
  open the Markdown textarea; it saves when the textarea loses focus:

  ![description editor](screenshots/model-edit-description.png)

- **Save / Cancel** — Save issues a single `PUT`; anything that changed
  (name, type, directory, preview, description) is applied atomically per field.
- **Delete** (red trash) — removes the model **and** its previews and notes
  after a confirmation dialog.

## 6. Downloading models

Open **Download List** from the header, then:

### Create Download Task

![create download task](screenshots/download.png)

1. Paste a **Civitai model page**, **HuggingFace repo/blob/tree** or a **direct
   file link** (`.safetensors`, `.ckpt`, `.gguf`, …) and press **Enter** or the
   search icon.
2. For a direct link you must pick the **Model Type** first (only types your
   ComfyUI has are offered); an optional **Subfolder** field lets you place the
   file deeper.
3. Civitai/HF pages resolve to one or more **versions** and **files**; pick the
   version in the toolbar and the file in the editor.

   ![resolved result](screenshots/download-resolved.png)

4. In the editor you can set the destination type/directory, a file name
   (folder prefixes allowed), a preview image and a Markdown description
   (Civitai/HF descriptions are pre‑filled, including trigger words and
   YAML metadata).
5. **Download** starts a background task. The preview is fetched in the browser
   when possible and server‑side otherwise; if both fail the model still
   downloads, just without a preview.

### Download List

Two sections — **External Downloads** and **Local Uploads** — each row showing a
preview thumbnail, progress bar, transferred/total size and speed, with
**pause / resume / delete** controls. Deleting removes the partial file and the
task bookkeeping. Paused downloads resume with an HTTP `Range` request.

> Progress, pause and completion survive closing the window: tasks live in the
> backend and are pushed over the websocket.

## 7. Uploading to HuggingFace

Set your token first: **Settings → Model Manager Neo → API Key → HuggingFace
API Key** (or export `HF_TOKEN`).

Open **Upload to HuggingFace** from the header:

1. **Select model type** — a button per type.
2. **Select model** — the grid of that type; picking one pre‑fills the
   destination path with the model’s relative path.
3. **Upload to HuggingFace**:

   ![hf upload form](screenshots/hf-upload.png)

   - **Repository ID** — `username/repo-name`.
   - **Create as private if the repository does not exist** — applies _only on
     creation_; an existing repository keeps its own visibility.
   - **Destination path in repo** — directory + file name inside the repo.

Press **Upload**. The request returns immediately and the transfer runs in the
background, so closing the window never cancels it. The progress read‑out names
the current phase:

| Phase        | What happens                                                                                          |
| ------------ | ----------------------------------------------------------------------------------------------------- |
| `Preparing…` | token check, repository lookup, pre‑upload negotiation                                                |
| `Hashing…`   | the local sha256 is computed (a multi‑GB model can take minutes); **no bytes leave your machine yet** |
| `Uploading…` | the real transfer, with live percentages                                                              |

![hf upload progress](screenshots/hf-upload-progress.png)

### Messages you may see on completion

| Toast                                                               | Meaning                                                                                                                                                                                                     |
| ------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Success** — `path -> repo`                                        | a new commit was created and bytes were transferred                                                                                                                                                         |
| **Already stored on HuggingFace**                                   | the identical bytes already existed in the repository’s object store, so HuggingFace transferred nothing (`Upload 0 LFS files`) but a new commit pointing at them **was** created; the toast links the file |
| **Skipped** — “An identical file already exists in 'repo': <url> …” | the very same file already sits at that exact path; HuggingFace refuses empty commits, so nothing was done. Pick another destination path to create a new commit                                            |
| **Error**                                                           | the transfer failed; the message carries the backend reason                                                                                                                                                 |

## 8. Upload from a local file

**Download List → Upload from Local File**:

1. pick a model type,
2. pick a folder (or sub‑folder) in the tree,
3. choose the file.

The upload is registered as a **local task** in the Download List with accurate
progress and completes into the chosen folder. The destination is validated
server‑side (no arbitrary writes, no path traversal).

## 8b. Feedback, galleries and the lightbox

- **Toasts.** Every action reports its outcome: success (green), warning
  (amber), error (red), info (accent). Each toast carries a severity icon, a
  tinted left bar, and a **close button** in its top-right corner; they stack at
  the top-right above every dialog and auto-dismiss after their lifetime.
  ![toasts](screenshots/toast-stack.png)
- **All previews are kept.** Downloads and saves store every preview image of a
  model (`<name>.webp`, `<name>.preview.webp`, `<name>.preview2.webp`, …).
- **Paging.** When a model has more than one preview, the preview area shows
  **`<` / `>` buttons** and an `i / n` counter, in view mode and in edit mode.
- **Lightbox.** Clicking (tapping) the preview opens it full-screen; `<` / `>`
  or the arrow keys page through the gallery, `Esc`, the backdrop or the close
  button dismiss it.
  ![lightbox](screenshots/lightbox.png)
- **Environment keys.** If `private.key` is empty and `HF_TOKEN` /
  `CIVITAI_API_KEY` are exported, those keys are adopted into `private.key`
  automatically (only the ones actually present).
- **Oversized uploads.** A file above your ComfyUI server's upload limit
  (`--max-upload-size`, default 100 MB) is reported with a toast explaining
  exactly how to raise the limit, instead of a bare "HTTP 413".

## 8c. Multi-select and ZipNN compression

### Select files

The toolbar of both layouts has a **Select files** toggle (list-checks icon).
While it is on, every card and folder shows a round checkbox at its top-left;
clicking a card ticks it instead of opening it. As soon as one item is selected
a bulk bar appears at the bottom of the window:

- **Add to workflow** — creates one loader node per selected model;
- **Delete** — deletes every selected model after a Danger confirmation
  (previews and notes included);
- **Clear selection** — unticks everything. Leaving the mode also clears it.

### ZipNN compression

Opening a `.safetensors` model shows the **ZipNN artwork itself as the button**
in the gap between the preview and the info table: the shipped SVG draws its own
glass plate (including a dark-mode variant), lifts and brightens on hover, and
explains itself in a tooltip and to screen readers. Pressing it asks for a
confirmation that is deliberately _not_ styled as Danger, then compresses
tensor-by-tensor in the background:

- the button is replaced by a **progress bar** while the task runs;
- on success the original file is replaced by `<name>.znn.safetensors`;
  previews and notes follow the rename, and the grid refreshes by itself;
- opening a compressed model shows the same button with **inverted colours**
  and the label **ZipNN decompress**; pressing it confirms and restores the
  plain `.safetensors` file.

Compressed files follow the official ZipNN layout (`znn_compressed_vectors`
metadata, Huffman-compressed floating-point tensors), so loaders patched with
`zipnn_safetensors()` read them transparently. ZipNN is installed on first use
(`pip install zipnn`); it needs a C compiler **and** the Python headers
(`Python.h`) on Linux because PyPI ships no Linux wheels. If the install fails,
the error toast shows the first interesting pip line (the full output stays in
the ComfyUI console), names the missing prerequisite together with the
distro-specific command that fixes it, and offers a **retry** action - a failed
install is cached for five minutes so hammering the button never re-runs a
doomed build. Air-gapped hosts can drop a prebuilt wheel into
`assets/zipnn-wheels/`; it is preferred over PyPI.

## 9. Settings

ComfyUI **Settings → Model Manager Neo**:

### API Key

- **HuggingFace API Key** / **Civitai API Key** — stored locally in
  `private.key` next to the extension (masked in the UI), with `HF_TOKEN` /
  `CIVITAI_API_KEY` as environment fallbacks. Keys saved in older versions’
  ComfyUI user settings are migrated automatically on first run.

### Model List

- **Exclude model types (separate with commas)** — hides those types from the
  grids and pickers.
- **Include hidden files (start with .)** — same as the toolbar eye button.

### UI

- **Card Size** / **Card Size Map** — persistence for the size picker (hidden
  entries; edit them through the Custom Size dialog).
- **Flat Layout** — default layout on open.

## 10. Languages

The UI follows ComfyUI’s locale (**Settings → ComfyUI → Locale**) and ships
complete bundles for **English**, **中文** and **日本語**. Region/script
subtags (`ja-JP`, `zh-Hant-TW`, …) are folded onto their base language; anything
else falls back to English.

![Japanese UI](screenshots/ja-model-info.png)

## 11. Troubleshooting

| Symptom                               | Cause / fix                                                                                                                                       |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| The manager button is missing         | the frontend did not register the extension — check the ComfyUI log for an import error, and that the folder is named `ComfyUI-Model-Manager-Neo` |
| `HuggingFace token not set`           | set the token in Settings (or `HF_TOKEN`) and reopen the dialog                                                                                   |
| A download never starts               | the URL may need authentication (Civitai gated models) — set the Civitai key; the task row shows the server’s error text                          |
| “Failed to update model: PathIndex …” | the selected type has no folder on this machine — pick a type from the dropdown                                                                   |
| The UI looks unstyled / grey boxes    | you are looking at a stale `web/` bundle; rebuild with `pnpm build` (only needed when developing)                                                 |
| Preview shows NO PREVIEW              | the model has no preview file; set one in edit mode                                                                                               |

## Screenshots

All images in this guide are generated from the **real production bundle** by
the verification harness:

```bash
pnpm capture          # PNGs into docs/screenshots/
pnpm capture --video  # also records hero.webm and converts it to hero.gif
```

See [`screenshots/README.md`](screenshots/README.md) for the full manifest and
for how to replace them with captures from a live ComfyUI window.
