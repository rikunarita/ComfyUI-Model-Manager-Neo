export {}

declare module '*.vue' {
  import { type DefineComponent } from 'vue'

  const component: DefineComponent<Record<string, unknown>, Record<string, unknown>, any>
  export default component
}

declare module 'hooks/store' {
  // Empty base interface: each store module augments it via
  // `declare module 'hooks/store' { interface StoreProvider { … } }`.
  // eslint-disable-next-line @typescript-eslint/no-empty-object-type
  interface StoreProvider {}
}
