# Screenshots to prepare

This fork intentionally ships **no** images inherited from the upstream project.
Drop your own captures into this folder using the exact filenames below — the
root [`README.md`](../../README.md) already references them, so each picture
appears automatically once the file exists.

**Capture tips**

- Run this extension inside a real ComfyUI window.
- Use the **dark theme** for a consistent look (the UI follows ComfyUI's
  palette).
- Aim for ~**1600 px** wide; export GIFs at ~8–12 fps to keep them small.
- Trim/round the dialog edges if you like, but keep them legible.

| #   | File               | Type         | What to capture                                                                                               |
| --- | ------------------ | ------------ | ------------------------------------------------------------------------------------------------------------- |
| 1   | `hero.gif`         | GIF (8–10 s) | A short tour: open the manager, switch layouts, hover a card. Used at the very top of the README.             |
| 2   | `view-flat.png`    | PNG          | **Flat** layout: grid of model cards with previews + the search bar and type / sort / card‑size selectors.    |
| 3   | `view-folders.png` | PNG          | **Folder** layout: breadcrumb trail and folder cards, one level inside a model type.                          |
| 4   | `node-graph.gif`   | GIF (4–6 s)  | Dragging a model card from the manager onto the canvas, spawning a loader node with the model preselected.    |
| 5   | `download.png`     | PNG          | **Create Download Task** dialog with a URL entered and results listed (Civitai / Hugging Face / direct link). |
| 6   | `hf-upload.png`    | PNG          | **Upload to Hugging Face** dialog (step 3): repo id, private toggle, destination path, progress bar.          |
| 7   | `model-info.png`   | PNG          | **Model info** view: preview image, base‑info table, and the Description / Metadata tabs.                     |
| 8   | `settings.png`     | PNG          | ComfyUI **Settings → Model Manager Neo** showing the API‑key rows (Civitai / Hugging Face).                   |

> Only files 1–4 are referenced inline in the README's Screenshots section; the
> rest (5–8) are listed so you can extend the gallery — add them wherever you
> like, or reference them from the matching feature bullet.

Once you've added the images you can delete this manifest, or keep it as
documentation for future contributors.
