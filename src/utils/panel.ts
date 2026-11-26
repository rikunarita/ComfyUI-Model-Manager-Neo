/**
 * Shared geometry for the extension's wide content panels.
 *
 * The manager window and every full-workspace dialog (model detail, download
 * list, task creation, HF upload, hygiene, identify-by-hash, ...) are sized
 * from a single rule so they line up instead of each falling back to a
 * different default. Capped so ultrawide screens keep a sensible content
 * measure instead of one endless row.
 *
 * Small utility dialogs (API key entry, folder creation, ...) deliberately
 * keep their own purpose-built sizes — the helper is only for panels whose
 * content is a full workspace.
 */

/** Fraction of the viewport width a wide panel targets. */
const WIDE_PANEL_RATIO = 0.8

/** Absolute cap (px) so 4K/ultrawide displays keep a readable measure. */
const WIDE_PANEL_MAX_WIDTH = 1600

/** The wide panel width for the *current* viewport. */
export const widePanelWidth = (): number =>
  Math.min(Math.floor(window.innerWidth * WIDE_PANEL_RATIO), WIDE_PANEL_MAX_WIDTH)
