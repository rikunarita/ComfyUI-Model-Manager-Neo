/**
 * Type definitions for ComfyUI-Model-Manager-Neo.
 *
 * ALL ComfyUI / LiteGraph types are sourced exclusively from
 * @comfyorg/comfyui-frontend-types (the single official type package).
 * The archived @comfyorg/litegraph package is NOT used.
 */
import type {
  ComfyApi as ComfyApiType,
  ComfyApp as ComfyAppType,
  ComfyExtension as ComfyExtensionBase,
  ComfyNodeDef as ComfyNodeDefType,
} from '@comfyorg/comfyui-frontend-types'

declare global {
  namespace ComfyAPI {
    namespace api {
      type ComfyApi = ComfyApiType
      const api: ComfyApi
    }

    namespace app {
      interface ComfyExtension extends ComfyExtensionBase {
        commands?: Array<{
          id: string
          label: string
          icon?: string
          function: (...args: any[]) => any
        }>
        menuCommands?: Array<{
          path: string[]
          commands: string[]
        }>
        keybindings?: Array<{
          combo: {
            key: string
            ctrl?: boolean
            shift?: boolean
            alt?: boolean
            meta?: boolean
          }
          commandId: string
        }>
        settings?: any[]
        [key: string]: any
      }

      type ComfyApp = ComfyAppType
      const app: ComfyApp
    }

    namespace ui {
      type Props = {
        parent?: HTMLElement
        $?: (el: HTMLElement) => void
        dataset?: DOMStringMap
        style?: Partial<CSSStyleDeclaration>
        for?: string
        textContent?: string
        [key: string]: any
      }
      type Children = Element[] | Element | string | string[]
      type ElementType<K extends string> = K extends keyof HTMLElementTagNameMap
        ? HTMLElementTagNameMap[K]
        : HTMLElement

      const $el: <TTag extends string>(
        tag: TTag,
        propsOrChildren?: Children | Props,
        children?: Children,
      ) => ElementType<TTag>

      class ComfyUI {
        app: app.ComfyApp
        settings: ComfySettingsDialog
        menuHamburger?: HTMLDivElement
        menuContainer?: HTMLDivElement
        dialog: dialog.ComfyDialog
      }

      type SettingInputType = 'boolean' | 'number' | 'slider' | 'combo' | 'text' | 'hidden'

      type SettingCustomRenderer = (
        name: string,
        setter: (v: any) => void,
        value: any,
        attrs: any,
      ) => HTMLElement

      interface SettingOption {
        text: string
        value?: string
      }

      interface SettingParams {
        id: string
        name: string
        type: SettingInputType | SettingCustomRenderer
        defaultValue: any
        onChange?: (newValue: any, oldValue?: any) => void
        attrs?: any
        tooltip?: string
        options?: Array<string | SettingOption> | ((value: any) => SettingOption[])
        category?: string[]
        experimental?: boolean
        deprecated?: boolean
      }

      class ComfySettingsDialog extends dialog.ComfyDialog {
        addSetting: (params: SettingParams) => { value: any }
        getSettingValue: <T>(id: string, defaultValue?: T) => T
        setSettingValue: <T>(id: string, value: T) => void
      }
    }

    namespace index {
      class ComfyAppMenu {
        app: app.ComfyApp
        logo: HTMLElement
        actionsGroup: button.ComfyButtonGroup
        settingsGroup: button.ComfyButtonGroup
        viewGroup: button.ComfyButtonGroup
        mobileMenuButton: button.ComfyButton
        element: HTMLElement
      }
    }

    namespace button {
      type ComfyButtonProps = {
        icon?: string
        overIcon?: string
        iconSize?: number
        content?: string | HTMLElement
        tooltip?: string
        enabled?: boolean
        action?: (e: Event, btn: ComfyButton) => void
        classList?: string
        visibilitySetting?: { id: string; showValue: boolean }
        app?: app.ComfyApp
      }

      class ComfyButton {
        element: HTMLElement
        constructor(props: ComfyButtonProps)
      }

      class ComfyButtonGroup {
        element: HTMLElement
        insert(button: ComfyButton, index?: number): void
        append(button: ComfyButton): void
        remove(indexOrButton: ComfyButton | number): void
        update(): void
        constructor(...buttons: (HTMLElement | ComfyButton)[])
      }
    }

    namespace dialog {
      class ComfyDialog {
        constructor(type?: string, buttons?: HTMLElement[] | null)
        element: HTMLElement
        close(): void
        show(html: string | HTMLElement | HTMLElement[]): void
      }
    }
  }

  // ---- LiteGraph types (hand-written minimal declarations) ----
  // The official frontend-types package does not reliably export LGraphNode /
  // LGraphCanvas / LGraph as named exports, so we declare the members this
  // extension relies on here. This keeps us free of the archived
  // @comfyorg/litegraph package while remaining compatible with Nodes 2.0.
  interface LGraphNode {
    widgets: any[]
    pos: [number, number]
  }

  interface LGraphCanvas {
    selected_nodes: Record<string, LGraphNode>
    canvas_mouse: [number, number]
    graph_mouse: [number, number]
    visible_nodes: LGraphNode[]
    selectNode: (node: LGraphNode) => void
    copyToClipboard: (nodes: LGraphNode[]) => void
    convertEventToCanvasOffset: (event: MouseEvent) => [number, number]
    processNodeWidgets: (node: LGraphNode, pos: [number, number], event: MouseEvent) => any
  }

  interface LGraph {
    add(node: LGraphNode | any, options?: any): void
    getNodeOnPos<T extends LGraphNode = LGraphNode>(
      x: number,
      y: number,
      node_list?: LGraphNode[],
      margin?: number,
    ): T | null
  }

  type ComfyNodeDef = ComfyNodeDefType

  interface Window {
    comfyAPI: typeof ComfyAPI
    LiteGraph: {
      createNode: (type: string, title: string | null, options: object) => LGraphNode
    }
  }
}
