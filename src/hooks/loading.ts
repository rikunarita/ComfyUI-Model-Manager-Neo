import { type Ref, ref } from 'vue'
import { defineStore } from 'hooks/store'

class GlobalLoading {
  loading: Ref<boolean> = ref(false)

  loadingStack = 0

  bind(loading: Ref<boolean>) {
    this.loading = loading
  }

  show() {
    this.loadingStack++
    this.loading.value = true
  }

  hide() {
    // Clamped: an unbalanced hide() used to drive the counter negative, after
    // which the same number of show() calls no longer reached 1 and the overlay
    // silently stopped appearing for the rest of the session.
    this.loadingStack = Math.max(0, this.loadingStack - 1)
    if (this.loadingStack === 0) this.loading.value = false
  }
}

const globalLoading = new GlobalLoading()

export const useGlobalLoading = defineStore('loading', () => {
  const loading = ref(false)

  globalLoading.bind(loading)

  return { loading }
})

declare module 'hooks/store' {
  interface StoreProvider {
    loading: ReturnType<typeof useGlobalLoading>
  }
}

export const useLoading = () => {
  // Standards catch-up C-5: the UI must not depend on @types/node globals.
  const targetTimer = ref<Record<string, ReturnType<typeof setTimeout> | undefined>>({})

  const show = (target: string = '_default') => {
    /*
     * BUG FIX: a second show() for a target whose 200 ms grace timer was still
     * pending overwrote the handle, orphaning the first timer. The orphan still
     * fired (incrementing the global stack) while its own callback cleared the
     * *new* handle, so the matching hide() found nothing to clear and called
     * globalLoading.hide() only once — the stack stayed at 1 and the overlay
     * never went away. Reachable whenever two `_default` operations overlap
     * (a model-detail `useRequest` still in flight while the user saves).
     * A pending show for the same target is now a no-op: the caller's hide()
     * still cancels it.
     */
    if (targetTimer.value[target]) return
    targetTimer.value[target] = setTimeout(() => {
      targetTimer.value[target] = undefined
      globalLoading.show()
    }, 200)
  }

  const hide = (target: string = '_default') => {
    if (targetTimer.value[target]) {
      clearTimeout(targetTimer.value[target])
      targetTimer.value[target] = undefined
    } else {
      globalLoading.hide()
    }
  }

  return { show, hide }
}
