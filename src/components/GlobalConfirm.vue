<template>
  <AlertDialog :open="confirmState.visible" @update:open="handleOpenChange">
    <AlertDialogContent class="max-w-md">
      <AlertDialogHeader>
        <AlertDialogTitle>{{ confirmState.options?.header || 'Confirm' }}</AlertDialogTitle>
        <AlertDialogDescription>
          {{ confirmState.options?.message }}
        </AlertDialogDescription>
      </AlertDialogHeader>
      <AlertDialogFooter>
        <AlertDialogCancel @click="handleReject">
          {{ confirmState.options?.rejectProps?.label || 'Cancel' }}
        </AlertDialogCancel>
        <AlertDialogAction @click="handleAccept">
          {{ confirmState.options?.acceptProps?.label || 'Confirm' }}
        </AlertDialogAction>
      </AlertDialogFooter>
    </AlertDialogContent>
  </AlertDialog>
</template>

<script setup lang="ts">
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
import { confirmState } from 'hooks/toast'

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
