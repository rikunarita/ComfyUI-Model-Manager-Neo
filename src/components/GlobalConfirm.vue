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

const handleAccept = () => {
  confirmState.options?.accept()
  confirmState.visible = false
  confirmState.options = null
}

const handleReject = () => {
  confirmState.options?.reject()
  confirmState.visible = false
  confirmState.options = null
}

const handleOpenChange = (open: boolean) => {
  if (!open) {
    handleReject()
  }
}
</script>
