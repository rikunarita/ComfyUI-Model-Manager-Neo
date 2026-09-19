# `docs/screenshots/` — manifest

This folder holds the images referenced by the README and the usage guides.
Each file documents a specific view of the extension; the table below says
exactly what every image should show so they can be (re)captured from a live
ComfyUI session.

> **Where the shots come from.** For README-quality images, open ComfyUI with
> the extension loaded and capture the views by hand — the table below says
> exactly what each file should show. Prefer the **dark theme** (the UI follows
> the host palette and the glass treatment reads best on dark) and aim for
> ~**1600 px** wide windows for consistency.

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
| `folder-picker.png`          | docs          | the nested folder-picker dialog painted **above** the model window (the stacking-order behaviour)                                                                              |
| `download.png`               | README, docs  | **Create Download Task** with a direct URL typed in                                                                                                                            |
| `download-resolved.png`      | docs          | the resolved editor: preview left of the gallery grid, version/file selectors, destination, description                                                                        |
| `hf-upload-step2.png`        | docs          | Hugging Face upload, model-selection step                                                                                                                                      |
| `hf-upload.png`              | README, docs  | Hugging Face upload step 3: repo id, private-on-create checkbox, destination path                                                                                              |
| `hf-upload-progress.png`     | docs          | the same dialog mid-transfer with the phase read-out (`Uploading… n%`)                                                                                                         |
| `hf-upload-toast.png`        | docs          | the completion toast stack above the manager                                                                                                                                   |
| `loading-panel.png`          | README, docs  | the **panel-scoped** loading scrim: only the manager window is dimmed/blurred                                                                                                  |
| `card-size.png`              | docs          | the Custom Size dialog (width/height sliders)                                                                                                                                  |
| `ja-view-flat.png`           | docs          | the flat layout in **Japanese**                                                                                                                                                |
| `ja-model-info.png`          | README, docs  | model detail in **Japanese**                                                                                                                                                   |
| `toast-stack.png`            | docs          | the three severities at once: glass body, severity icon, tinted left bar, manual close button                                                                                  |
| `lightbox.png`               | docs          | the full-screen preview viewer opened from a card preview, with `<` / `>` paging                                                                                               |
| `selection-mode.png`         | docs          | selection mode: round per-card checkboxes and the bulk action bar (add to workflow / delete)                                                                                   |
| `zipnn-button.png`           | docs          | the model detail window with the ZipNN call-to-action in the gap between preview and table                                                                                     |

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
