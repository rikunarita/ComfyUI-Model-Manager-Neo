<template>
  <ConfigProvider teleport-to="body">
    <TooltipProvider :delay-duration="400">
      <Sonner />
      <GlobalConfirm />
      <GlobalLoading />
      <GlobalDialogStack />
    </TooltipProvider>
  </ConfigProvider>
</template>

<script setup lang="ts">
import { ConfigProvider } from 'reka-ui'
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import DialogDownload from 'components/DialogDownload.vue'
import DialogExplorer from 'components/DialogExplorer.vue'
import DialogHfUpload from 'components/DialogHfUpload.vue'
import DialogManager from 'components/DialogManager.vue'
import GlobalConfirm from 'components/GlobalConfirm.vue'
import GlobalDialogStack from 'components/GlobalDialogStack.vue'
import GlobalLoading from 'components/GlobalLoading.vue'
import { Sonner } from 'components/ui/sonner'
import { TooltipProvider } from 'components/ui/tooltip'
import { useStoreProvider } from 'hooks/store'
import { useToast } from 'hooks/toast'
import { $el, app, ComfyButton } from 'scripts/comfyAPI'

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
          tooltip: t('refresh'),
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
          tooltip: t('refresh'),
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
      app.ui?.settings.getSettingValue('ModelManager.Scan.IncludeHiddenFiles') ?? false
    const hiddenIcon = includeHidden ? 'pi pi-eye' : 'pi pi-eye-slash'
    const hiddenTooltip = includeHidden ? t('hideHiddenFiles') : t('showHiddenFiles')

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
            app.ui?.settings.setSettingValue('ModelManager.Scan.IncludeHiddenFiles', newValue)
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
          tooltip: t('refresh'),
        },
        {
          key: 'download',
          icon: 'pi pi-download',
          command: openDownloadDialog,
          tooltip: t('downloadList'),
        },
        {
          key: 'upload',
          icon: 'pi pi-upload',
          command: openHfUploadDialog,
          tooltip: t('uploadToHuggingFace'),
        },
      ],
      minWidth: cardWidth * 2 + gutter + 42,
      minHeight: (cardWidth / aspect) * 0.5 + 162,
    })
  }

  window.addEventListener('open-model-manager', openManagerDialog)

  // レガシー UI 用コンテナへのボタン追加
  app.ui?.menuContainer?.appendChild(
    $el('button', {
      id: 'comfyui-model-manager-button',
      textContent: t('modelManager'),
      onclick: openManagerDialog,
    }),
  )

  // ComfyButton インスタンスの生成（新フロントエンド用）
  const managerButton = new ComfyButton({
    icon: 'folder-search',
    tooltip: t('openModelManager'),
    content: t('modelManager'),
    action: openManagerDialog,
  })

  try {
    if (app.menu?.settingsGroup?.element) {
      app.menu.settingsGroup.element.before(managerButton.element)
    } else {
      app.menu?.settingsGroup?.insert?.(managerButton.element)
    }
  } catch (e) {
    console.warn('Failed to add Model Manager button to topbar:', e)
  }
})
</script>
