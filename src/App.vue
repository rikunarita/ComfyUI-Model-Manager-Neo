<template>
  <ConfigProvider teleport-to="body">
    <TooltipProvider :delay-duration="400">
      <Sonner position="top-right" :toast-options="{ classes: { toast: 'mm-glass-light' } }" />
      <GlobalConfirm />
      <GlobalDialogStack />
    </TooltipProvider>
  </ConfigProvider>
</template>

<script setup lang="ts">
import { Download, Eye, EyeOff, FolderOpen, FolderSearch, LayoutGrid, RefreshCw, Upload } from '@lucide/vue'
import DialogDownload from 'components/DialogDownload.vue'
import DialogExplorer from 'components/DialogExplorer.vue'
import DialogHfUpload from 'components/DialogHfUpload.vue'
import DialogManager from 'components/DialogManager.vue'
import DialogScanning from 'components/DialogScanning.vue'
import GlobalDialogStack from 'components/GlobalDialogStack.vue'
import GlobalLoading from 'components/GlobalLoading.vue'
import { Sonner } from 'components/ui/sonner'
import { TooltipProvider } from 'components/ui/tooltip'
import { useStoreProvider } from 'hooks/store'
import { useToast } from 'hooks/toast'
import GlobalConfirm from 'components/GlobalConfirm.vue'
import { ConfigProvider } from 'reka-ui'
import { app } from 'scripts/comfyAPI'
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { resolveIcon } from 'utils/iconMap'

const { t } = useI18n()

const { dialog, models, config, download } = useStoreProvider()

const { toast } = useToast()

const firstOpenManager = ref(true)

onMounted(() => {
  const refreshModelsAndConfig = async () => {
    await Promise.all([models.refresh(true)])
    toast.add({
      severity: 'success',
      summary: 'Refreshed Models',
      life: 2000,
    })
  }

  const openModelScanning = () => {
    dialog.open({
      key: 'model-information-scanning',
      title: t('batchScanModelInformation'),
      content: DialogScanning,
      modal: true,
      defaultSize: {
        width: 680,
        height: 490,
      },
    })
  }

  const openDownloadDialog = () => {
    dialog.open({
      key: 'model-manager-download-list',
      title: t('downloadList'),
      content: DialogDownload,
      headerButtons: [
        {
          key: 'refresh',
          icon: 'pi pi-refresh',
          command: () => download.refresh(),
        },
      ],
    })
  }

  const openHfUploadDialog = () => {
    dialog.open({
      key: 'model-manager-hf-upload',
      title: t('uploadToHuggingFace'),
      content: DialogHfUpload,
      headerButtons: [
        {
          key: 'refresh',
          icon: 'pi pi-refresh',
          command: refreshModelsAndConfig,
        },
      ],
    })
  }

  const toggleLayout = () => {
    const newValue = !config.flat.value
    config.flat.value = newValue
    app.ui?.settings.setSettingValue('ModelManager.UI.Flat', newValue)
    dialog.closeAll()
    openManagerDialog()
  }

  const openManagerDialog = () => {
    const { cardWidth, gutter, aspect, flat } = config
    const layoutIcon = flat.value ? 'pi pi-th-large' : 'pi pi-folder-open'
    const includeHidden =
      app.ui?.settings.getSettingValue(
        'ModelManager.Scan.IncludeHiddenFiles',
      ) ?? false
    const hiddenIcon = includeHidden ? 'pi pi-eye' : 'pi pi-eye-slash'
    const hiddenTooltip = includeHidden
      ? t('hideHiddenFiles')
      : t('showHiddenFiles')

    if (firstOpenManager.value) {
      models.refresh(true)
      firstOpenManager.value = false
    }

    dialog.open({
      key: 'model-manager',
      title: t('modelManager'),
      content: flat.value ? DialogManager : DialogExplorer,
      keepAlive: true,
      headerButtons: [
        {
          key: 'scanning',
          icon: 'mdi mdi-folder-search-outline text-lg',
          command: openModelScanning,
        },
        {
          key: 'toggle-layout',
          icon: layoutIcon,
          command: toggleLayout,
          tooltip: flat.value ? t('switchToFolderView') : t('switchToFlatView'),
        },
        {
          key: 'toggle-hidden',
          icon: hiddenIcon,
          command: async () => {
            const newValue = !includeHidden
            app.ui?.settings.setSettingValue(
              'ModelManager.Scan.IncludeHiddenFiles',
              newValue,
            )
            await refreshModelsAndConfig()
            dialog.closeAll()
            openManagerDialog()
          },
          tooltip: hiddenTooltip,
        },
        {
          key: 'refresh',
          icon: 'pi pi-refresh',
          command: refreshModelsAndConfig,
        },
        {
          key: 'download',
          icon: 'pi pi-download',
          command: openDownloadDialog,
        },
        {
          key: 'upload',
          icon: 'pi pi-upload',
          command: openHfUploadDialog,
        },
      ],
      minWidth: cardWidth * 2 + gutter + 42,
      minHeight: (cardWidth / aspect) * 0.5 + 162,
    })
  }

  window.addEventListener('open-model-manager', openManagerDialog)
})
</script>
