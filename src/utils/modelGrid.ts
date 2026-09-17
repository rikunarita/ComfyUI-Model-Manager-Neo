/**
 * Typed reimplementation of the model-grid helpers formerly in legacy.ts.
 * Only the functions actually consumed by hooks/model.ts are kept.
 * All global references ($el, SearchPath, ComfyButton, etc.) are replaced
 * with proper imports. No dependency on the archived @comfyorg/litegraph.
 */
import { app } from 'scripts/comfyAPI'

const MODEL_NODE_TYPE: Record<string, string | undefined> = {
  checkpoints: 'CheckpointLoaderSimple',
  clip: 'CLIPLoader',
  clip_vision: 'CLIPVisionLoader',
  controlnet: 'ControlNetLoader',
  diffusers: 'DiffusersLoader',
  embeddings: 'Embedding',
  gligen: 'GLIGENLoader',
  hypernetworks: 'HypernetworkLoader',
  photomaker: 'PhotoMakerLoader',
  loras: 'LoraLoader',
  style_models: 'StyleModelLoader',
  unet: 'UNETLoader',
  upscale_models: 'UpscaleModelLoader',
  vae: 'VAELoader',
  vae_approx: undefined,
}

function modelWidgetIndex(nodeType: string | undefined): number {
  return nodeType === undefined ? -1 : 0
}

function splitExtension(name: string): [string, string] {
  const idx = name.lastIndexOf('.')
  if (idx <= 0) return [name, '']
  return [name.slice(0, idx), name.slice(idx)]
}

function insertEmbeddingIntoText(text: string, file: string, removeExtension: boolean): string {
  let name = file
  if (removeExtension) {
    name = splitExtension(name)[0]
  }
  const sep = text.length === 0 || /\s$/.test(text) ? '' : ' '
  return text + sep + '(embedding:' + name + ':1.0)'
}

function flashButton(target: EventTarget | null, success: boolean): void {
  const el = target as HTMLElement | null
  if (!el) return
  const original = el.style.outline
  el.style.outline = success ? '2px solid #4ade80' : '2px solid #f87171'
  setTimeout(() => {
    el.style.outline = original
  }, 600)
}

function getWidgetComboIndices(node: LGraphNode | null, value: string): number[] {
  const indices: number[] = []
  node?.widgets?.forEach((widget: any, index: number) => {
    if (widget.type === 'combo' && widget.options?.values?.includes(value)) {
      indices.push(index)
    }
  })
  return indices
}

/**
 * Which combo widget a dropped model should land in: the single matching
 * combo, or - the drag started on a widget and `strictlyOnWidget` asks for
 * it - the combo actually under the pointer when several match.
 */
function resolveDropWidgetIndex(
  node: LGraphNode | null,
  path: string,
  strictlyOnWidget: boolean,
  pos: [number, number],
  event: DragEvent,
): number {
  const widgetIndices = getWidgetComboIndices(node, path)
  if (widgetIndices.length === 0) return -1
  if (widgetIndices.length === 1) {
    if (!strictlyOnWidget) return widgetIndices[0]
    const draggedWidget = (app.canvas as any).processNodeWidgets(node, pos, event)
    return draggedWidget === node!.widgets[widgetIndices[0]] ? widgetIndices[0] : -1
  }
  const draggedWidget = (app.canvas as any).processNodeWidgets(node, pos, event)
  return widgetIndices.findIndex(index => draggedWidget === node!.widgets[index])
}

export function dragAddModel(
  event: DragEvent,
  modelType: string,
  path: string,
  removeEmbeddingExtension: boolean,
  strictlyOnWidget: boolean,
): void {
  const target = document.elementFromPoint(event.clientX, event.clientY)

  if (modelType !== 'embeddings' && (target as HTMLElement)?.id === 'graph-canvas') {
    const pos = (app.canvas as any).convertEventToCanvasOffset(event) as [number, number]
    const node = app.graph.getNodeOnPos(pos[0], pos[1], (app.canvas as any).visible_nodes)

    const widgetIndex = resolveDropWidgetIndex(node, path, strictlyOnWidget, pos, event)

    if (widgetIndex !== -1 && node) {
      node.widgets[widgetIndex].value = path
      app.canvas.selectNode(node)
    } else {
      const expectedNodeType = MODEL_NODE_TYPE[modelType]
      const newNode = (window.LiteGraph as any).createNode(expectedNodeType, null, {})
      let newWidgetIndex = modelWidgetIndex(expectedNodeType)
      if (newWidgetIndex === -1) {
        newWidgetIndex = getWidgetComboIndices(newNode, path)[0] ?? -1
      }
      if (newNode != null && newWidgetIndex !== -1) {
        newNode.pos[0] = pos[0]
        newNode.pos[1] = pos[1]
        newNode.widgets[newWidgetIndex].value = path
        ;(app.graph as any).add(newNode, { doProcessChange: true })
        app.canvas.selectNode(newNode)
      }
    }
    event.stopPropagation()
  } else if (modelType === 'embeddings' && (target as HTMLTextAreaElement)?.type === 'textarea') {
    const pos = (app.canvas as any).convertEventToCanvasOffset(event) as [number, number]
    const nodeAtPos = app.graph.getNodeOnPos(pos[0], pos[1], (app.canvas as any).visible_nodes)
    if (nodeAtPos) {
      app.canvas.selectNode(nodeAtPos)
      // BUG FIX: previously the *extension* half of splitExtension() was
      // inserted, producing "(embedding:.safetensors:1.0)". The full model
      // path must be passed; insertEmbeddingIntoText() strips the extension
      // itself when removeEmbeddingExtension is set (matches upstream
      // ComfyUI behaviour).
      ;(target as HTMLTextAreaElement).value = insertEmbeddingIntoText(
        (target as HTMLTextAreaElement).value,
        path,
        removeEmbeddingExtension,
      )
      event.stopPropagation()
    }
  }

  flashButton(event.target, true)
}
