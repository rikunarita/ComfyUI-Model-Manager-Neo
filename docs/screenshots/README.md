# `docs/screenshots/` — manifest

Every image in this folder is a **real render of the shipped bundle**, produced by
the verification harness (`harness/serve.py` boots the actual Python routes plus
the committed `web/` bundle in headless Chromium at 1600×1000, dark theme):

```bash
pnpm capture          # PNGs only          (~60 s)
pnpm capture --video  # also records hero.webm and converts it to hero.gif
```

The capture driver is [`harness/capture.mjs`](../../harness/capture.mjs). Re-run
it any time the UI changes; the output is deterministic apart from the gradient
previews the harness synthesises for its demo library.

> **Where the shots come from.** The harness stand-in host is a plain gradient
> (ComfyUI itself is not running) and the model names/preview art come from the
> harness workspace, so these images document _this extension's_ chrome
> faithfully but not your own library. For README-quality shots of a real
> session, open ComfyUI with the extension loaded and grab the same views by
> hand — the table below says exactly what each file should show.

## Files

| File                         | Used by       | What it shows                                                                                                                                                                  |
| ---------------------------- | ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `hero.gif`                   | README header | ~10 s tour: open the manager, switch to the folder view, hover a folder (the glass opening animation), enter a folder, switch back, open a model                               |
| `hero.webm`                  | —             | the same tour as a lossless-enough recording; `hero.gif` is derived from it (`ffmpeg -vf fps=10,scale=900:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse`) |
| `view-flat.png`              | README, docs  | full window in the **Flat** layout: grid, search, type/sort/size selectors, glass chips                                                                                        |
| `view-flat-dialog.png`       | docs          | the manager window alone, flat layout                                                                                                                                          |
| `view-folders.png`           | README, docs  | **Folder** layout one level deep, with the breadcrumb trail                                                                                                                    |
| `view-folders-dialog.png`    | docs          | the folder-explorer window alone                                                                                                                                               |
| `model-info.png`             | README, docs  | model detail: preview, base-info table (**Directory ends with `/`**), Description tab                                                                                          |
| `model-edit.png`             | docs          | the same window in **edit mode**: type dropdown, folder button, name field with its folder-prefix hint                                                                         |
| `model-edit-description.png` | docs          | the description textarea opened through the **Edit icon**                                                                                                                      |
| `folder-picker.png`          | docs          | the nested folder-picker dialog painted **above** the model window (the stacking-order regression test)                                                                        |
| `download.png`               | README, docs  | **Create Download Task** with a direct URL typed in                                                                                                                            |
| `download-resolved.png`      | docs          | the resolved editor: version/file selectors, destination, preview, description                                                                                                 |
| `hf-upload-step2.png`        | docs          | HuggingFace upload, model-selection step                                                                                                                                       |
| `hf-upload.png`              | README, docs  | HuggingFace upload step 3: repo id, private-on-create checkbox, destination path                                                                                               |
| `hf-upload-progress.png`     | docs          | the same dialog mid-transfer with the phase read-out (`Uploading… n%`)                                                                                                         |
| `hf-upload-toast.png`        | docs          | the completion toast stack above the manager                                                                                                                                   |
| `loading-panel.png`          | README, docs  | the **panel-scoped** loading scrim: only the manager window is dimmed/blurred                                                                                                  |
| `card-size.png`              | docs          | the Custom Size dialog (width/height sliders)                                                                                                                                  |
| `ja-view-flat.png`           | docs          | the flat layout in **Japanese**                                                                                                                                                |
| `ja-model-info.png`          | README, docs  | model detail in **Japanese**                                                                                                                                                   |
| `toast-stack.png`            | docs          | the three severities at once: glass body, severity icon, tinted left bar, manual close button                                                                                  |
| `lightbox.png`               | docs          | the full-screen preview viewer opened from a card preview, with `<` / `>` paging                                                                                               |

## Not captured here (capture live instead)

| File             | Why                                                                                   | What to shoot                                                                                          |
| ---------------- | ------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| `settings.png`   | the API-key rows live in **ComfyUI's own** Settings page, which the harness stubs out | ComfyUI Settings → _Model Manager Neo_ → _API Key_, showing both key rows with their edit/delete icons |
| `node-graph.gif` | needs a real LiteGraph canvas                                                         | 4–6 s clip dragging a model card onto the canvas, spawning a loader node with the model preselected    |

## Capture tips for live shots

- Run ComfyUI in the **dark theme** — the UI follows the host palette, and the
  glass treatment reads best on dark.
- Aim for ~**1600 px** wide windows; export GIFs at ~8–12 fps to keep them small.
- Prefer a library with at least one model **with** and one **without** a
  preview, so the NO‑PREVIEW artwork is visible.
- Trim/round the dialog edges if you like, but keep the toolbar and chips
  legible.

Once you have replaced a file you can delete this manifest, or keep it as
documentation for future contributors.
