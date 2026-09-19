<template>
  <ConfigProvider teleport-to="body">
    <TooltipProvider :delay-duration="400">
      <Sonner />
      <GlobalConfirm />
      <GlobalDialogStack />
    </TooltipProvider>
  </ConfigProvider>
</template>

<script setup lang="ts">
import { ConfigProvider } from 'reka-ui'
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import DialogDownload from 'components/DialogDownload.vue'
import DialogExplorer from 'components/DialogExplorer.vue'
import DialogHfUpload from 'components/DialogHfUpload.vue'
import DialogHygiene from 'components/DialogHygiene.vue'
import DialogManager from 'components/DialogManager.vue'
import GlobalConfirm from 'components/GlobalConfirm.vue'
import GlobalDialogStack from 'components/GlobalDialogStack.vue'
import { Sonner } from 'components/ui/sonner'
import { TooltipProvider } from 'components/ui/tooltip'
import { autoCompressUnused } from 'hooks/autoCompress'
import { loadCollections } from 'hooks/collections'
import { useModelDetail } from 'hooks/modelDetail'
import { loadRecent } from 'hooks/recent'
import { loadStars } from 'hooks/stars'
import { useStoreProvider } from 'hooks/store'
import { useToast } from 'hooks/toast'
import { takeZipnnSettle } from 'hooks/zipnn'
import { $el, app, ComfyButton } from 'scripts/comfyAPI'
import { bytesToSize } from 'utils/common'

const { t } = useI18n()

const { dialog, models, config, download } = useStoreProvider()
const { openModelDetail } = useModelDetail()

const { toast } = useToast()

const firstOpenManager = ref(true)

/**
 * Aggregate size of every model file in the library - the live read-out next
 * to the manager window's title (folder entries carry no size of their own;
 * type-root cards show the same per-type sum).
 */
const totalModelBytes = computed(() => {
  let sum = 0
  for (const list of Object.values(models.data.value)) {
    for (const entry of list) {
      if (!entry.isFolder) sum += entry.sizeBytes || 0
    }
  }
  return sum
})

/**
 * ZipNN completion handling, at APP lifetime.
 *
 * BUG FIX: the post-task refresh used to live in a `DialogModelDetail`
 * watcher, so it only ran while that model card happened to be open - and a
 * multi-gigabyte compression outlives most dialogs (close the card while it
 * runs and NOTHING refreshed when it finished; the grids kept showing the
 * pre-rename file and re-opening it 404'd). Both layouts derive from the
 * same models store, so one `refreshFolder()` updates the flat grid AND the
 * folder explorer. If the card of the renamed model is still open it is
 * swapped for a fresh one showing the new file
 * (`.safetensors` <-> `.znn.safetensors`).
 *
 * Driven by the `mm-zipnn-settled` window event (one per finished task, also
 * for queued folder batches) instead of a watcher on `zipnnState.active`,
 * which stays true across queued batches.
 */
const handleZipnnSettled = async () => {
  const settle = takeZipnnSettle()
  if (!settle?.ok) return
  // refreshModels reports its own failure via toast; it must not escape as
  // an unhandled rejection from this window-lifetime listener.
  await models.refreshFolder(settle.type).catch(() => {})
  if (!settle.targetKey) return
  const staleOpen = dialog.stack.value.some(item => item.key === settle.targetKey)
  if (!staleOpen) return
  const renamed = (models.data.value[settle.type] ?? []).find(
    m =>
      !m.isFolder &&
      m.pathIndex === settle.pathIndex &&
      m.subFolder === settle.subFolder &&
      `${m.basename}${m.extension}` === settle.newFullname,
  )
  dialog.close({ key: settle.targetKey })
  if (renamed) openModelDetail(renamed)
}

onMounted(() => {
  loadStars()
  loadRecent()
  loadCollections()
  window.addEventListener('mm-zipnn-settled', () => {
    void handleZipnnSettled()
  })
  const refreshModelsAndConfig = async () => {
    await Promise.all([models.refresh(true)])
    autoCompressUnused(models.data.value)
    toast.add({
      severity: 'success',
      summary: t('refreshedModels'),
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
      title: t('uploadToHub'),
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

  const openHygieneDialog = () => {
    dialog.open({
      key: 'hygiene',
      title: t('hygiene'),
      content: DialogHygiene,
      defaultSize: { width: 680, height: 520 },
    })
  }

  const toggleLayout = () => {
    const newValue = !config.flat.value
    config.flat.value = newValue
    app.ui?.settings.setSettingValue('ModelManager.UI.Flat', newValue)
    dialog.closeAll()
    openManagerDialog()
    toast.add({
      severity: 'info',
      summary: newValue ? t('layoutSwitchedFlat') : t('layoutSwitchedFolder'),
      life: 2500,
    })
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
    } else {
      // Stale-while-revalidate: show the cached grids immediately and
      // re-scan in the background (rate-limited), so files that appeared or
      // moved outside the UI show up on their own instead of only after the
      // manual refresh button.
      void models.revalidate()
    }

    dialog.open({
      key: 'model-manager',
      title: t('modelManager'),
      badge: () => `${t('totalSize')}: ${bytesToSize(totalModelBytes.value)}`,
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
          key: 'hygiene',
          icon: 'pi pi-scan',
          command: openHygieneDialog,
          tooltip: t('hygiene'),
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
            toast.add({
              severity: 'info',
              summary: newValue ? t('hiddenShown') : t('hiddenHidden'),
              life: 2500,
            })
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
          tooltip: t('uploadToHub'),
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
