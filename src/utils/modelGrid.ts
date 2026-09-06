/**
 * Typed reimplementation of the model-grid helpers formerly in legacy.ts.
 * Only the functions actually consumed by hooks/model.ts are kept.
 * All global references ($el, SearchPath, ComfyButton, etc.) are replaced
 * with proper imports. No dependency on the archived @comfyorg/litegraph.
 */
import { app } from 'scripts/comfyAPI'

export const MODEL_NODE_TYPE: Record<string, string | undefined> = {
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

export function modelWidgetIndex(nodeType: string | undefined): number {
  return nodeType === undefined ? -1 : 0
}

export function splitExtension(name: string): [string, string] {
  const idx = name.lastIndexOf('.')
  if (idx <= 0) return [name, '']
  return [name.slice(0, idx), name.slice(idx)]
}

export function insertEmbeddingIntoText(
  text: string,
  file: string,
  removeExtension: boolean,
): string {
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

function getWidgetComboIndices(
  node: LGraphNode | null,
  value: string,
): number[] {
  const indices: number[] = []
  node?.widgets?.forEach((widget: any, index: number) => {
    if (widget.type === 'combo' && widget.options?.values?.includes(value)) {
      indices.push(index)
    }
  })
  return indices
}

export function dragAddModel(
  event: DragEvent,
  modelType: string,
  path: string,
  removeEmbeddingExtension: boolean,
  strictlyOnWidget: boolean,
): void {
  const target = document.elementFromPoint(event.clientX, event.clientY)

  if (
    modelType !== 'embeddings' &&
    (target as HTMLElement)?.id === 'graph-canvas'
  ) {
    const pos = (app.canvas as any).convertEventToCanvasOffset(
      event,
    ) as [number, number]
    const node = app.graph.getNodeOnPos(
      pos[0],
      pos[1],
      (app.canvas as any).visible_nodes,
    )

    let widgetIndex = -1
    const widgetIndices = getWidgetComboIndices(node, path)
    if (widgetIndices.length === 1) {
      widgetIndex = widgetIndices[0]
      if (strictlyOnWidget) {
        const draggedWidget = (app.canvas as any).processNodeWidgets(
          node,
          pos,
          event,
        )
        if (draggedWidget != node!.widgets[widgetIndex]) {
          widgetIndex = -1
        }
      }
    } else if (widgetIndices.length > 1) {
      const draggedWidget = (app.canvas as any).processNodeWidgets(
        node,
        pos,
        event,
      )
      widgetIndex = widgetIndices.findIndex(
        (index) => draggedWidget == node!.widgets[index],
      )
    }

    if (widgetIndex !== -1 && node) {
      node.widgets[widgetIndex].value = path
      app.canvas.selectNode(node)
    } else {
      const expectedNodeType = MODEL_NODE_TYPE[modelType]
      const newNode = (window.LiteGraph as any).createNode(
        expectedNodeType,
        null,
        {},
      )
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
  } else if (
    modelType === 'embeddings' &&
    (target as HTMLTextAreaElement)?.type === 'textarea'
  ) {
    const pos = (app.canvas as any).convertEventToCanvasOffset(
      event,
    ) as [number, number]
    const nodeAtPos = app.graph.getNodeOnPos(
      pos[0],
      pos[1],
      (app.canvas as any).visible_nodes,
    )
    if (nodeAtPos) {
      app.canvas.selectNode(nodeAtPos)
      const [, embeddingFile] = splitExtension(path)
      ;(target as HTMLTextAreaElement).value = insertEmbeddingIntoText(
        (target as HTMLTextAreaElement).value,
        embeddingFile,
        removeEmbeddingExtension,
      )
      event.stopPropagation()
    }
  }

  flashButton(event.target, true)
}
