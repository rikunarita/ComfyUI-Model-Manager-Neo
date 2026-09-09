<template>
  <AlertDialog :open="confirmState.visible" @update:open="handleOpenChange">
    <AlertDialogContent class="max-w-md">
      <AlertDialogHeader>
        <!--
          BUG FIX: every caller passes `icon: 'pi pi-info-circle'` and
          `acceptProps: { severity: 'danger' }` / `rejectProps: { severity:
          'secondary', outlined: true }`, but this component ignored all three.
          The icon was never rendered and, worse, a destructive confirmation
          ("Delete this model?", "Delete this download task?", "Delete API
          key?") looked exactly like the Cancel button next to it. Both are
          honoured now: the icon resolves through the Lucide map (PrimeIcons is
          gone) and `severity: 'danger'` maps to the `destructive` variant.
        -->
        <AlertDialogTitle class="flex items-center gap-2">
          <component :is="confirmIcon" v-if="confirmIcon" class="size-5 shrink-0" />
          {{ confirmState.options?.header || 'Confirm' }}
        </AlertDialogTitle>
        <AlertDialogDescription>
          {{ confirmState.options?.message }}
        </AlertDialogDescription>
      </AlertDialogHeader>
      <AlertDialogFooter>
        <AlertDialogCancel :class="rejectClass" @click="handleReject">
          {{ confirmState.options?.rejectProps?.label || 'Cancel' }}
        </AlertDialogCancel>
        <AlertDialogAction :class="acceptClass" @click="handleAccept">
          {{ confirmState.options?.acceptProps?.label || 'Confirm' }}
        </AlertDialogAction>
      </AlertDialogFooter>
    </AlertDialogContent>
  </AlertDialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from 'components/ui/alert-dialog'
import { buttonVariants } from 'components/ui/button'
import { confirmState } from 'hooks/toast'
import { resolveIcon } from 'utils/iconMap'

const confirmIcon = computed(() => {
  const icon = confirmState.options?.icon
  return icon ? resolveIcon(icon) : undefined
})

/** PrimeVue severity -> Neo button variant. */
const variantFor = (severity?: string, outlined?: boolean) => {
  switch (severity) {
    case 'danger':
      return 'destructive' as const
    case 'secondary':
      return outlined ? ('outline' as const) : ('secondary' as const)
    case 'info':
    case 'success':
    case 'warning':
    case 'help':
      return 'default' as const
    default:
      return undefined
  }
}

const acceptClass = computed(() => {
  const variant = variantFor(confirmState.options?.acceptProps?.severity)
  return variant ? buttonVariants({ variant }) : undefined
})

const rejectClass = computed(() => {
  const reject = confirmState.options?.rejectProps
  const variant = variantFor(reject?.severity, reject?.outlined)
  // AlertDialogCancel already defaults to `outline`; only override when the
  // caller asked for something else.
  return variant && variant !== 'outline' ? buttonVariants({ variant }) : undefined
})

/**
 * BUG FIX: reka-ui's AlertDialogAction / AlertDialogCancel wrap DialogClose,
 * whose INTERNAL onClick (`onOpenChange(false)`) runs BEFORE our own @click
 * handler. The resulting `update:open(false)` was treated as a rejection, so
 * `options` was already nulled by the time `handleAccept` ran — the accept
 * callback (delete task / delete model / remove API key ...) silently never
 * fired.
 *
 * The settle logic below is order-independent:
 *  - an explicit accept/reject click always settles the dialog synchronously;
 *  - a bare close (Escape, programmatic) defers its fallback rejection by one
 *    microtask and is invalidated (token) if a click settles the dialog first.
 */
let closeToken = 0

const settle = (kind: 'accept' | 'reject') => {
  closeToken++
  const options = confirmState.options
  confirmState.visible = false
  confirmState.options = null
  if (kind === 'accept') {
    options?.accept()
  } else {
    options?.reject()
  }
}

const handleAccept = () => {
  settle('accept')
}

const handleReject = () => {
  settle('reject')
}

const handleOpenChange = (open: boolean) => {
  if (!open && confirmState.options) {
    const token = ++closeToken
    const optionsAtClose = confirmState.options
    Promise.resolve().then(() => {
      // Only run the fallback rejection if nothing else settled the dialog in
      // the meantime (i.e. the close was not caused by a button click) and no
      // NEW confirm was queued in the same tick.
      if (token === closeToken && confirmState.options === optionsAtClose) {
        settle('reject')
      }
    })
  }
}
</script>
