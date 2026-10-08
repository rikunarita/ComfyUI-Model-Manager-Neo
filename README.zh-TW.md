> [!CAUTION]
> **本專案仍在積極開發中，目前不建議一般使用。**可能出現意料之外的
> bug；由於功能正在陸續新增，部分成果物可能是半成品。介面今後也可能
> 繼續變化。話雖如此，我們非常歡迎回饋問題與提交 issue。

<div align="center">

# <img src="https://api.iconify.design/lucide/boxes.svg?color=%236366f1" width="41" height="41" align="middle" alt=""> ComfyUI‑Model‑Manager‑Neo

### 瀏覽 · 下載 · 上傳 · 拖放 —— 優雅地管理你的模型。

在 **Vue 3 + Tailwind CSS v4 + reka‑ui** 之上重新建置的 ComfyUI 模型管理器，
採用現代玻璃擬態介面重新設計；包括 ZipNN 壓縮引擎在內的所有熱點路徑，
均由**預建置的純 Rust 核心**執行。

![Version](https://img.shields.io/badge/version-0.4.0-6366f1.svg)
![License](https://img.shields.io/badge/License-GPL--3.0--only-blue.svg)
![ComfyUI](https://img.shields.io/badge/ComfyUI-Custom%20Node-8A8B98.svg)
![CI](https://github.com/rikunarita/ComfyUI-Model-Manager-Neo/actions/workflows/ci.yml/badge.svg?branch=main)
![Security](https://github.com/rikunarita/ComfyUI-Model-Manager-Neo/actions/workflows/security.yml/badge.svg?branch=main)
![Native core](https://github.com/rikunarita/ComfyUI-Model-Manager-Neo/actions/workflows/native.yml/badge.svg?branch=main)
![ZipNN](https://img.shields.io/badge/ZipNN-Rust_reimplementation-0ea5e9.svg)
![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)

![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB.svg?logo=python&logoColor=white)
![Rust](https://img.shields.io/badge/Rust-1.85%2B_%C2%B7_edition_2024-DEA584.svg?logo=rust&logoColor=black)
![PyO3](https://img.shields.io/badge/PyO3-0.29_%C2%B7_abi3--py312_%2B_abi3t--py315-229988.svg)
![Free-threaded](https://img.shields.io/badge/CPython-3.15%2B_free--threaded_%28abi3t%29-229988.svg?logo=python&logoColor=white)
![Vue](https://img.shields.io/badge/Vue-3.5-4FC08D.svg?logo=vuedotjs&logoColor=white)
![reka-ui](https://img.shields.io/badge/reka--ui-2-16A353.svg?logo=rekaui&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-6-3178C6.svg?logo=typescript&logoColor=white)
![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-v4-38BDF8.svg?logo=tailwindcss&logoColor=white)
![Vite](https://img.shields.io/badge/Vite-8_%C2%B7_Rolldown-646CFF.svg?logo=vite&logoColor=white)
![Node](https://img.shields.io/badge/Node-26-339933.svg?logo=nodedotjs&logoColor=white)
![pnpm](https://img.shields.io/badge/pnpm-12-F69220.svg?logo=pnpm&logoColor=white)
![uv](https://img.shields.io/badge/uv-dev_%26_CI-DE5FE9.svg?logo=uv&logoColor=white)

![ESLint](https://img.shields.io/badge/ESLint-10-4B32C3.svg?logo=eslint&logoColor=white)
![Prettier](https://img.shields.io/badge/Prettier-3-F7B93E.svg?logo=prettier&logoColor=black)
![Stylelint](https://img.shields.io/badge/Stylelint-17-263238.svg?logo=stylelint&logoColor=white)
![Ruff](https://img.shields.io/badge/Ruff-0.16.9-D7FF64.svg?logo=ruff&logoColor=black)
![mypy](https://img.shields.io/badge/mypy-static_types-2A6DB2.svg)
![Fallow](https://img.shields.io/badge/Fallow-dead_code_%C2%B7_dupes-2E7D32.svg)

![CodeQL](https://img.shields.io/badge/CodeQL-SAST-24292E.svg?logo=github&logoColor=white)
![OSV-Scanner](https://img.shields.io/badge/OSV--Scanner-SCA-4285F4.svg)
![Gitleaks](https://img.shields.io/badge/Gitleaks-secret_scanning-C0392B.svg)
![zizmor](https://img.shields.io/badge/%F0%9F%8C%88_zizmor-Actions_hardening-8E44AD.svg)
![cargo-fuzz](https://img.shields.io/badge/cargo--fuzz-Fuzzing-DEA584.svg?logo=rust&logoColor=black)

![Linux x86_64](https://img.shields.io/badge/Linux-x86__64-FCC624.svg?logo=linux&logoColor=black)
![Linux aarch64](https://img.shields.io/badge/Linux-aarch64-FCC624.svg?logo=linux&logoColor=black)
![macOS universal2](https://img.shields.io/badge/macOS-Intel_%2B_Apple_Silicon-000000.svg?logo=apple)
![Windows x64](https://img.shields.io/badge/Windows-x64-0078D6.svg?logo=windows&logoColor=white)

[English](README.md) · [日本語](README.ja.md) · [简体中文](README.zh-CN.md) · **繁體中文**

![概覽動畫](demo-assets/hero.webm)

</div>

---

**目錄**

- [Why Neo?](#why-neo) · [截圖](#screenshots) · [安裝](#installation) · [功能](#features)
- [模型搜尋與多平台發現](#search) · [ZipNN 無失真壓縮](#zipnn) · [與原版相比改變了什麼](#what-changed) · [被移除的功能](#removed-features)
- [文件](#documentation) · [開發](#development) · [致謝與歸屬](#credits) · [安全](#security) · [授權](#license)

---

<a id="why-neo"></a>

## <img src="https://api.iconify.design/lucide/sparkles.svg?color=%23f59e0b" width="34" height="34" align="middle" alt=""> Why Neo?

**ComfyUI‑Model‑Manager‑Neo** 繼承了優秀的原版管理器，並從零開始重建了
整個使用體驗：

**1. Neo 新增**

- <img src="https://api.iconify.design/lucide/cpu.svg?color=%23f59e0b" width="19" height="19" align="middle" alt=""> **Rust 原生核心** —— 模型庫掃描、雜湊、safetensors 頭部解析、張量樹、
  資料夾監視、預覽 WebP 編解碼以及整個 ZipNN 引擎，都執行在儲存庫內附帶的
  **預建置 Rust 擴充套件**中：四個平台 × 兩種 Stable ABI 風味（GIL 建置用 abi3 =
  CPython 3.12 及以上，自由執行緒建置用 abi3t = CPython 3.15 及以上、PEP 803），
  各一個二進位。核心本身只需一次普通的 `import` 即可載入 ——
  **不需要編譯器、不需要 pip 包、不需要下載**（擴充套件的四個 Python hub 相依
  仍會在首次啟動時自動安裝）。與純 Python 原版的實測對比：5,000 個模型的
  庫掃描冷啟動快約 **7.5 倍**（熱態低於 100 ms）、五種雜湊記法**一遍**算完、
  65,000 張量的 MoE 張量樹建置快約 **100 倍**、ZipNN 壓縮無論模型多大
  **峰值記憶體都低於 1 GB**（證據見 [`docs/BENCH.md`](docs/BENCH.md)）。
- <img src="https://api.iconify.design/lucide/shield-check.svg?color=%2322c55e" width="19" height="19" align="middle" alt=""> **經過驗證的記憶體安全壓縮** —— Rust 引擎透過 lint 禁止 `unsafe` 程式碼：
  格式核心完全不含 `unsafe`，唯一需要它的邊界（只讀記憶體對映）經過了安全
  評審並有文件記錄。引擎還由七個持續 fuzz 目標加固，每次還原都會與壓縮時
  記錄的 SHA‑256 校驗。與官方 `zipnn` 0.5.4 包的格式相容性是一項 CI 關卡，
  每次 push 都會雙向交叉驗證。
- <img src="https://api.iconify.design/lucide/package-plus.svg?color=%23f59e0b" width="19" height="19" align="middle" alt=""> **ZipNN 無失真壓縮** —— 就地壓縮與解壓縮 safetensors 模型（`.znn.safetensors`）、
  將整個資料夾批次打包為密封的 `<name>_DeltaZNN` 包、把微調模型相對其
  基礎模型縮小為極小的**差分檔案**。
- <img src="https://api.iconify.design/lucide/upload-cloud.svg?color=%23f59e0b" width="19" height="19" align="middle" alt=""> **上傳到 Hugging Face / ModelScope** —— 把任意本地模型直接釋出到 Hugging Face
  或 ModelScope 儲存庫（需要時自動建立儲存庫，可選私有、附帶相關資產並顯示
  實時進度）。ModelScope 支援——下載、上傳、搜尋與認證——為 Neo 全新整合。
- <img src="https://api.iconify.design/lucide/radar.svg?color=%23f59e0b" width="19" height="19" align="middle" alt=""> **多 hub 搜尋與雜湊識別** —— 在同一個輸入框中並行搜尋 Hugging Face、
  ModelScope 與 Civitai，並能用雜湊把任意本地檔案反查到 Civitai 目錄。
- <img src="https://api.iconify.design/lucide/list-checks.svg?color=%23f59e0b" width="19" height="19" align="middle" alt=""> **多選** —— 勾選模型與資料夾卡片，一次性加入工作流或刪除。
- <img src="https://api.iconify.design/lucide/star.svg?color=%23eab308" width="19" height="19" align="middle" alt=""> **星標** —— 每張卡片都有星標開關；加星的條目永遠排在最前。
- <img src="https://api.iconify.design/lucide/folder-plus.svg?color=%2322c55e" width="19" height="19" align="middle" alt=""> **建立資料夾** —— 資料夾檢視中的「新增資料夾」按鈕。
- <img src="https://api.iconify.design/lucide/link.svg?color=%23f59e0b" width="19" height="19" align="middle" alt=""> **直鏈下載** —— 貼上原始 `.safetensors` / `.ckpt` / `.gguf` URL，選擇目標
  資料夾，還可選自定義子資料夾。
- <img src="https://api.iconify.design/lucide/zap.svg?color=%23f59e0b" width="19" height="19" align="middle" alt=""> **`hf_xet` 加速** —— Hugging Face 傳輸在可用時使用分塊、去重的 Xet 協議。
- <img src="https://api.iconify.design/lucide/languages.svg?color=%23f59e0b" width="19" height="19" align="middle" alt=""> **日語與繁體中文語言包** —— 在 English 與簡體中文之外，新增完整的日語
  與繁體中文（zh-TW）語言包。介面語言跟隨 ComfyUI 自身的設定；地區子標籤
  （`ja-JP` 等）摺疊到其基礎語言，Hant 文字系統標籤（`zh-Hant`、
  `zh-Hant-TW` 等）選擇繁體中文包。

**2. 重新整理與增強**

- <img src="https://api.iconify.design/lucide/layers.svg?color=%23f59e0b" width="19" height="19" align="middle" alt=""> **玻璃擬態 UI** —— 半透明、帶模糊與層次感的介面，自動跟隨 ComfyUI 自身的
  淺色/深色配色。
- <img src="https://api.iconify.design/lucide/puzzle.svg?color=%23f59e0b" width="19" height="19" align="middle" alt=""> **Reka-UI 全面重新整理** —— PrimeVue 相依已替換為輕量、無樣式的 **[reka-ui]**
  原語、**Tailwind CSS v4** 與 **[Lucide]** 圖示：一套讀得懂、改得動的
  shadcn‑vue 風格元件。
- <img src="https://api.iconify.design/lucide/workflow.svg?color=%23f59e0b" width="19" height="19" align="middle" alt=""> **一流的節點圖整合** —— 把模型拖到畫布上即可生成或填充節點，把 embedding
  拖進文字區，載入預覽圖中內嵌的工作流。
- <img src="https://api.iconify.design/lucide/monitor-smartphone.svg?color=%23f59e0b" width="19" height="19" align="middle" alt=""> **響應式** —— 面向桌面、移動與多屏環境設計。
- <img src="https://api.iconify.design/lucide/wrench.svg?color=%23f59e0b" width="19" height="19" align="middle" alt=""> **現代工具鏈** —— Vite 8（Rolldown）、TypeScript 6、ESLint 10 flat config、
  Prettier、Stylelint、Ruff、clippy、husky + lint‑staged。確定性的、
  lint 零警告的建置。

> [!NOTE]
> Neo 是 [`hayden-cn/ComfyUI-Model-Manager`](https://github.com/hayden-cn/ComfyUI-Model-Manager)
> 的 **fork**，以相同的 **GPL‑3.0** 授權分發。原版架構的全部功勞屬於其
> 作者 —— 見[致謝](#credits)。

---

<a id="screenshots"></a>

## <img src="https://api.iconify.design/lucide/camera.svg?color=%238b5cf6" width="34" height="34" align="middle" alt=""> 截圖

### 1. 平鋪「模型」檢視 —— 搜尋、排序與網格大小調整

![平鋪模型網格](demo-assets/view-flat.avif)

**平鋪**佈局下的管理器視窗：玻璃質感模型卡片組成的網格（帶預覽、類型與
大小標籤）、搜尋欄，以及類型 / 排序 / 卡片尺寸選擇器。

### 2. 資料夾（資源管理器）檢視 —— 瀏覽目錄樹

![資料夾資源管理器檢視](demo-assets/view-folders.avif)

**資料夾**佈局的第一層，帶麵包屑路徑，以及指標停留時會輕輕浮起的淡綠松石
玻璃資料夾卡片。

### 3. 模型詳細、編輯與 Hugging Face 上傳

|                                                                   |                                                                         |
| ----------------------------------------------------------------- | ----------------------------------------------------------------------- |
| ![模型資訊](demo-assets/model-info.avif)                          | ![編輯模式](demo-assets/model-edit.avif)                                |
| _模型資訊：預覽、基礎資訊表、Description 與 Information 標籤頁。_ | _編輯模式：類型下拉框、資料夾選擇按鈕、接受 `folder/name` 字首的檔名。_ |

|                                                                    |                                                                               |
| ------------------------------------------------------------------ | ----------------------------------------------------------------------------- |
| ![Hugging Face 上傳](demo-assets/hf-upload.avif)                   | ![日語介面](demo-assets/ja-model-info.avif)                                   |
| _上傳到 Hugging Face 的第 3 步：儲存庫 ID、建立時私有、目標路徑。_ | _同一視窗的**日語**介面 —— 內建完整的 English / 中文（簡繁）/ 日本語語言包。_ |

### 4. 模型名搜尋與 safetensors 張量樹

|                                                                                                |                                                                                          |
| ---------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| ![多平台搜尋](demo-assets/search-columns.avif)                                                 | ![張量樹](demo-assets/tensor-tree.avif)                                                  |
| _一次查詢、三個 hub：Hugging Face / ModelScope / Civitai 三列結果，帶頭像、下載數與深度連結。_ | _Information 標籤頁以可摺疊的資料夾樹渲染 safetensors 頭部（Hugging Face 檢視器風格）。_ |

10 秒導覽見 [`demo-assets/hero.webm`](demo-assets/hero.webm)。

---

<a id="installation"></a>

## <img src="https://api.iconify.design/lucide/rocket.svg?color=%2322c55e" width="34" height="34" align="middle" alt=""> 安裝

Neo 作為 ComfyUI 自定義節點執行。任選一種方式：

**1 · Git clone（推薦，便於更新）**

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/rikunarita/ComfyUI-Model-Manager-Neo.git
```

**2 · 手動下載**

下載
[儲存庫壓縮檔](https://github.com/rikunarita/ComfyUI-Model-Manager-Neo/archive/refs/heads/main.zip)，
解壓縮到 `ComfyUI/custom_nodes/`，並確認資料夾名為
`ComfyUI-Model-Manager-Neo`。

**3 · ComfyUI Registry（ComfyUI Manager / CLI）**

Neo 已釋出在 ComfyUI registry 上，節點名為
[`comfyui-model-manager-neo`](https://registry.comfy.org/publishers/rikunarita7669/nodes/comfyui-model-manager-neo)：
在 [ComfyUI-Manager] 中搜尋 **“ComfyUI‑Model‑Manager‑Neo”**，或使用官方
命令列安裝：

```bash
comfy node install comfyui-model-manager-neo
```

然後**重啟 ComfyUI**。Python 相依（`huggingface_hub`、`hf_xet`、
`modelscope_hub`、`markdownify`）會在首次啟動時自動安裝。Web 打包產物
預建置於 [`web/`](web)，Rust 核心預建置於
[`native/native-bin/`](native/native-bin)，因此_執行_本擴充套件既不需要
Node.js 也不需要編譯器 —— 一次普通的 `import` 即可載入核心（平台覆蓋
見[引擎表](#the-engine-a-prebuilt-pure-rust-core)）。

透過頂欄的 **「Model Manager Neo」** 按鈕、側邊欄、
`Extensions → Model Manager Neo` 選單或命令面板開啟管理器。

---

<a id="features"></a>

## <img src="https://api.iconify.design/lucide/list-checks.svg?color=%233b82f6" width="34" height="34" align="middle" alt=""> 功能

<details open>
<summary><b>瀏覽與整理</b></summary>

- 兩種佈局：**平鋪**網格（預設檢視）與**資料夾**資源管理器，隨時切換。
- 實時搜尋（支援 `*` 萬用字元與多詞元「AND」匹配）。
- 按名稱、大小、建立日期、修改日期或**最近使用**排序（開啟模型或將其
  加入節點圖即記錄一次使用）。
- 卡片尺寸可調（預設加完全自定義尺寸）。
- 無需重啟即可切換隱藏檔案（以 `.` 開頭）的顯示。
- 圖片**與影片**預覽（任意預覽可在全屏**燈箱**中放大）、懸停時開合動畫的
  懸停時輕輕浮動的淡綠松石玻璃資料夾圖案，以及玻璃質感的無預覽佔點陣圖。
- 類型根資料夾卡片帶有**該類型的合計大小**（輕量容量看板）；記錄的
  SHA256 與庫中其他檔案一致的模型，會在詳細視窗中顯示紅色**重複警告**。
- 存放在類型根目錄之下的模型，會在名稱上方顯示其**子目錄**（兩種佈局
  一致）。
- **智慧收藏** —— 把平鋪檢視當前的搜尋與類型篩選儲存為具名收藏（按使用者
  持久化），一鍵重新應用；全部收納在一個膠囊按鈕中：軟盤部分開啟儲存
  對話方塊，其餘部分開啟應用/切換選單。
- **衛生掃描** —— 純本地清查（不聯網、不算雜湊）：孤立的預覽與筆記、
  沒有預覽的模型、空資料夾，並可透過慣常的確認對話方塊批次清理。
- **可選的資料夾監視** —— 預設關閉的原生監視啟用後，當其他程式增刪
  模型時，受影響的列表約 1.5 秒內重新整理。

</details>

<details>
<summary><b>節點圖整合</b></summary>

- 將模型縮圖拖到畫布上以**新增載入器節點**。
- 拖到已有節點上以**填充匹配的輸入**（存在歧義時精確匹配）。
- 將 **embedding** 拖到文字區以追加 `(embedding:name:1.0)`。
- 將預覽圖拖到節點圖上以**載入其中內嵌的工作流**。
- **新增** 按鈕：把節點放置到畫布。

</details>

<details>
<summary><b>下載</b></summary>

- 貼上 **Civitai**、**Hugging Face**、**ModelScope**（`www.modelscope.ai`）
  或**直接檔案** URL —— 或輸入模型**名稱**，並行搜尋三個 hub。
- Civitai 映象主機 `civitai.red` 上的頁面 URL 與 Civitai 完全同等對待
  （儲存的模型頁保留貼上時的主機名）。
- 解析單個頁面的多個檔案與多個版本，供你挑選。
- 直鏈必須顯式指定目標類型，可選自定義子資料夾。
- 可選預覽圖 —— 保留模型頁提供的**整個圖集**，下載時選取的圖片成為
  卡片的主預覽；每次下載都附帶可編輯的 Markdown 描述。
- **剩餘空間保護**：對話方塊顯示目標卷的剩餘空間，宣告大小放不下的任務
  會被後端拒絕。
- 暫停 / 繼續 / 刪除任務；進度、速度與大小實時更新。
- Hugging Face 下載使用 `huggingface_hub`（可用時加 `hf_xet`）。
- Civitai 下載在完成後做 SHA256 校驗、按檔案類型自動歸位，並對基礎模型
  不匹配與可執行載荷格式發出警告。

</details>

<details>
<summary><b>上傳</b></summary>

- **從本地檔案**上傳到任意模型資料夾（在下載列表中以帶進度的實時任務
  登記）。
- **上傳到 Hugging Face 或 ModelScope**：在嚮導第一步選擇平台；用對應
  權杖認證；儲存庫不存在時自動建立（可選公開/私有）；選擇目標路徑並檢視
  實時進度。ModelScope 始終使用國際站 `www.modelscope.ai` 域名。
- 可選的**相關資產**開關會把每個 `<模型名>.*` 伴隨檔案（預覽圖、Markdown
  筆記）一併上傳到模型所在的儲存庫目錄 —— 筆記還可以作為儲存庫的
  `README.md` 提交。
- 選取的**資料夾**可批次上傳（內部所有模型，保留子資料夾結構），入口在
  資料夾檢視的選擇欄。

</details>

<details>
<summary><b>模型資訊與維護</b></summary>

- 在只讀的 **Information** 表中檢視模型的全部記錄資訊：筆記 YAML
  front‑matter 解析出的作者、基礎模型、全部雜湊（`AutoV1` …
  `SHA256_12`）、格式與精度、模型平台、模型頁連結與所有預覽 URL（未知
  鍵原樣列在末尾）；沒有筆記的模型則顯示 safetensors 的 `__metadata__`
  塊。
- safetensors 模型還會以可摺疊的**資料夾樹**顯示其完整**張量佈局** ——
  點分名稱按段分組，每層帶計數，每張量帶 name / dtype / shape，風格與
  Hugging Face 檢視器一致。張量樹由 Rust 核心預先分組，因此 65,000 張量
  的 MoE 頭部也能即時開啟。
- 重新命名、在資料夾或類型之間移動，或**永久刪除**模型及其預覽與筆記；
  在有未儲存更改時取消編輯會先請求確認。
- 檢視、編輯並儲存模型旁邊的 Markdown 筆記；Information 表本身也可在
  明確警告之後編輯（儲存時會重寫筆記的 front‑matter）。
- 管理預覽**圖集**：排序、移除、新增本地圖片，並選擇主預覽（編輯模式
  中帶藍色圓環的那張）。
- **開啟模型頁**按鈕帶有模型來源 hub（Civitai、Hugging Face 或
  ModelScope）的標誌；**下載到本地**把已儲存的檔案以附件形式流式傳送
  給瀏覽器。
- **按雜湊識別**把本地檔案反查到 Civitai 目錄（先嚐試已記錄的雜湊，
  全部落空再單遍雜湊檔案）。
- 一切資訊都在開啟模型時按需載入 —— 不存在全庫掃描步驟。

</details>

<details>
<summary><b>設定與 i18n</b></summary>

- **Civitai**、**Hugging Face** 與 **ModelScope** 的 API 金鑰，本地儲存於
  `private.key`（並有 `CIVITAI_API_KEY` / `HF_TOKEN` /
  `MODELSCOPE_API_TOKEN` 環境變數回退）。舊版本儲存在 ComfyUI 使用者設定
  中的金鑰會在首次執行時自動遷移。
- 從模型列表中排除指定類型；包含或排除隱藏檔案。
- **監視模型資料夾的外部更改**（預設關閉；網路掛載自動跳過）。
- ZipNN 自動化：自動壓縮 N 天未使用的模型、下載完成後自動壓縮、prompt
  執行期間暫停下載。
- 內建完整的 **English**、**中文**（簡體與繁體）與 **日本語**；地區子標籤
  （`ja-JP` 等）摺疊到其基礎語言，Hant 文字系統標籤選擇繁體中文包。

</details>

---

<a id="search"></a>

## <img src="https://api.iconify.design/lucide/search.svg?color=%2314b8a6" width="34" height="34" align="middle" alt=""> 模型搜尋與多平台發現

**建立下載任務**視窗不僅接受頁面 URL：任何**不以** `https://` 開頭的輸入
都會被當作模型名查詢，在三個平台上並行搜尋 —— **Hugging Face**（左列）、
**ModelScope**（中列）、**Civitai**（右列）。輸入時搜尋模式與 URL 模式
實時切換；結果經短暫防抖後重新整理；每一列各自報告自己的錯誤，不會讓整次
搜尋失敗。

- 每條結果都顯示釋出使用者/組織的**頭像**（hub 未提供頭像時顯示首字母
  徽章）以及累計下載數。
- 模型 id 拆成兩個深度連結：**所有者名**開啟使用者/組織頁，**儲存庫名**開啟
  模型頁；點選行內其他位置則把該模型直接解析進下載編輯器。
- 支援純 **`username/repo-name`** 輸入，且**一次 Enter 總能解析**：先取
  結果中的精確匹配，再把裸儲存庫 id 當作 Hugging Face 儲存庫，最後取第一個
  非空列的首行；若還沒有結果，Enter 立即執行名稱搜尋。
- 每一列都支援翻頁：捲動到底部時，只要存在下一頁就會出現
  **「∨ 顯示更多」**按鈕。
- 各平台的隱藏與**排序方式**可在 **設定 → Model Manager Neo → 搜尋** 中
  選擇（預設為 Hugging Face 趨勢、ModelScope 點贊、Civitai 評分最高）。

Civitai 下載還帶有官方 CLI 普及的安全網，並適配到管理器的任務系統：

- **下載計劃（dry run）** —— 開始前，編輯器顯示解析後的目標路徑、宣告
  大小、公開 SHA256 以及平台 API 金鑰是否已設定。
- **SHA256 校驗** —— 完成的 Civitai 下載會與公開 SHA256 比對；不匹配則
  刪除檔案並讓任務失敗。
- **佈局歸位** —— 版本檔案自身的類型若對映到別的模型資料夾（如隨附的
  VAE），則歸入那個資料夾而非當前選取的資料夾。
- **基礎模型警告** —— 當版本的基礎模型與目標資料夾庫中已記錄的基礎
  模型不符時提示。
- **可執行格式警告** —— pickle 與歸檔載荷在載入時可能執行程式碼；編輯器
  會在下載前明確告知。
- **Hub 帳戶（whoami）** —— 對每個已設定金鑰的平台，下載對話方塊顯示已
  連線的帳戶；401 失敗時會準確說明在哪裡建立金鑰、如何繼續。

放大 Civitai 來源模型的預覽時，燈箱左側顯示圖片、右側顯示解析出的
**生成中繼資料**（提示詞、負面提示詞、取樣器、步數、CFG scale、種子、
clip skip、尺寸、基礎模型與資源配方）。

模型詳細視窗的**按雜湊識別**向 Civitai 目錄詢問某個本地檔案是哪個模型
版本：先嚐試 Markdown 伴隨檔案中已記錄的雜湊，全部落空才對檔案做單遍
雜湊（`SHA256` / `AutoV2` / `AutoV1` / `CRC32`，外加 `BLAKE3`）。命中時
開啟解析出的模型與版本，附帶基礎模型、觸發詞、檔案列表以及官方 CLI
會列印的同一條 `civitai download` 命令；未命中則報告找不到匹配的模型
版本。

---

<a id="zipnn"></a>

## <img src="https://api.iconify.design/lucide/package-plus.svg?color=%230ea5e9" width="34" height="34" align="middle" alt=""> ZipNN 無失真壓縮

大型 `.safetensors` 檢查點很快就會吃滿磁碟。Neo 以
[ZipNN](https://github.com/zipnn/zipnn) 格式**就地、無損**地壓縮與解壓縮
它們 —— 與官方 ZipNN 專案相同的張量感知方案 —— 由 Neo 的**純 Rust
核心**執行，並在 CI 中與官方 `zipnn` 0.5.4 包雙向交叉驗證，因此產物與
更廣泛的 ZipNN 生態保持可互換。

### 1. 工作原理

模型權重絕大部分是浮點數，而浮點數絕大部分是_冗餘_的：表現良好的權重
張量中，指數字節會反覆出現。ZipNN 正是利用這一點。對每張量：

- 將值**拆分**為位元組平面，並重排符號 / 指數 / 尾數位元，使相似位元組聚集
  在一起，然後
- 用 FiniteStateEntropy（FSE）編解碼器對每個平面做 **Huffman 編碼**。

非浮點張量（整數索引、掩碼等）在官方配方中會原樣穿過 —— **Neo 的 Rust
核心則同樣壓縮它們**（覆蓋全部 safetensors dtype，分兩個互操作帶；見下方
[dtype 覆蓋與互操作矩陣](#dtype-coverage--the-interoperability-matrix)）——
而壓縮後實際不會變小的張量則**原樣保留**。每張被壓縮的張量以 `uint8`
向量儲存，檔案在單條 `znn_compressed_vectors` 中繼資料中記錄它們各自的
原始 `dtype` 與 `shape`。不做任何近似或丟棄 —— 解壓縮**逐位元**復原原始
檔案。

壓縮後的模型寫在原件旁邊，命名為 `<name>.znn.safetensors` —— 正是官方
ZipNN 工具（以及打過 `zipnn_safetensors()` 補丁的載入器）所期望的字尾，
因此打過補丁的 ComfyUI 載入器可以透明地讀取 Neo 壓縮的模型。真實的
檢查點通常能壓到原大小的 **60–80 %**（隨機性強的資料壓縮率低得多；
低熵權重則壓縮得更多）。

<a id="dtype-coverage--the-interoperability-matrix"></a>

### 2. dtype 覆蓋與互操作矩陣

Rust 核心以兩個互操作帶壓縮 **safetensors 0.8 定義的全部 22 種 dtype**。
壓縮檔案所屬的帶記錄在中繼資料中（擴充套件帶為 `znn_neo_extended="1"`），並
在介面中呈現：Information 標籤頁的 **Neo Extended** 徽章、dtype 明細行
（`bfloat16×412, uint8×3, …`），以及壓縮確認框中事先的明確提示。

| 張量 dtype                                                                                                                      | ZipNN dtype 碼    | 官方 ZipNN 0.5.4 工具的行為                                     |
| ------------------------------------------------------------------------------------------------------------------------------- | ----------------- | --------------------------------------------------------------- |
| `F32` `F16` `BF16` `F8_E4M3` `F8_E5M2`                                                                                          | 1–30（上游帶）    | **原樣解碼 Neo 的檔案**                                         |
| `F64` `C64` `I8` `U8` `BOOL` `I16` `U16` `I32` `U32` `I64` `U64` `F8_E4M3FNUZ` `F8_E5M2FNUZ` `F8_E8M0` `F4` `F6_E2M3` `F6_E3M2` | 128–146（Neo 帶） | **以明確錯誤拒絕** —— 絕不靜默損壞（已在 CI 中針對 pip 版實證） |

值得了解的細節：

- 官方解碼器對所有未實現的 dtype 碼都會以
  `ValueError: Unsupported Dtype N` 拒絕 —— Neo 擴充套件檔案在原理上就不可能
  被上游工具誤解碼；在 Neo 內部則與其他檔案一樣以 SHA‑256 校驗逐位元組
  還原；
- `complex64` 使用 Neo 帶（碼 130）：官方 0.5.4 解碼器沒有保留碼 9 的
  分支，會像拒絕 Neo 碼一樣拒絕它（已在 CI 中用測試實證），因此不存在
  需要相容的物件；
- 高位位元組全為零的整數張量（`< 65536` 的 `int32` 索引、掩碼、縮放表等）
  還會使用**截斷模式**：全零位元組平面整體從載荷中丟棄 —— 由於壓縮器只
  丟棄它在整張量範圍內驗證過為零的平面，這在構造上就是無損的；
- `complex128` 與 `bcomplex32` 只存在於 codec 層（碼 129/131），沒有
  safetensors 表示 —— 任何 `.safetensors` 檔案都承載不了它們。

### 3. 使用方法

開啟任意 `.safetensors` 模型，按下預覽與資訊表之間的 **ZipNN 按鈕**。
確認後：

1. 壓縮期間按鈕變為**進度條**；ComfyUI 保持響應，任務可隨時取消；
2. 完成後原檔案替換為 `<name>.znn.safetensors`，預覽與 Markdown 筆記
   跟隨改名，網格自動重新整理。

壓縮是可逆的：在壓縮檔案完全寫入並校驗通過之前，原檔案絕不會被刪除；
解壓縮時會與壓縮時記錄的 SHA‑256 進行校驗。

開啟**已壓縮**的模型時，同一按鈕翻轉為_解壓縮_（以反色顯示），還原出普通
`.safetensors`。資訊表會以**原始檔案大小**、**壓縮後檔案大小**與
**佔原始大小百分比**三行取代單行的_檔案大小_（由官方 ZipNN CLI 壓縮的
檔案不記錄原始大小，仍顯示單行）。

同一按鈕也位於**每張模型與資料夾卡片的右上角**（星標旁），無需開啟詳情
視窗即可壓縮或解壓縮。執行中的任務以環形進度圈顯示（批次時帶百分比）。

### 4. 批次壓縮（整個資料夾）

選取資料夾（「Select files」）後按下**底部欄的 ZipNN 圖案按鈕** —— 或
使用資料夾卡片右上角的按鈕 —— 資料夾樹內所有 `.safetensors` 模型都會
被壓縮（預覽與筆記跟隨各自的模型），並**移入打包資料夾
`<name>_DeltaZNN`**；原資料夾清空後消失。已經就地壓縮的模型（單模型按鈕、自動壓縮或舊版本產物）
不會被重新壓縮，而是原樣移入打包資料夾 —— 不會有已壓縮檔案殘留在其旁。
`*_DeltaZNN` 打包資料夾是密封的：

- 其中只能存放 ZipNN 內容（`*.znn.*` 模型、`*.znn` 差分檔案）；普通
  模型的上傳、下載與移入都會被拒絕；
- 打包資料夾與普通資料夾不能同時選取 —— 勾選其中一類時，另一類會帶
  警告通知自動取消選取；
- 打包資料夾的 ZipNN 按鈕是**反色**的；按下即**批次解壓縮**整個打包檔案
  夾，把全部內容移回以其命名的資料夾（清空的打包資料夾被刪除）；
- 差分資料夾（`<base>_DeltaZNN`，見下文）也是打包資料夾：其反色按鈕
  一次性還原其中每個微調模型；
- 模型**類型根資料夾**（`checkpoints` 等）的打包資料夾建在**自己內部**
  （`<root>_DeltaZNN`）—— 類型根的兄弟目錄會落在 ComfyUI 資料夾對映
  之外，從載入器與管理器中都會消失；方向自動檢測：存在普通模型時
  壓縮，只剩打包資料夾時解壓縮；
- 舊版本建立的打包資料夾（`<name>_ZNN`）仍能被識別並解壓縮回原名。

多個資料夾按佇列執行：一次確認、逐次任務、同一時間只有一個進度狀態。

### 5. 差分壓縮（微調相對基礎模型）

微調模型與它的基礎模型共享大部分位元組，ZipNN 可以只儲存**差異**：恰好
選取兩個普通 `.safetensors` 模型，按下底部欄的 **ZipNN 差分壓縮**。小
對話方塊讓你選擇哪一個是**基礎**、哪一個是**微調**（兩者可以帶不同的
中繼資料）。結果 —— 通常只有微調模型大小的百分之幾 —— 寫入
**`<base>_DeltaZNN/<ft>_delta_<base>.znn`**，冗餘的微調檔案被刪除。
解壓縮差分（其卡片按鈕，反色圖案）會把微調模型**逐位元組精確**還原到基礎
模型旁邊，並撤走清空的差分資料夾。還原需要基礎模型仍在，且差分檔案
記錄了微調模型自身的 SHA‑256，因此還原全程可驗證。

差分檔案以官方 ZipNN 的 **streaming 容器**格式寫出：官方 `zipnn` 套件
（位元組差分模式）可以逐位元組精確地還原它們，反過來 Neo 也能還原官方
工具生成的差分（單一容器與 streaming 兩種形式）—— 兩個方向都包含在 CI
交叉驗證中。此外，`.znn` 會註冊進 ComfyUI 的支援模型副檔名清單（與原版
實驗性的 `.gguf` 一樣），因此差分檔案會作為受管理的模型出現在網格中，
可以直接從介面還原。

### <a id="the-engine-a-prebuilt-pure-rust-core"></a>6. 引擎：預建置的純 Rust 核心

壓縮器並非對官方 Python 包的封裝，而是 Neo 自研的純 Rust 引擎在執行該
格式：上游 C 擴充套件在 PyPI 上沒有 Linux wheel（`pip install zipnn` 需要
從原始碼編譯），Neo 把這份編譯完全移出你的機器。格式被移植到 Rust
（[`native/crates/znn-codec`](native/crates/znn-codec)：格式核心無
`unsafe` 程式碼、七個持續 fuzz 目標、與原始 C 實現位元組一致的差分記錄），
並以**預建置 abi3 / abi3t 二進位**形式隨儲存庫分發 —— 每個平台 × 每種
Stable ABI 風味一個，僅靠 `import` 載入：

| 平台                            | 產物                                            | 要求                                                |
| ------------------------------- | ----------------------------------------------- | --------------------------------------------------- |
| Linux x86_64                    | `native-bin/linux-x86_64/mm_core.abi3.so`       | glibc ≥ 2.28（Debian 10 / Ubuntu 20.04+）           |
| Linux aarch64                   | `native-bin/linux-aarch64/mm_core.abi3.so`      | glibc ≥ 2.28                                        |
| macOS（Intel 與 Apple Silicon） | `native-bin/macos-universal2/mm_core.abi3.so`   | 單個 fat 二進位 —— Intel 10.12+ / Apple Silicon 11+ |
| Windows x86_64                  | `native-bin/windows-x86_64/mm_core.pyd`         | MSVC 建置                                           |
| Linux x86_64（自由執行緒）      | `native-bin/linux-x86_64t/mm_core.abi3t.so`     | glibc ≥ 2.28，自由執行緒 CPython 3.15+              |
| Linux aarch64（自由執行緒）     | `native-bin/linux-aarch64t/mm_core.abi3t.so`    | glibc ≥ 2.28，自由執行緒 CPython 3.15+              |
| macOS（自由執行緒）             | `native-bin/macos-universal2t/mm_core.abi3t.so` | 單個 fat 二進位，自由執行緒 CPython 3.15+           |
| Windows x86_64（自由執行緒）    | `native-bin/windows-x86_64t/mm_core.pyd`        | MSVC 建置，自由執行緒 CPython 3.15+                 |

每個平台的一個二進位即可服務 **CPython 3.12 及以上**所有版本（Stable
ABI、`abi3-py312` —— 已在 CI 中針對 3.12 與 3.14 實證）；自由執行緒建置則由
**abi3t** 孿生產物服務（`abi3t-py315`、PEP 803 —— 已在 CI 中針對 3.15 的
GIL/自由執行緒兩種建置實證），載入器會自動選擇（自由執行緒直譯器無法載入普通
abi3 二進位；3.15+ 的 GIL 建置繼續使用普通產物）。每個二進位都受 ≤ 5 MB 的
CI 尺寸預算關卡約束（八個二進位的合計以 40 MB 參考上限管理）。linux-x86_64 與
Windows 的 GIL 二進位經過 **PGO 最佳化** —— Profile-Guided Optimization，每次
CI 建置都從確定性工作負載重新訓練；CI A/B 實測相對未最佳化建置的首次執行
吞吐最高約快 10 %（[BENCH §13](docs/BENCH.md)）；abi3t 二進位現階段以非 PGO
方式發布。

這次移植也從根源上改善了可靠性：在重寫過程中，C 核心的差分路徑被實證
存在一類記憶體安全缺陷（特定輸入長度下的確定性崩潰、非整數倍塊上的越界
寫入）。Rust 引擎從結構上消除了這一缺陷類 —— 所有平面拆分與塊運算都帶
邊界檢查，唯一的 `unsafe` 邊界（只讀 mmap）也經過安全評審 —— 當年觸發
崩潰的輸入已被固定為迴歸測試。互操作不是承諾而是 CI 關卡：`integration`
工作流在每次 push 時與**官方 pip `zipnn` 0.5.4** 雙向交叉驗證。授權：
格式移植歸屬 ZipNN（MIT）與 FiniteStateEntropy（BSD‑2‑Clause）；預覽
WebP 編解碼使用 zenwebp（AGPL‑3.0）—— 全文見
[`native/NOTICE`](native/NOTICE)。

在沒有對應二進位的平台上（其他架構、32 位、特殊 libc），擴充套件仍然可以
安裝：瀏覽、下載與雜湊回退到純 Python 路徑，而 ZipNN 操作與預覽重編碼
會報告載入器給出的確切原因，絕不靜默失敗。

> [!NOTE]
> 壓縮透過 mmap 流式處理檔案 —— 峰值記憶體約等於最大單張量，而非整個
> 模型（12 GB 的檢查點也能在 1 GB 以內完成壓縮）。**無損且經過驗證**：
> 核心在壓縮時記錄原件的 SHA‑256，還原時內聯複核（不匹配則保留壓縮
> 檔案，並把產物移為 `.corrupt` 以供檢查）；普通 `.safetensors` 只在
> `.znn.safetensors` 寫入並透過原子改名驗證之後才被刪除，失敗的執行會
> 清理自己的部分產物。可選的 **paranoid 模式**還會在刪除原件之前再解壓縮
> 一遍並比對。

---

<a id="what-changed"></a>

## <img src="https://api.iconify.design/lucide/git-compare.svg?color=%23a855f7" width="34" height="34" align="middle" alt=""> 與原版相比改變了什麼

本節按 GPL‑3.0 授權的要求明示 fork 的差異。比較基準為
[`hayden-cn/ComfyUI-Model-Manager`](https://github.com/hayden-cn/ComfyUI-Model-Manager)
**v2.8.5**。功能被保留並擴展；被_移除_的共有三樣：PrimeVue 相依本身、
批次掃描功能，以及複製節點按鈕 —— 見[被移除的功能](#removed-features)。

### <img src="https://api.iconify.design/lucide/palette.svg?color=%23d946ef" width="26" height="26" align="middle" alt=""> 介面

| 區域           | 原版                                                      | **Neo**                                                                                                                                                                                                              |
| -------------- | --------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 元件庫         | PrimeVue 4                                                | **reka‑ui**（無樣式）+ shadcn‑vue 風格封裝                                                                                                                                                                           |
| 樣式           | Tailwind CSS v3 + PrimeVue 主題                           | 帶作用域 `--mm-*` 設計權杖的 **Tailwind CSS v4**                                                                                                                                                                     |
| 圖示           | PrimeIcons                                                | 透過圖示對映使用 **Lucide**（`@lucide/vue`）                                                                                                                                                                         |
| 觀感           | 標準 PrimeVue 表面                                        | **玻璃擬態**（模糊、層次、微互動），自動深色模式                                                                                                                                                                     |
| 對話方塊       | PrimeVue `Dialog`/`ContextMenu`                           | reka‑ui 對話方塊，逐對話方塊尺寸/位置、拖曳移動、帶錨點的右鍵選單                                                                                                                                                    |
| 模型詳細標籤頁 | Description + Metadata（原始 safetensors `__metadata__`） | Description + **Information**：解析筆記 YAML front‑matter 的只讀表格（作者、基礎模型、雜湊、格式與精度、模型平台、模型頁連結、所有預覽 URL，未知鍵原樣列出），回退為原始 `__metadata__`，外加 safetensors **張量樹** |
| 語言           | English、中文                                             | English、中文（簡體＋**繁體**）、**日本語**（完整語言包）                                                                                                                                                            |

### <img src="https://api.iconify.design/lucide/cpu.svg?color=%230ea5e9" width="26" height="26" align="middle" alt=""> 後端與引擎

最深層的改變在介面之下。原版為純 Python（7 個後端模組、19 條 HTTP
路由）；Neo 成長為 16 個 Python 模組、42 條路由，並把所有熱點路徑移入
預建置 Rust 擴充套件（`native/`，基於 Stable ABI 的 PyO3 —— 見
[引擎表](#the-engine-a-prebuilt-pure-rust-core)）。純 Python 回退只保留在
「降級回答優於報錯」的地方：

| 區域             | 原版                                                                                                   | **Neo**                                                                                                                                                                                                                                                                    |
| ---------------- | ------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 模型列表         | 每次請求遞迴 Python `os.scandir`                                                                       | Rust 並行遍歷 + 跨重啟持久化的 front‑matter 索引（5,000 模型掃描冷啟動約 7.5 倍、熱態約 100 ms；逐條目 golden 測試）                                                                                                                                                       |
| 模型詳細路由     | 頭部解析跑在**事件迴圈上** —— 巨大 MoE 頭部會凍住整個伺服器                                            | 經 executor + Rust 解析；伺服器保持響應                                                                                                                                                                                                                                    |
| 雜湊             | 單條 `hashlib` SHA‑256 迴圈                                                                            | 五種記法（`SHA256`/`AutoV1`/`AutoV2`/`CRC32`/`BLAKE3`）**一遍**流式完成                                                                                                                                                                                                    |
| 下載校驗         | 完成後整檔案重讀                                                                                       | 寫入迴圈供給的內聯摘要 —— 零額外 I/O —— 保留 Civitai SHA‑256 關卡                                                                                                                                                                                                          |
| safetensors 頭部 | `comfy.utils` + `json.loads`                                                                           | 單一路由後的 Rust jiter 解析（metadata + tensors + 預分組展示樹；65k 張量 MoE 樹建置約快 100 倍，wire 格式與 JS 交叉核對）                                                                                                                                                 |
| ZipNN 壓縮       | —                                                                                                      | 整個引擎：壓縮 / 解壓縮 / 資料夾批次 / 微調差分，mmap 流式（任何模型都低於 1 GB 記憶體）、SHA‑256 校驗還原、協作式取消                                                                                                                                                     |
| 預覽圖           | PIL 重編碼；動畫固定到第 1 幀                                                                          | zenwebp（純 Rust）編碼/解碼；動畫 GIF/WebP 預覽**保持動畫**（幀、時長、迴圈數與 ICC 配置檔案均保留）                                                                                                                                                                       |
| Hub 整合         | 僅 Civitai 與 Hugging Face：頁面解析用阻塞 `requests`，檔案經普通 HTTP URL 取得 —— 完全沒有 ModelScope | **Civitai + Hugging Face + ModelScope** —— ModelScope 為全新整合（下載源、上傳目標、搜尋樞紐與認證）。SDK 傳輸（`huggingface_hub` + `hf_xet`、`modelscope_hub`）、三樞紐並行名稱搜尋、依樞紐存於 `private.key` 的 API 金鑰（環境變數回退 + 從 ComfyUI 設定遷移）、雜湊反查 |
| Hub HTTP         | 執行緒池 worker 內的阻塞 `requests`                                                                    | 事件迴圈上一條共享 `aiohttp` 會話（停滯的 CDN 再也無法按 read timeout 的 120 秒佔住 worker）                                                                                                                                                                               |
| 資料夾監視       | —                                                                                                      | 可選的原生 `notify` 監視（預設關閉）：按類型約 1.5 秒重新整理，跳過網路掛載，監視預算耗盡時降級到 30 秒 TTL 重新整理                                                                                                                                                       |
| 模型庫衛生       | —                                                                                                      | 孤立伴隨檔案 / 空資料夾清查與批次清理                                                                                                                                                                                                                                      |
| 上傳預檢         | —                                                                                                      | HF/ModelScope 上傳的重複檢測雜湊在原生核心中執行（釋放 GIL）                                                                                                                                                                                                               |

在原版之上的功能級新增 —— **完整的 ModelScope 整合**（下載源、上傳目標、
搜尋樞紐與認證）、上傳到 Hugging Face、基於 SDK 的 Hugging Face 下載
（`huggingface_hub` + `hf_xet`；原版僅抓取普通 resolve URL）、多 hub 搜尋、
雜湊識別、智慧收藏、星標、「最近使用」記錄與排序、多選、建立資料夾、
直鏈下載、瀏覽器內「下載到本地」、剩餘空間保護、Civitai 下載安全網、
圖集預覽、SHA256 重複警告、子目錄標籤與類型根目錄的合計大小、全屏預覽
燈箱、日語與繁體中文語言包 —— 已在[功能](#features)中描述；全部為
Neo 側的工作。

### <img src="https://api.iconify.design/lucide/package.svg?color=%23f97316" width="26" height="26" align="middle" alt=""> 相依包

- **移除：** `primevue`、`@primevue/themes`、`lodash`、`dayjs`、`js-yaml`
  （最後一個在原版中即已未被使用 —— YAML 工作一直由 `yaml` 承擔）。
- **新增 / 替換：** `reka-ui`、`@lucide/vue`、`es-toolkit`（← lodash）、
  `date-fns`（← dayjs）、`vue-sonner`（通知）、
  `class-variance-authority`、`clsx`、`tailwind-merge`。
- **升級：** Vite 5 → **8**（Rolldown）、TypeScript 5 → **6**、Vue i18n 9 →
  **11**、markdown‑it 14 → **15**、`@vueuse/core` 11 → **15**、`yaml` 2.6 →
  **2.9**。
- **Python：** 新增 `huggingface_hub` + `hf_xet` + `modelscope_hub`（原版僅
  需要 `markdownify`）；以 asyncio 任務池取代舊執行緒池；以共享 aiohttp
  客戶端取代所有直接阻塞的 `requests` 呼叫。
- **Rust：** 新增 `native/` 工作區（`znn-codec` 格式核心 + `mm-core` PyO3
  繫結），以預建置 abi3 / abi3t 二進位分發 —— 擴充套件本身不安裝任何編譯型 Python
  包。ZipNN 壓縮完全由 Neo 側實現（原版從未提供）；本 fork 在開發早期
  階段曾隨附的 vendored ZipNN C 原始碼及其按 CPython 版本劃分的 `.so` 檔案，
  在 Rust 核心就位後已全部移除。

### <img src="https://api.iconify.design/lucide/sliders-horizontal.svg?color=%2306b6d4" width="26" height="26" align="middle" alt=""> 工具列 / 按鈕職責

管理器頭部被重新設計為明確的圖示驅動操作：**平鋪 ⇄ 資料夾佈局切換**、
**衛生掃描**、**顯示/隱藏隱藏檔案**、**重新整理**、**下載列表**，以及
**上傳到 Hugging Face / ModelScope**。

### <img src="https://api.iconify.design/lucide/folder-open.svg?color=%23f59e0b" width="26" height="26" align="middle" alt=""> 玻璃資產包（資料夾圖示與無預覽圖案）

介面使用 `assets/` 中手工製作的玻璃擬態資產包：

- **資料夾卡片**靜止時顯示一隻玻璃資料夾；懸停時開始輕柔的 CSS 浮動
  （上下起伏），指標離開後立即恢復靜止。SVG 為不含 SMIL 的純向量檔案，
  透過 HTTP 以 ETag 和一天 max‑age 提供服務，所有卡片共享同一份快取副本。
- **麵包屑**為每一段加上小資料夾字形。
- **沒有預覽的模型**使用玻璃質感的 NO‑PREVIEW 圖案，以向量
  （`image/svg+xml`）形式提供，因此絕不會被柵格化。
- **模型 hub 標誌**（Civitai、Hugging Face、ModelScope）作為**開啟模型
  頁**按鈕的背景，模型來源一眼可辨。

_為什麼偏偏是淡綠松石？因為這是 **Neo**。_

### <img src="https://api.iconify.design/lucide/hammer.svg?color=%2365a30d" width="26" height="26" align="middle" alt=""> 工具鏈

lint 與格式化流水線是一套約定俗成、配置完整的組合：前端 **ESLint 10
flat config** + **Prettier** + **Stylelint 17**，Python 後端 **Ruff** +
**mypy**，Rust 工作區 **clippy `-D warnings`** + **rustfmt**，並由
**dependency‑cruiser**（匯入圖關卡）與 [Fallow](https://fallow.tools)
（死程式碼與重複）補全。品質由五層測試金字塔保障：Rust 單元測試、golden
契約測試、**cargo‑fuzz** 目標（7 個表面、每週每目標 3 小時預算）、在
三個 OS 上針對建置產物的完整 pytest 套件，以及官方 `zipnn` 交叉驗證
（見[開發](#development)）。

---

<a id="removed-features"></a>

## <img src="https://api.iconify.design/lucide/trash-2.svg?color=%23ef4444" width="34" height="34" align="middle" alt=""> 被移除的功能

<a id="removed-feature"></a>

### <img src="https://api.iconify.design/lucide/scan-search.svg?color=%23ef4444" width="26" height="26" align="middle" alt=""> 批次掃描

**「批次掃描模型資訊」** 功能已被移除，因為它是冗餘的：模型詳細視窗
直接從 safetensors 頭部讀取該模型的 `__metadata__`，連同檔案旁的
Markdown 筆記一起呈現；沒有預覽的模型在網格中直接帶上隨附的玻璃無
預覽圖案。那種遍歷全庫、雜湊每個模型並向 Civitai 按雜湊查詢的做法，是
通往同一資訊的第二條、慢得多的路徑 —— 還附帶一個模態對話方塊、一個
全域性 store、websocket 事件、磁碟上的任務檔案與它自己的設定，全都需要
維護。

比掃描活得更久的兩項設定如今驅動著**模型列表**（哪些類型載入網格、
是否顯示以 `.` 開頭的檔案），設定分類為 **Model List**。它們保留歷史
的 `ModelManager.Scan.*` ID 字串，因為這個 ID 是 ComfyUI 持久化每個
使用者取值所用的鍵 —— 改名會讓所有已安裝環境儲存的設定變成孤兒。

> [!NOTE]
> **放棄的內容：** 按檔案雜湊從 Civitai _批次回填_ 預覽與描述的唯一途徑。
> 資訊從未獲取過的模型會一直保留佔位預覽，直到手動設定預覽/筆記
> （編輯器的圖集條），或透過_建立下載任務_重新下載。讀取模型資訊不受
> 影響 —— 它始終按需從磁碟讀取；單個模型仍可透過詳細視窗的雜湊反查
> 在 Civitai 目錄中識別。

<a id="removed-feature-copy-node"></a>

### <img src="https://api.iconify.design/lucide/clipboard-x.svg?color=%23ef4444" width="26" height="26" align="middle" alt=""> 複製節點到剪貼簿

**「複製節點到剪貼簿」**按鈕（模型詳細操作列與卡片懸停列均已移除）已刪除：
把半設定的載入器節點複製進 ComfyUI 內部剪貼簿，容易與圖譜自身的複製/貼上
流程衝突；而其實際目的（把載入器節點放到畫布上）由拖曳卡片或**新增節點**
按鈕更直接地達成。

---

<a id="documentation"></a>

## <img src="https://api.iconify.design/lucide/book-open.svg?color=%237c3aed" width="34" height="34" align="middle" alt=""> 文件

逐步使用指南，每份都完整自足：

- [`docs/USAGE.md`](docs/USAGE.md) — English
- [`docs/USAGE.ja.md`](docs/USAGE.ja.md) — 日本語
- [`docs/USAGE.zh-CN.md`](docs/USAGE.zh-CN.md) — 中文（簡體）
- [`docs/USAGE.zh-TW.md`](docs/USAGE.zh-TW.md) — 中文（繁體）

內容涵蓋安裝、兩種佈局、卡片操作與拖曳到節點圖、模型編輯器（資料夾
選擇器、帶資料夾字首的檔名、預覽、描述）、下載與任務列表、hub 上傳
（Hugging Face / ModelScope）的階段與完成訊息、ZipNN 壓縮、設定與
語言，以及疑難排解表。

延伸閱讀：

- [`docs/BENCH.md`](docs/BENCH.md) —— 本 README 中所有效能結論背後的
  測量記錄。
- [`native/README.md`](native/README.md) —— Rust 工作區：佈局、測試
  金字塔、fuzz 配置與預建置二進位的生成方式。
- [`SECURITY.md`](SECURITY.md) —— 如何私下回報漏洞、範圍界定，以及
  每次 push 都會執行的 CI 安全關卡。

---

<a id="development"></a>

## <img src="https://api.iconify.design/lucide/terminal.svg?color=%230ea5e9" width="34" height="34" align="middle" alt=""> 開發

**建置** Web 打包產物只需要 Node.js；在 ComfyUI 內執行擴充套件只需要
Python（Rust 核心預建置隨附）。

```bash
corepack enable          # 使用鎖定的 pnpm 版本（Node 26）
pnpm install
uv sync --frozen         # Python 開發/測試環境（.venv）
```

Python 開發/測試環境（pytest、ruff、mypy、hub SDK、torch‑CPU）由
**[uv]** 管理 —— `uv sync --frozen` 從 `pyproject.toml` 的
`[dependency-groups]` 與已提交的 `uv.lock` 一次性重建。這只是開發上的
便利：_執行時_契約不變 —— ComfyUI 仍會在首次啟動時自行安裝
`requirements.txt`（兩份清單由測試機械地固定為一致）。

開發 Rust 核心時，stable 工具鏈就足夠了 —— debug 建置也是合法的
`mm_core`（API 握手與整個 pytest 套件的行為與 release 一致）：

```bash
cd native && cargo build -p mm-core
cp target/debug/libmm_core.so native-bin/linux-x86_64/mm_core.abi3.so   # 本平台的 tag
```

`scripts/build-native.sh --target <tag> --size-gate` 可復現隨附的 release
產物（cargo‑zigbuild 保證 glibc ≥ 2.28 下限、maturin + lipo 生成 macOS
universal2、maturin/MSVC 生成 Windows）；[`native/README.md`](native/README.md)
記錄了工作區、測試金字塔與 fuzz 配置。

| 指令碼                                | 用途                                                          |
| ------------------------------------- | ------------------------------------------------------------- |
| `pnpm dev`                            | Vite 開發伺服器（為 ComfyUI 熱過載寫入 `web/manager-dev.js`） |
| `pnpm build`                          | 生產建置到 `web/`                                             |
| `pnpm build:clean`                    | 刪除 `web/` 後重新建置                                        |
| `pnpm rebuild`                        | 刪除 `node_modules/` **與** `web/`，重新安裝後建置            |
| `pnpm typecheck`                      | `vue-tsc --noEmit` 類型檢查                                   |
| `pnpm lint` / `pnpm lint:fix`         | ESLint（flat config）                                         |
| `pnpm lint:css` / `pnpm lint:css:fix` | Stylelint 17（CSS + Vue SFC style 塊，相容 Tailwind v4）      |
| `pnpm deps`                           | dependency-cruiser：匯入圖關卡（需要 Node ≥ 22）              |
| `pnpm deps:graph`                     | 輸出模組圖 `dependency_graph.svg`                             |
| `pnpm format` / `pnpm format:check`   | Prettier（帶 Tailwind 外掛）                                  |
| `pnpm py:lint` (`:fix`)               | 後端 Ruff lint（`py/`、`__init__.py`、`tests/`、`scripts/`）  |
| `pnpm py:format` (`:check`)           | 後端 Ruff format                                              |
| `pnpm py:test`                        | pytest 套件（未建置 `mm_core` 時跳過 native 路徑測試）        |
| `python -m mypy`                      | 後端靜態類型（pyproject 的 `[tool.mypy]`）                    |
| `pnpm rs:fmt` (`:check`) / `rs:lint`  | `native/` 的 rustfmt / clippy `-D warnings`                   |
| `pnpm rs:test`                        | Rust 單元 + 整合測試（mm-core 不帶 extension-module）         |
| `pnpm rs:build`                       | `mm-core` 的 release 建置                                     |
| `pnpm fallow`                         | Fallow 完整流水線：死程式碼 + 重複 + 健康度                   |
| `pnpm fallow:dead` (`:type-aware`)    | 未使用檔案/export/類型/相依、迴圈 —— 可選的 TS 語義分析       |
| `pnpm fallow:dupes`                   | AST 克隆檢測（`mild` 模式，見 `.fallowrc.json`）              |
| `pnpm fallow:health`                  | 複雜度熱點、重構目標、0–100 健康分                            |
| `pnpm fallow:fix:dry` / `fallow:fix`  | 自動清理預覽 / 應用（永遠先 dry-run）                         |
| `pnpm fallow:audit`                   | PR 風格關卡：只報告當前變更引入的問題                         |

**husky** 的 `pre-commit` 鉤子會對暫存檔案執行 **lint-staged**（前端
ESLint + Stylelint + Prettier，後端 Ruff），外加完整的 `pnpm typecheck`。

### 1. 品質關卡

**Fallow**（Rust 實現，分析器內不含 AI）把儲存庫讀作一張相依圖，報告未
使用的檔案/export/類型/相依、迴圈匯入、克隆組與複雜度熱點；程式碼樹保持
**零未使用 export、零重複**，CI 在任何 ERROR 級發現上失敗。

**ESLint 10** flat config 串聯 `typescript-eslint`、`eslint-plugin-vue`、
`eslint-plugin-import-x`、`eslint-plugin-tailwindcss` 與
`eslint-config-prettier`；**Prettier** 負責格式化與 Tailwind 類排序；
**Stylelint 17** 檢查 `src/style.css` 與所有 SFC style 塊；
**dependency‑cruiser 18** 把關 `src/` 的匯入圖（無迴圈、無孤兒、出貨
程式碼不匯入 devDependency 與 Node core）。

**Ruff**（`pyproject.toml [tool.ruff]`）負責後端 lint 與格式化（目標
`py312`、行寬 120、精選規則集），其上再由 **mypy** 檢查靜態類型。

**CI** 在每次 push 時執行以上全部，外加前端測量關卡
（`scripts/bench/front/k15.mjs`）；`native` 工作流建置八個平台產物
（四個 abi3 + 四個 abi3t）、強制執行尺寸預算、對全部七個 fuzz 目標做
smoke fuzz、在 CPython 3.12 與 3.14 下 import abi3 產物、在 3.15 的
GIL/自由執行緒兩種建置下 import abi3t 產物，並在 Linux、Windows、macOS 上
執行完整 pytest 套件（含自由執行緒 3.15t 單元）與官方 `zipnn` 交叉驗證。

**安全關卡**與上述檢查並行，由 `Security` 工作流程承載：**CodeQL**
（default setup、extended 查詢套件 —— TypeScript/Vue、Python、Rust 以及
Actions 設定本身）、**OSV-Scanner**（全部四個相依面；PR 以新引入的漏洞
攔截）、**Gitleaks**（與 GitHub 自帶 push protection 並行的全歷史金鑰
掃描）與 **zizmor**（工作流程加固）；所有接受的風險都附有書面理由 ——
詳見 [`SECURITY.md`](SECURITY.md)。

### 2. 專案結構

```
├─ __init__.py            # ComfyUI 入口：安裝相依、註冊路由
├─ py/                    # Python 後端（aiohttp 路由、任務、hub 客戶端）
│  ├─ manager.py          #   模型 CRUD + native 加速的列表/衛生掃描
│  ├─ download.py         #   下載任務（http + huggingface_hub + modelscope_hub）
│  ├─ upload.py           #   本地檔案上傳（路徑校驗）
│  ├─ upload_hf.py        #   上傳到 Hugging Face（共享 hub 流水線）
│  ├─ upload_modelscope.py#   上傳到 ModelScope
│  ├─ compress.py         #   驅動 native 任務 API 的 ZipNN 路由
│  ├─ information.py      #   Civitai/HF/ModelScope 頁面解析、預覽服務
│  ├─ search.py           #   多平台模型名搜尋 + 頭像代理
│  ├─ identify.py         #   Civitai 雜湊反查
│  ├─ native.py           #   預建置核心載入器（平台 tag、API 握手）
│  ├─ http_client.py      #   所有 hub 往返共享的 aiohttp 會話
│  ├─ watcher.py          #   可選的模型庫監視（native notify，預設關閉）
│  ├─ auth.py · config.py · thread.py · utils.py
├─ native/                # Rust 工作區（GPL-3.0；歸屬見 native/NOTICE）
│  ├─ crates/znn-codec/   #   ZipNN 格式核心 + scan/hash/header/webp（+ fuzz/）
│  ├─ crates/mm-core/     #   PyO3 abi3 繫結（mm_core 模組）
│  └─ native-bin/         #   按平台 tag 存放的預建置二進位（提交於 main）
├─ src/                   # Vue 3 前端
│  ├─ components/         #   應用元件 + ui/（reka-ui 封裝）
│  ├─ hooks/              #   store、models、download、zipnn、upload、config 等
│  ├─ utils/ · types/ · locales/
│  ├─ style.css           #   Tailwind v4 入口 + 設計權杖
│  └─ main.ts             #   註冊為 ComfyUI 擴充套件
├─ scripts/               # native 建置 + 官方 zipnn 交叉驗證 + 前端效能關卡
├─ tests/                 # pytest 套件：golden 契約、parity、接合部
└─ web/                   # 提供給 ComfyUI 的預建置打包產物（已提交）
```

---

<a id="credits"></a>

## <img src="https://api.iconify.design/lucide/heart-handshake.svg?color=%23ec4899" width="34" height="34" align="middle" alt=""> 致謝與歸屬

ComfyUI‑Model‑Manager‑Neo 之所以存在，只因為
**[hayden‑cn](https://github.com/hayden-cn)** 的
**[`ComfyUI-Model-Manager`](https://github.com/hayden-cn/ComfyUI-Model-Manager)**
先存在。這個 fork 中的每一個結構性想法 —— 模型資料夾抽象、帶 websocket
進度協議的可恢復下載任務系統、Civitai 與 Hugging Face 頁面解析器、把
卡片拖到節點圖上的整合、模型編輯器的表單管線，乃至卡片尺寸預設這樣的
小細節 —— 都是 hayden‑cn 的設計。Neo 改變的是外表、相依與大量 bug；
它不必重新發明軀體。閱讀原版仍然是理解_這個程式碼庫為何是現在這個形狀_
的最快途徑，而對架構的誠實歸屬是：**他們的**。

壓縮引擎實現了 **[ZipNN](https://github.com/zipnn/zipnn)** 專案（MIT）的
格式 —— Hershcovitch 等人，_“ZipNN: Lossless Compression for AI Models”_
（[arXiv:2411.05239](https://arxiv.org/abs/2411.05239)）—— 熵編碼遵循
zstd huff0/FSE 規範（RFC 8878）與 FiniteStateEntropy（BSD‑2‑Clause）。
原生核心的完整第三方歸屬見 [`native/NOTICE`](native/NOTICE)。

本 fork 是依據 **GNU General Public License v3.0** 使用與修改的衍生
作品。Neo 中的修改（UI 重建、PrimeVue 移除、Rust 原生核心、ZipNN
壓縮、Hugging Face / ModelScope 樞紐整合、多 hub 搜尋與雜湊識別、包現代化、工具鏈、
可靠性與安全性加固、批次掃描移除、日語本地化 —— 逐條見
[與原版相比改變了什麼](#what-changed)）以相同的 GPL‑3.0 授權提供。
按授權要求，原版版權宣告與授權全文保留在 [`LICENSE`](LICENSE) 中。

### <img src="https://api.iconify.design/logos/qwen-icon.svg" width="26" height="26" align="middle" alt=""> Built with Qwen Studio

本 fork 的很大一部分是在與 **[Qwen Studio]** 的緊密協作中完成的：玻璃
擬態 UI 重建、Rust 原生核心、ZipNN 壓縮引擎、hub 上傳流程、可靠性與
安全性加固，以及大量除錯工作。

建置過程中使用了這些優秀專案：[reka-ui]、[Tailwind CSS]、[Lucide]、
[VueUse]、[es-toolkit]、[vue-sonner]、[huggingface_hub]、[hf_xet]、
[modelscope_hub]、[ZipNN]、[zenwebp]。

---

<a id="security"></a>

## <img src="https://api.iconify.design/lucide/shield-check.svg?color=%2322c55e" width="34" height="34" align="middle" alt=""> 安全

Neo 接受持續而非偶發的掃描。每次 push 與拉取請求都會執行：針對 OSV
資料庫的相依審計（涵蓋全部四個鎖定檔）、由 CodeQL 對 TypeScript/Vue、
Python 與 Rust 原始碼以及 CI 設定本身進行的靜態分析、涵蓋完整 git 歷史的
金鑰掃描，以及針對 GitHub 工作流程的專項加固檢查；Rust 核心還會每週在七個
目標上進行模糊測試。所有接受的風險都附有書面理由 —— 沒有任何問題會被
悄悄掩蓋。如果你發現漏洞，請私下回報：[`SECURITY.md`](SECURITY.md)。

---

<a id="license"></a>

## <img src="https://api.iconify.design/lucide/scale.svg?color=%2394a3b8" width="34" height="34" align="middle" alt=""> 授權

**GPL‑3.0‑only** —— 全文見 [`LICENSE`](LICENSE)。

Rust 原生核心（[`native/`](native/)）還為預覽 WebP 管線額外連結
**[zenwebp]** —— 純 Rust WebP 編解碼器，**AGPL‑3.0‑only** 或 Imazen
商業雙許可。Neo 為 GPL‑3.0‑only，並在 **AGPL‑3.0** 條款下使用 zenwebp
（AGPLv3 §13 明確允許 AGPL 作品與 GPLv3 作品結合，AGPL 部分保持
AGPL）。ComfyUI 是**本地**應用而非網路服務，因此 AGPL 的網路條款在此
實質上不發生作用；分發時的原始碼可得義務由本公開儲存庫滿足。原生核心的
完整第三方歸屬：[`native/NOTICE`](native/NOTICE)。

<div align="center">

**如果 Neo 為你節省了時間，請考慮給儲存庫點個星 <img src="https://api.iconify.design/lucide/star.svg?color=%23eab308" width="19" height="19" align="middle" alt="">，並感謝
[原作者](https://github.com/hayden-cn/ComfyUI-Model-Manager)。**

</div>

<!-- Link references -->

[reka-ui]: https://reka-ui.com
[Tailwind CSS]: https://tailwindcss.com
[Lucide]: https://lucide.dev
[VueUse]: https://vueuse.org
[es-toolkit]: https://es-toolkit.dev
[vue-sonner]: https://vue-sonner.vercel.app
[huggingface_hub]: https://github.com/huggingface/huggingface_hub
[hf_xet]: https://github.com/huggingface/xet-core
[modelscope_hub]: https://github.com/modelscope/modelscope_hub
[ZipNN]: https://github.com/zipnn/zipnn
[zenwebp]: https://github.com/imazen/zenwebp
[uv]: https://docs.astral.sh/uv/
[Qwen Studio]: https://chat.qwen.ai/
[ComfyUI-Manager]: https://github.com/ltdrdata/ComfyUI-Manager
