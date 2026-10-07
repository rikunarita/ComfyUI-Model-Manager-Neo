> [!CAUTION]
> **本项目仍在积极开发中，目前不推荐一般使用。**可能出现意料之外的
> bug；由于功能正在陆续添加，部分成果物可能是半成品。界面今后也可能
> 继续变化。话虽如此，我们非常欢迎反馈问题与提交 issue。

<div align="center">

# <img src="https://api.iconify.design/lucide/boxes.svg?color=%236366f1" width="41" height="41" align="middle" alt=""> ComfyUI‑Model‑Manager‑Neo

### 浏览 · 下载 · 上传 · 拖放 —— 优雅地管理你的模型。

在 **Vue 3 + Tailwind CSS v4 + reka‑ui** 之上重新构建的 ComfyUI 模型管理器，
采用现代玻璃拟态界面重新设计；包括 ZipNN 压缩引擎在内的所有热点路径，
均由**预构建的纯 Rust 核心**执行。

![Version](https://img.shields.io/badge/version-0.3.1-6366f1.svg)
![License](https://img.shields.io/badge/License-GPL--3.0--only-blue.svg)
![ComfyUI](https://img.shields.io/badge/ComfyUI-Custom%20Node-8A8B98.svg)
![CI](https://github.com/rikunarita/ComfyUI-Model-Manager-Neo/actions/workflows/ci.yml/badge.svg?branch=main)
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
![ESLint](https://img.shields.io/badge/ESLint-10-4B32C3.svg?logo=eslint&logoColor=white)
![Prettier](https://img.shields.io/badge/Prettier-3-F7B93E.svg?logo=prettier&logoColor=black)
![Stylelint](https://img.shields.io/badge/Stylelint-17-263238.svg?logo=stylelint&logoColor=white)
![Ruff](https://img.shields.io/badge/Ruff-0.16.9-D7FF64.svg?logo=ruff&logoColor=black)
![Node](https://img.shields.io/badge/Node-26-339933.svg?logo=nodedotjs&logoColor=white)
![pnpm](https://img.shields.io/badge/pnpm-12-F69220.svg?logo=pnpm&logoColor=white)
![uv](https://img.shields.io/badge/uv-dev_%26_CI-DE5FE9.svg?logo=uv&logoColor=white)

![Linux x86_64](https://img.shields.io/badge/Linux-x86__64-FCC624.svg?logo=linux&logoColor=black)
![Linux aarch64](https://img.shields.io/badge/Linux-aarch64-FCC624.svg?logo=linux&logoColor=black)
![macOS universal2](https://img.shields.io/badge/macOS-Intel_%2B_Apple_Silicon-000000.svg?logo=apple)
![Windows x64](https://img.shields.io/badge/Windows-x64-0078D6.svg?logo=windows&logoColor=white)

[English](README.md) · [日本語](README.ja.md) · **简体中文** · [繁體中文](README.zh-TW.md)

![概览动画](demo-assets/hero.webm)

</div>

---

**目录**

- [Why Neo?](#why-neo) · [截图](#screenshots) · [安装](#installation) · [功能](#features)
- [模型搜索与多平台发现](#search) · [ZipNN 无损压缩](#zipnn) · [与原版相比改变了什么](#what-changed) · [被移除的功能：批量扫描](#removed-feature) · [被移除的功能：复制节点](#removed-feature-copy-node)
- [文档](#documentation) · [开发](#development) · [致谢与归属](#credits) · [许可证](#license)

---

<a id="why-neo"></a>

## <img src="https://api.iconify.design/lucide/sparkles.svg?color=%23f59e0b" width="34" height="34" align="middle" alt=""> Why Neo?

**ComfyUI‑Model‑Manager‑Neo** 继承了优秀的原版管理器，并从零开始重建了
整个使用体验：

**1. Neo 新增**

- <img src="https://api.iconify.design/lucide/cpu.svg?color=%23f59e0b" width="19" height="19" align="middle" alt=""> **Rust 原生核心** —— 模型库扫描、哈希、safetensors 头部解析、张量树、
  文件夹监视、预览 WebP 编解码以及整个 ZipNN 引擎，都运行在仓库内附带的
  **预构建 Rust 扩展**中：四个平台 × 两种 Stable ABI 风味（GIL 构建用 abi3 =
  CPython 3.12 及以上，自由线程构建用 abi3t = CPython 3.15 及以上、PEP 803），
  各一个二进制。核心本身只需一次普通的 `import` 即可加载 ——
  **不需要编译器、不需要 pip 包、不需要下载**（扩展的四个 Python hub 依赖
  仍会在首次启动时自动安装）。与纯 Python 原版的实测对比：5,000 个模型的
  库扫描冷启动快约 **7.5 倍**（热态低于 100 ms）、五种哈希记法**一遍**算完、
  65,000 张量的 MoE 张量树构建快约 **100 倍**、ZipNN 压缩无论模型多大
  **峰值内存都低于 1 GB**（证据见 [`docs/BENCH.md`](docs/BENCH.md)）。
- <img src="https://api.iconify.design/lucide/shield-check.svg?color=%2322c55e" width="19" height="19" align="middle" alt=""> **经过验证的内存安全压缩** —— Rust 引擎通过 lint 禁止 `unsafe` 代码：
  格式核心完全不含 `unsafe`，唯一需要它的边界（只读内存映射）经过了安全
  评审并有文档记录。引擎还由七个持续 fuzz 目标加固，每次还原都会与压缩时
  记录的 SHA‑256 校验。与官方 `zipnn` 0.5.4 包的格式兼容性是一项 CI 关卡，
  每次 push 都会双向交叉验证。
- <img src="https://api.iconify.design/lucide/package-plus.svg?color=%23f59e0b" width="19" height="19" align="middle" alt=""> **ZipNN 无损压缩** —— 就地压缩与解压 safetensors 模型（`.znn.safetensors`）、
  将整个文件夹批量打包为密封的 `<name>_DeltaZNN` 包、把微调模型相对其
  基础模型缩小为极小的**差分文件**。
- <img src="https://api.iconify.design/lucide/upload-cloud.svg?color=%23f59e0b" width="19" height="19" align="middle" alt=""> **上传到 Hugging Face / ModelScope** —— 把任意本地模型直接发布到 Hugging Face
  或 ModelScope 仓库（需要时自动创建仓库，可选私有、附带相关资产并显示
  实时进度）。ModelScope 支持——下载、上传、搜索与认证——为 Neo 全新集成。
- <img src="https://api.iconify.design/lucide/radar.svg?color=%23f59e0b" width="19" height="19" align="middle" alt=""> **多 hub 搜索与哈希识别** —— 在同一个输入框中并行搜索 Hugging Face、
  ModelScope 与 Civitai，并能用哈希把任意本地文件反查到 Civitai 目录。
- <img src="https://api.iconify.design/lucide/list-checks.svg?color=%23f59e0b" width="19" height="19" align="middle" alt=""> **多选** —— 勾选模型与文件夹卡片，一次性加入工作流或删除。
- <img src="https://api.iconify.design/lucide/star.svg?color=%23eab308" width="19" height="19" align="middle" alt=""> **星标** —— 每张卡片都有星标开关；加星的条目永远排在最前。
- <img src="https://api.iconify.design/lucide/folder-plus.svg?color=%2322c55e" width="19" height="19" align="middle" alt=""> **创建文件夹** —— 文件夹视图中的「添加文件夹」按钮。
- <img src="https://api.iconify.design/lucide/link.svg?color=%23f59e0b" width="19" height="19" align="middle" alt=""> **直链下载** —— 粘贴原始 `.safetensors` / `.ckpt` / `.gguf` URL，选择目标
  文件夹，还可选自定义子文件夹。
- <img src="https://api.iconify.design/lucide/zap.svg?color=%23f59e0b" width="19" height="19" align="middle" alt=""> **`hf_xet` 加速** —— Hugging Face 传输在可用时使用分块、去重的 Xet 协议。
- <img src="https://api.iconify.design/lucide/languages.svg?color=%23f59e0b" width="19" height="19" align="middle" alt=""> **日语与繁體中文语言包** —— 在 English 与简体中文之外，新增完整的日语
  与繁體中文（zh-TW）语言包。界面语言跟随 ComfyUI 自身的设置；地区子标签
  （`ja-JP` 等）折叠到其基础语言，Hant 文字系统标签（`zh-Hant`、
  `zh-Hant-TW` 等）选择繁體中文包。

**2. 刷新与增强**

- <img src="https://api.iconify.design/lucide/layers.svg?color=%23f59e0b" width="19" height="19" align="middle" alt=""> **玻璃拟态 UI** —— 半透明、带模糊与层次感的界面，自动跟随 ComfyUI 自身的
  浅色/深色配色。
- <img src="https://api.iconify.design/lucide/puzzle.svg?color=%23f59e0b" width="19" height="19" align="middle" alt=""> **Reka-UI 全面刷新** —— PrimeVue 依赖已替换为轻量、无样式的 **[reka-ui]**
  原语、**Tailwind CSS v4** 与 **[Lucide]** 图标：一套读得懂、改得动的
  shadcn‑vue 风格组件。
- <img src="https://api.iconify.design/lucide/workflow.svg?color=%23f59e0b" width="19" height="19" align="middle" alt=""> **一流的节点图集成** —— 把模型拖到画布上即可生成或填充节点，把 embedding
  拖进文本区，加载预览图中内嵌的工作流。
- <img src="https://api.iconify.design/lucide/monitor-smartphone.svg?color=%23f59e0b" width="19" height="19" align="middle" alt=""> **响应式** —— 面向桌面、移动与多屏环境设计。
- <img src="https://api.iconify.design/lucide/wrench.svg?color=%23f59e0b" width="19" height="19" align="middle" alt=""> **现代工具链** —— Vite 8（Rolldown）、TypeScript 6、ESLint 10 flat config、
  Prettier、Stylelint、Ruff、clippy、husky + lint‑staged。确定性的、
  lint 零警告的构建。

> [!NOTE]
> Neo 是 [`hayden-cn/ComfyUI-Model-Manager`](https://github.com/hayden-cn/ComfyUI-Model-Manager)
> 的 **fork**，以相同的 **GPL‑3.0** 许可证分发。原版架构的全部功劳属于其
> 作者 —— 见[致谢](#credits)。

---

<a id="screenshots"></a>

## <img src="https://api.iconify.design/lucide/camera.svg?color=%238b5cf6" width="34" height="34" align="middle" alt=""> 截图

### 1. 平铺「模型」视图 —— 搜索、排序与网格大小调整

![平铺模型网格](demo-assets/view-flat.avif)

**平铺**布局下的管理器窗口：玻璃质感模型卡片组成的网格（带预览、类型与
大小标签）、搜索栏，以及类型 / 排序 / 卡片尺寸选择器。

### 2. 文件夹（资源管理器）视图 —— 浏览目录树

![文件夹资源管理器视图](demo-assets/view-folders.avif)

**文件夹**布局的第一层，带面包屑路径，以及指针停留时会轻轻浮起的淡绿松石
玻璃文件夹卡片。

### 3. 模型详情、编辑与 Hugging Face 上传

|                                                                   |                                                                           |
| ----------------------------------------------------------------- | ------------------------------------------------------------------------- |
| ![模型信息](demo-assets/model-info.avif)                          | ![编辑模式](demo-assets/model-edit.avif)                                  |
| _模型信息：预览、基础信息表、Description 与 Information 标签页。_ | _编辑模式：类型下拉框、文件夹选择按钮、接受 `folder/name` 前缀的文件名。_ |

|                                                                  |                                                                               |
| ---------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| ![Hugging Face 上传](demo-assets/hf-upload.avif)                 | ![日语界面](demo-assets/ja-model-info.avif)                                   |
| _上传到 Hugging Face 的第 3 步：仓库 ID、创建时私有、目标路径。_ | _同一窗口的**日语**界面 —— 内置完整的 English / 中文（简繁）/ 日本語语言包。_ |

### 4. 模型名搜索与 safetensors 张量树

|                                                                                                |                                                                                          |
| ---------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| ![多平台搜索](demo-assets/search-columns.avif)                                                 | ![张量树](demo-assets/tensor-tree.avif)                                                  |
| _一次查询、三个 hub：Hugging Face / ModelScope / Civitai 三列结果，带头像、下载数与深度链接。_ | _Information 标签页以可折叠的文件夹树渲染 safetensors 头部（Hugging Face 查看器风格）。_ |

10 秒导览见 [`demo-assets/hero.webm`](demo-assets/hero.webm)。

---

<a id="installation"></a>

## <img src="https://api.iconify.design/lucide/rocket.svg?color=%2322c55e" width="34" height="34" align="middle" alt=""> 安装

Neo 作为 ComfyUI 自定义节点运行。任选一种方式：

**1 · Git clone（推荐，便于更新）**

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/rikunarita/ComfyUI-Model-Manager-Neo.git
```

**2 · 手动下载**

下载
[仓库压缩包](https://github.com/rikunarita/ComfyUI-Model-Manager-Neo/archive/refs/heads/main.zip)，
解压到 `ComfyUI/custom_nodes/`，并确认文件夹名为
`ComfyUI-Model-Manager-Neo`。

**3 · ComfyUI Registry（ComfyUI Manager / CLI）**

Neo 已发布在 ComfyUI registry 上，节点名为
[`comfyui-model-manager-neo`](https://registry.comfy.org/publishers/rikunarita7669/nodes/comfyui-model-manager-neo)：
在 [ComfyUI-Manager] 中搜索 **“ComfyUI‑Model‑Manager‑Neo”**，或使用官方
命令行安装：

```bash
comfy node install comfyui-model-manager-neo
```

然后**重启 ComfyUI**。Python 依赖（`huggingface_hub`、`hf_xet`、
`modelscope_hub`、`markdownify`）会在首次启动时自动安装。Web 打包产物
预构建于 [`web/`](web)，Rust 核心预构建于
[`native/native-bin/`](native/native-bin)，因此_运行_本扩展既不需要
Node.js 也不需要编译器 —— 一次普通的 `import` 即可加载核心（平台覆盖
见[引擎表](#the-engine-a-prebuilt-pure-rust-core)）。

通过顶栏的 **「Model Manager Neo」** 按钮、侧边栏、
`Extensions → Model Manager Neo` 菜单或命令面板打开管理器。

---

<a id="features"></a>

## <img src="https://api.iconify.design/lucide/list-checks.svg?color=%233b82f6" width="34" height="34" align="middle" alt=""> 功能

<details open>
<summary><b>浏览与整理</b></summary>

- 两种布局：**平铺**网格（默认视图）与**文件夹**资源管理器，随时切换。
- 实时搜索（支持 `*` 通配符与多词元「AND」匹配）。
- 按名称、大小、创建日期、修改日期或**最近使用**排序（打开模型或将其
  加入节点图即记录一次使用）。
- 卡片尺寸可调（预设加完全自定义尺寸）。
- 无需重启即可切换隐藏文件（以 `.` 开头）的显示。
- 图片**与视频**预览（任意预览可在全屏**灯箱**中放大）、悬停时开合动画的
  悬停时轻轻浮动的淡绿松石玻璃文件夹图案，以及玻璃质感的无预览占位图。
- 类型根文件夹卡片带有**该类型的合计大小**（轻量容量看板）；记录的
  SHA256 与库中其他文件一致的模型，会在详情窗口中显示红色**重复警告**。
- 存放在类型根目录之下的模型，会在名称上方显示其**子目录**（两种布局
  一致）。
- **智能收藏** —— 把平铺视图当前的搜索与类型筛选保存为具名收藏（按用户
  持久化），一键重新应用；全部收纳在一个胶囊按钮中：软盘部分打开保存
  对话框，其余部分打开应用/切换菜单。
- **卫生扫描** —— 纯本地清查（不联网、不算哈希）：孤立的预览与笔记、
  没有预览的模型、空文件夹，并可通过惯常的确认对话框批量清理。
- **可选的文件夹监视** —— 默认关闭的原生监视启用后，当其他程序增删
  模型时，受影响的列表约 1.5 秒内刷新。

</details>

<details>
<summary><b>节点图集成</b></summary>

- 将模型缩略图拖到画布上以**添加加载器节点**。
- 拖到已有节点上以**填充匹配的输入**（存在歧义时精确匹配）。
- 将 **embedding** 拖到文本区以追加 `(embedding:name:1.0)`。
- 将预览图拖到节点图上以**加载其中内嵌的工作流**。
- **添加** 按钮：把节点放置到画布。

</details>

<details>
<summary><b>下载</b></summary>

- 粘贴 **Civitai**、**Hugging Face**、**ModelScope**（`www.modelscope.ai`）
  或**直接文件** URL —— 或输入模型**名称**，并行搜索三个 hub。
- Civitai 镜像主机 `civitai.red` 上的页面 URL 与 Civitai 完全同等对待
  （保存的模型页保留粘贴时的主机名）。
- 解析单个页面的多个文件与多个版本，供你挑选。
- 直链必须显式指定目标类型，可选自定义子文件夹。
- 可选预览图 —— 保留模型页提供的**整个图集**，下载时选中的图片成为
  卡片的主预览；每次下载都附带可编辑的 Markdown 描述。
- **剩余空间保护**：对话框显示目标卷的剩余空间，声明大小放不下的任务
  会被后端拒绝。
- 暂停 / 继续 / 删除任务；进度、速度与大小实时更新。
- Hugging Face 下载使用 `huggingface_hub`（可用时加 `hf_xet`）。
- Civitai 下载在完成后做 SHA256 校验、按文件类型自动归位，并对基础模型
  不匹配与可执行载荷格式发出警告。

</details>

<details>
<summary><b>上传</b></summary>

- **从本地文件**上传到任意模型文件夹（在下载列表中以带进度的实时任务
  登记）。
- **上传到 Hugging Face 或 ModelScope**：在向导第一步选择平台；用对应
  令牌认证；仓库不存在时自动创建（可选公开/私有）；选择目标路径并查看
  实时进度。ModelScope 始终使用国际站 `www.modelscope.ai` 域名。
- 可选的**相关资产**开关会把每个 `<模型名>.*` 伴随文件（预览图、Markdown
  笔记）一并上传到模型所在的仓库目录 —— 笔记还可以作为仓库的
  `README.md` 提交。
- 选中的**文件夹**可批量上传（内部所有模型，保留子文件夹结构），入口在
  文件夹视图的选择栏。

</details>

<details>
<summary><b>模型信息与维护</b></summary>

- 在只读的 **Information** 表中查看模型的全部记录信息：笔记 YAML
  front‑matter 解析出的作者、基础模型、全部哈希（`AutoV1` …
  `SHA256_12`）、格式与精度、模型平台、模型页链接与所有预览 URL（未知
  键原样列在末尾）；没有笔记的模型则显示 safetensors 的 `__metadata__`
  块。
- safetensors 模型还会以可折叠的**文件夹树**显示其完整**张量布局** ——
  点分名称按段分组，每层带计数，每张量带 name / dtype / shape，风格与
  Hugging Face 查看器一致。张量树由 Rust 核心预先分组，因此 65,000 张量
  的 MoE 头部也能即时打开。
- 重命名、在文件夹或类型之间移动，或**永久删除**模型及其预览与笔记；
  在有未保存更改时取消编辑会先请求确认。
- 查看、编辑并保存模型旁边的 Markdown 笔记；Information 表本身也可在
  明确警告之后编辑（保存时会重写笔记的 front‑matter）。
- 管理预览**图集**：排序、移除、添加本地图片，并选择主预览（编辑模式
  中带蓝色圆环的那张）。
- **打开模型页**按钮带有模型来源 hub（Civitai、Hugging Face 或
  ModelScope）的标志；**下载到本地**把已保存的文件以附件形式流式发送
  给浏览器。
- **按哈希识别**把本地文件反查到 Civitai 目录（先尝试已记录的哈希，
  全部落空再单遍哈希文件）。
- 一切信息都在打开模型时按需加载 —— 不存在全库扫描步骤。

</details>

<details>
<summary><b>设置与 i18n</b></summary>

- **Civitai**、**Hugging Face** 与 **ModelScope** 的 API 密钥，本地保存于
  `private.key`（并有 `CIVITAI_API_KEY` / `HF_TOKEN` /
  `MODELSCOPE_API_TOKEN` 环境变量回退）。旧版本保存在 ComfyUI 用户设置
  中的密钥会在首次运行时自动迁移。
- 从模型列表中排除指定类型；包含或排除隐藏文件。
- **监视模型文件夹的外部更改**（默认关闭；网络挂载自动跳过）。
- ZipNN 自动化：自动压缩 N 天未使用的模型、下载完成后自动压缩、prompt
  执行期间暂停下载。
- 内置完整的 **English**、**中文**（简体与繁體）与 **日本語**；地区子标签
  （`ja-JP` 等）折叠到其基础语言，Hant 文字系统标签选择繁體中文包。

</details>

---

<a id="search"></a>

## <img src="https://api.iconify.design/lucide/search.svg?color=%2314b8a6" width="34" height="34" align="middle" alt=""> 模型搜索与多平台发现

**创建下载任务**窗口不仅接受页面 URL：任何**不以** `https://` 开头的输入
都会被当作模型名查询，在三个平台上并行搜索 —— **Hugging Face**（左列）、
**ModelScope**（中列）、**Civitai**（右列）。输入时搜索模式与 URL 模式
实时切换；结果经短暂防抖后刷新；每一列各自报告自己的错误，不会让整次
搜索失败。

- 每条结果都显示发布用户/组织的**头像**（hub 未提供头像时显示首字母
  徽章）以及累计下载数。
- 模型 id 拆成两个深度链接：**所有者名**打开用户/组织页，**仓库名**打开
  模型页；点击行内其他位置则把该模型直接解析进下载编辑器。
- 支持纯 **`username/repo-name`** 输入，且**一次 Enter 总能解析**：先取
  结果中的精确匹配，再把裸仓库 id 当作 Hugging Face 仓库，最后取第一个
  非空列的首行；若还没有结果，Enter 立即执行名称搜索。
- 每一列都支持翻页：滚动到底部时，只要存在下一页就会出现
  **「∨ 显示更多」**按钮。
- 各平台的隐藏与**排序方式**可在 **设置 → Model Manager Neo → 搜索** 中
  选择（默认为 Hugging Face 趋势、ModelScope 点赞、Civitai 评分最高）。

Civitai 下载还带有官方 CLI 普及的安全网，并适配到管理器的任务系统：

- **下载计划（dry run）** —— 开始前，编辑器显示解析后的目标路径、声明
  大小、公开 SHA256 以及平台 API 密钥是否已配置。
- **SHA256 校验** —— 完成的 Civitai 下载会与公开 SHA256 比对；不匹配则
  删除文件并让任务失败。
- **布局归位** —— 版本文件自身的类型若映射到别的模型文件夹（如随附的
  VAE），则归入那个文件夹而非当前选中的文件夹。
- **基础模型警告** —— 当版本的基础模型与目标文件夹库中已记录的基础
  模型不符时提示。
- **可执行格式警告** —— pickle 与归档载荷在加载时可能执行代码；编辑器
  会在下载前明确告知。
- **Hub 账户（whoami）** —— 对每个已配置密钥的平台，下载对话框显示已
  连接的账户；401 失败时会准确说明在哪里创建密钥、如何继续。

放大 Civitai 来源模型的预览时，灯箱左侧显示图片、右侧显示解析出的
**生成元数据**（提示词、负面提示词、采样器、步数、CFG scale、种子、
clip skip、尺寸、基础模型与资源配方）。

模型详情窗口的**按哈希识别**向 Civitai 目录询问某个本地文件是哪个模型
版本：先尝试 Markdown 伴随文件中已记录的哈希，全部落空才对文件做单遍
哈希（`SHA256` / `AutoV2` / `AutoV1` / `CRC32`，外加 `BLAKE3`）。命中时
打开解析出的模型与版本，附带基础模型、触发词、文件列表以及官方 CLI
会打印的同一条 `civitai download` 命令；未命中则报告找不到匹配的模型
版本。

---

<a id="zipnn"></a>

## <img src="https://api.iconify.design/lucide/package-plus.svg?color=%230ea5e9" width="34" height="34" align="middle" alt=""> ZipNN 无损压缩

大型 `.safetensors` 检查点很快就会吃满磁盘。Neo 以
[ZipNN](https://github.com/zipnn/zipnn) 格式**就地、无损**地压缩与解压
它们 —— 与官方 ZipNN 项目相同的张量感知方案 —— 由 Neo 的**纯 Rust
核心**执行，并在 CI 中与官方 `zipnn` 0.5.4 包双向交叉验证，因此产物与
更广泛的 ZipNN 生态保持可互换。

### 1. 工作原理

模型权重绝大部分是浮点数，而浮点数绝大部分是_冗余_的：表现良好的权重
张量中，指数字节会反复出现。ZipNN 正是利用这一点。对每张量：

- 将值**拆分**为字节平面，并重排符号 / 指数 / 尾数比特，使相似字节聚集
  在一起，然后
- 用 FiniteStateEntropy（FSE）编解码器对每个平面做 **Huffman 编码**。

非浮点张量（整数索引、掩码等）在官方配方中会原样穿过 —— **Neo 的 Rust
核心则同样压缩它们**（覆盖全部 safetensors dtype，分两个互操作带；见下方
[dtype 覆盖与互操作矩阵](#dtype-coverage--the-interoperability-matrix)）——
而压缩后实际不会变小的张量则**原样保留**。每张被压缩的张量以 `uint8`
向量存储，文件在单条 `znn_compressed_vectors` 元数据中记录它们各自的
原始 `dtype` 与 `shape`。不做任何近似或丢弃 —— 解压**逐比特**复原原始
文件。

压缩后的模型写在原件旁边，命名为 `<name>.znn.safetensors` —— 正是官方
ZipNN 工具（以及打过 `zipnn_safetensors()` 补丁的加载器）所期望的后缀，
因此打过补丁的 ComfyUI 加载器可以透明地读取 Neo 压缩的模型。真实的
检查点通常能压到原大小的 **60–80 %**（随机性强的数据压缩率低得多；
低熵权重则压缩得更多）。

<a id="dtype-coverage--the-interoperability-matrix"></a>

### 2. dtype 覆盖与互操作矩阵

Rust 核心以两个互操作带压缩 **safetensors 0.8 定义的全部 22 种 dtype**。
压缩文件所属的带记录在元数据中（扩展带为 `znn_neo_extended="1"`），并
在界面中呈现：Information 标签页的 **Neo Extended** 徽章、dtype 明细行
（`bfloat16×412, uint8×3, …`），以及压缩确认框中事先的明确提示。

| 张量 dtype                                                                                                                      | ZipNN dtype 码    | 官方 ZipNN 0.5.4 工具的行为                                     |
| ------------------------------------------------------------------------------------------------------------------------------- | ----------------- | --------------------------------------------------------------- |
| `F32` `F16` `BF16` `F8_E4M3` `F8_E5M2`                                                                                          | 1–30（上游带）    | **原样解码 Neo 的文件**                                         |
| `F64` `C64` `I8` `U8` `BOOL` `I16` `U16` `I32` `U32` `I64` `U64` `F8_E4M3FNUZ` `F8_E5M2FNUZ` `F8_E8M0` `F4` `F6_E2M3` `F6_E3M2` | 128–146（Neo 带） | **以明确错误拒绝** —— 绝不静默损坏（已在 CI 中针对 pip 版实证） |

值得了解的细节：

- 官方解码器对所有未实现的 dtype 码都会以
  `ValueError: Unsupported Dtype N` 拒绝 —— Neo 扩展文件在原理上就不可能
  被上游工具误解码；在 Neo 内部则与其他文件一样以 SHA‑256 校验逐字节
  还原；
- `complex64` 使用 Neo 带（码 130）：官方 0.5.4 解码器没有保留码 9 的
  分支，会像拒绝 Neo 码一样拒绝它（已在 CI 中用测试实证），因此不存在
  需要兼容的对象；
- 高位字节全为零的整数张量（`< 65536` 的 `int32` 索引、掩码、缩放表等）
  还会使用**截断模式**：全零字节平面整体从载荷中丢弃 —— 由于压缩器只
  丢弃它在整张量范围内验证过为零的平面，这在构造上就是无损的；
- `complex128` 与 `bcomplex32` 只存在于 codec 层（码 129/131），没有
  safetensors 表示 —— 任何 `.safetensors` 文件都承载不了它们。

### 3. 使用方法

打开任意 `.safetensors` 模型。在预览与信息表之间的空隙里，就是
**ZipNN 图案本身构成的按钮** —— 随附 SVG 自带玻璃底板（含深色模式
变体），悬停时上浮变亮，并通过工具提示与屏幕阅读器自我说明。按下后：

1. 弹出刻意_不_使用「Danger」样式的确认框（压缩可逆，且在压缩文件完全
   写入并校验通过之前绝不删除原件）；
2. 按钮替换为**实时进度条**，Rust 核心流式处理文件（内存映射、释放
   GIL —— ComfyUI 其余部分保持响应），任务可随时取消；
3. 成功后原件替换为 `<name>.znn.safetensors` —— 预览与 Markdown 笔记
   跟随改名，网格自动刷新。

打开**已压缩**模型时，同一图案以**反色**显示，动作翻转为_解压_，同样
经过确认框，还原出普通 `.safetensors`。信息表也会变化：单行_文件大小_
替换为**原始文件大小**、**压缩后文件大小**与**占原始大小百分比** ——
压缩前的大小在压缩时已记录在文件元数据中，因此明细在改名后依然保留
（官方 ZipNN CLI 压缩的文件不写该键，故仍显示普通的_文件大小_行）。

同一图案还出现在**每张模型与文件夹卡片的右上角**（星标开关旁）：一键
即可压缩（或反色解压），无需打开模型，确认框完全相同。任何任务运行
期间 —— 单个、批量或差分 —— 按钮显示**环形进度圈**（批量时带百分比）。

### 4. 批量压缩（整个文件夹）

选中文件夹（「Select files」）后按下**底部栏的 ZipNN 图案按钮** —— 或
使用文件夹卡片右上角的按钮 —— 文件夹树内所有 `.safetensors` 模型都会
被压缩（预览与笔记跟随各自的模型），并**移入打包文件夹
`<name>_DeltaZNN`**；原文件夹清空后消失。已经就地压缩的模型（单模型按钮、自动压缩或旧版本产物）
不会被重新压缩，而是原样移入打包文件夹 —— 不会有已压缩文件残留在其旁。
`*_DeltaZNN` 打包文件夹是密封的：

- 其中只能存放 ZipNN 内容（`*.znn.*` 模型、`*.znn` 差分文件）；普通
  模型的上传、下载与移入都会被拒绝；
- 打包文件夹与普通文件夹不能同时选中 —— 勾选其中一类时，另一类会带
  警告通知自动取消选中；
- 打包文件夹的 ZipNN 按钮是**反色**的；按下即**批量解压**整个打包文件
  夹，把全部内容移回以其命名的文件夹（清空的打包文件夹被删除）；
- 差分文件夹（`<base>_DeltaZNN`，见下文）也是打包文件夹：其反色按钮
  一次性还原其中每个微调模型；
- 模型**类型根文件夹**（`checkpoints` 等）的打包文件夹建在**自己内部**
  （`<root>_DeltaZNN`）—— 类型根的兄弟目录会落在 ComfyUI 文件夹映射
  之外，从加载器与管理器中都会消失；方向自动检测：存在普通模型时
  压缩，只剩打包文件夹时解压；
- 旧版本创建的打包文件夹（`<name>_ZNN`）仍能被识别并解压回原名。

多个文件夹按队列执行：一次确认、逐次任务、同一时间只有一个进度状态。

### 5. 差分压缩（微调相对基础模型）

微调模型与它的基础模型共享大部分字节，ZipNN 可以只保存**差异**：恰好
选中两个普通 `.safetensors` 模型，按下底部栏的 **ZipNN 差分压缩**。小
对话框让你选择哪一个是**基础**、哪一个是**微调**（两者可以带不同的
元数据）。结果 —— 通常只有微调模型大小的百分之几 —— 写入
**`<base>_DeltaZNN/<ft>_delta_<base>.znn`**，冗余的微调文件被删除。
解压差分（其卡片按钮，反色图案）会把微调模型**逐字节精确**还原到基础
模型旁边，并撤走清空的差分文件夹。还原需要基础模型仍在，且差分文件
记录了微调模型自身的 SHA‑256，因此还原全程可验证。

差分文件以官方 ZipNN 的 **streaming 容器**格式写出：官方 `zipnn` 包
（字节差分模式）可以逐字节精确地还原它们，反过来 Neo 也能还原官方工具
生成的差分（单容器与 streaming 两种形式）—— 两个方向都包含在 CI 交叉
验证中。此外，`.znn` 会注册进 ComfyUI 的支持模型扩展名列表（与原版
实验性的 `.gguf` 一样），因此差分文件会作为受管理的模型出现在网格中，
可以直接从界面还原。

### <a id="the-engine-a-prebuilt-pure-rust-core"></a>6. 引擎：预构建的纯 Rust 核心

压缩器并非对官方 Python 包的封装，而是 Neo 自研的纯 Rust 引擎在运行该
格式：上游 C 扩展在 PyPI 上没有 Linux wheel（`pip install zipnn` 需要
从源码编译），Neo 把这份编译完全移出你的机器。格式被移植到 Rust
（[`native/crates/znn-codec`](native/crates/znn-codec)：格式核心无
`unsafe` 代码、七个持续 fuzz 目标、与原始 C 实现字节一致的差分记录），
并以**预构建 abi3 / abi3t 二进制**形式随仓库分发 —— 每个平台 × 每种
Stable ABI 风味一个，仅靠 `import` 加载：

| 平台                            | 产物                                            | 要求                                                |
| ------------------------------- | ----------------------------------------------- | --------------------------------------------------- |
| Linux x86_64                    | `native-bin/linux-x86_64/mm_core.abi3.so`       | glibc ≥ 2.28（Debian 10 / Ubuntu 20.04+）           |
| Linux aarch64                   | `native-bin/linux-aarch64/mm_core.abi3.so`      | glibc ≥ 2.28                                        |
| macOS（Intel 与 Apple Silicon） | `native-bin/macos-universal2/mm_core.abi3.so`   | 单个 fat 二进制 —— Intel 10.12+ / Apple Silicon 11+ |
| Windows x86_64                  | `native-bin/windows-x86_64/mm_core.pyd`         | MSVC 构建                                           |
| Linux x86_64（自由线程）        | `native-bin/linux-x86_64t/mm_core.abi3t.so`     | glibc ≥ 2.28，自由线程 CPython 3.15+                |
| Linux aarch64（自由线程）       | `native-bin/linux-aarch64t/mm_core.abi3t.so`    | glibc ≥ 2.28，自由线程 CPython 3.15+                |
| macOS（自由线程）               | `native-bin/macos-universal2t/mm_core.abi3t.so` | 单个 fat 二进制，自由线程 CPython 3.15+             |
| Windows x86_64（自由线程）      | `native-bin/windows-x86_64t/mm_core.pyd`        | MSVC 构建，自由线程 CPython 3.15+                   |

每个平台的一个二进制即可服务 **CPython 3.12 及以上**所有版本（Stable
ABI、`abi3-py312` —— 已在 CI 中针对 3.12 与 3.14 实证）；自由线程构建则由
**abi3t** 孪生产物服务（`abi3t-py315`、PEP 803 —— 已在 CI 中针对 3.15 的
GIL/自由线程两种构建实证），加载器会自动选择（自由线程解释器无法加载普通
abi3 二进制；3.15+ 的 GIL 构建继续使用普通产物）。每个二进制都受 ≤ 5 MB 的
CI 尺寸预算关卡约束（八个二进制的合计以 40 MB 参考上限管理）。linux-x86_64 与
Windows 的 GIL 二进制经过 **PGO 优化** —— Profile-Guided Optimization，每次
CI 构建都从确定性工作负载重新训练；CI A/B 实测相对未优化构建的首次运行
吞吐最高约快 10 %（[BENCH §13](docs/BENCH.md)）；abi3t 二进制现阶段以非 PGO
方式发布。

这次移植也从根源上改善了可靠性：在重写过程中，C 核心的差分路径被实证
存在一类内存安全缺陷（特定输入长度下的确定性崩溃、非整数倍块上的越界
写入）。Rust 引擎从结构上消除了这一缺陷类 —— 所有平面拆分与块运算都带
边界检查，唯一的 `unsafe` 边界（只读 mmap）也经过安全评审 —— 当年触发
崩溃的输入已被固定为回归测试。互操作不是承诺而是 CI 关卡：`integration`
工作流在每次 push 时与**官方 pip `zipnn` 0.5.4** 双向交叉验证。许可证：
格式移植归属 ZipNN（MIT）与 FiniteStateEntropy（BSD‑2‑Clause）；预览
WebP 编解码使用 zenwebp（AGPL‑3.0）—— 全文见
[`native/NOTICE`](native/NOTICE)。

在没有对应二进制的平台上（其他架构、32 位、特殊 libc），扩展仍然可以
安装：浏览、下载与哈希回退到纯 Python 路径，而 ZipNN 操作与预览重编码
会报告加载器给出的确切原因，绝不静默失败。

> [!NOTE]
> 压缩通过 mmap 流式处理文件 —— 峰值内存约等于最大单张量，而非整个
> 模型（12 GB 的检查点也能在 1 GB 以内完成压缩）。**无损且经过验证**：
> 核心在压缩时记录原件的 SHA‑256，还原时内联复核（不匹配则保留压缩
> 文件，并把产物移为 `.corrupt` 以供检查）；普通 `.safetensors` 只在
> `.znn.safetensors` 写入并通过原子改名验证之后才被删除，失败的运行会
> 清理自己的部分产物。可选的 **paranoid 模式**还会在删除原件之前再解压
> 一遍并比对。

---

<a id="what-changed"></a>

## <img src="https://api.iconify.design/lucide/git-compare.svg?color=%23a855f7" width="34" height="34" align="middle" alt=""> 与原版相比改变了什么

本节按 GPL‑3.0 许可证的要求明示 fork 的差异。比较基准为
[`hayden-cn/ComfyUI-Model-Manager`](https://github.com/hayden-cn/ComfyUI-Model-Manager)
**v2.8.5**。功能被保留并扩展；被_移除_的只有两样：PrimeVue 依赖本身，
以及批量扫描功能 —— 见[被移除的功能：批量扫描](#removed-feature)。

### <img src="https://api.iconify.design/lucide/palette.svg?color=%23d946ef" width="26" height="26" align="middle" alt=""> 界面

| 区域           | 原版                                                      | **Neo**                                                                                                                                                                                                              |
| -------------- | --------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 组件库         | PrimeVue 4                                                | **reka‑ui**（无样式）+ shadcn‑vue 风格封装                                                                                                                                                                           |
| 样式           | Tailwind CSS v3 + PrimeVue 主题                           | 带作用域 `--mm-*` 设计令牌的 **Tailwind CSS v4**                                                                                                                                                                     |
| 图标           | PrimeIcons                                                | 通过图标映射使用 **Lucide**（`@lucide/vue`）                                                                                                                                                                         |
| 观感           | 标准 PrimeVue 表面                                        | **玻璃拟态**（模糊、层次、微交互），自动深色模式                                                                                                                                                                     |
| 对话框         | PrimeVue `Dialog`/`ContextMenu`                           | reka‑ui 对话框，逐对话框尺寸/位置、拖拽移动、带锚点的右键菜单                                                                                                                                                        |
| 模型详情标签页 | Description + Metadata（原始 safetensors `__metadata__`） | Description + **Information**：解析笔记 YAML front‑matter 的只读表格（作者、基础模型、哈希、格式与精度、模型平台、模型页链接、所有预览 URL，未知键原样列出），回退为原始 `__metadata__`，外加 safetensors **张量树** |
| 语言           | English、中文                                             | English、中文（简体＋**繁體**）、**日本語**（完整语言包）                                                                                                                                                            |

### <img src="https://api.iconify.design/lucide/cpu.svg?color=%230ea5e9" width="26" height="26" align="middle" alt=""> 后端与引擎

最深层的改变在界面之下。原版为纯 Python（7 个后端模块、19 条 HTTP
路由）；Neo 成长为 16 个 Python 模块、42 条路由，并把所有热点路径移入
预构建 Rust 扩展（`native/`，基于 Stable ABI 的 PyO3 —— 见
[引擎表](#the-engine-a-prebuilt-pure-rust-core)）。纯 Python 回退只保留在
「降级回答优于报错」的地方：

| 区域             | 原版                                                                                                   | **Neo**                                                                                                                                                                                                                                                                    |
| ---------------- | ------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 模型列表         | 每次请求递归 Python `os.scandir`                                                                       | Rust 并行遍历 + 跨重启持久化的 front‑matter 索引（5,000 模型扫描冷启动约 7.5 倍、热态约 100 ms；逐条目 golden 测试）                                                                                                                                                       |
| 模型详情路由     | 头部解析跑在**事件循环上** —— 巨大 MoE 头部会冻住整个服务器                                            | 经 executor + Rust 解析；服务器保持响应                                                                                                                                                                                                                                    |
| 哈希             | 单条 `hashlib` SHA‑256 循环                                                                            | 五种记法（`SHA256`/`AutoV1`/`AutoV2`/`CRC32`/`BLAKE3`）**一遍**流式完成                                                                                                                                                                                                    |
| 下载校验         | 完成后整文件重读                                                                                       | 写入循环供给的内联摘要 —— 零额外 I/O —— 保留 Civitai SHA‑256 关卡                                                                                                                                                                                                          |
| safetensors 头部 | `comfy.utils` + `json.loads`                                                                           | 单一路由后的 Rust jiter 解析（metadata + tensors + 预分组展示树；65k 张量 MoE 树构建约快 100 倍，wire 格式与 JS 交叉核对）                                                                                                                                                 |
| ZipNN 压缩       | —                                                                                                      | 整个引擎：压缩 / 解压 / 文件夹批量 / 微调差分，mmap 流式（任何模型都低于 1 GB 内存）、SHA‑256 校验还原、协作式取消                                                                                                                                                         |
| 预览图           | PIL 重编码；动画固定到第 1 帧                                                                          | zenwebp（纯 Rust）编码/解码；动画 GIF/WebP 预览**保持动画**（帧、时长、循环数与 ICC 配置文件均保留）                                                                                                                                                                       |
| Hub 集成         | 仅 Civitai 与 Hugging Face：页面解析用阻塞 `requests`，文件经普通 HTTP URL 获取 —— 完全没有 ModelScope | **Civitai + Hugging Face + ModelScope** —— ModelScope 为全新集成（下载源、上传目标、搜索枢纽与认证）。SDK 传输（`huggingface_hub` + `hf_xet`、`modelscope_hub`）、三枢纽并行名称搜索、按枢纽存于 `private.key` 的 API 密钥（环境变量回退 + 从 ComfyUI 设置迁移）、哈希反查 |
| Hub HTTP         | 线程池 worker 内的阻塞 `requests`                                                                      | 事件循环上一条共享 `aiohttp` 会话（停滞的 CDN 再也无法按 read timeout 的 120 秒占住 worker）                                                                                                                                                                               |
| 文件夹监视       | —                                                                                                      | 可选的原生 `notify` 监视（默认关闭）：按类型约 1.5 秒刷新，跳过网络挂载，监视预算耗尽时降级到 30 秒 TTL 刷新                                                                                                                                                               |
| 模型库卫生       | —                                                                                                      | 孤立伴随文件 / 空文件夹清查与批量清理                                                                                                                                                                                                                                      |
| 上传预检         | —                                                                                                      | HF/ModelScope 上传的重复检测哈希在原生核心中执行（释放 GIL）                                                                                                                                                                                                               |

在原版之上的功能级新增 —— **完整的 ModelScope 集成**（下载源、上传目标、
搜索枢纽与认证）、上传到 Hugging Face、基于 SDK 的 Hugging Face 下载
（`huggingface_hub` + `hf_xet`；原版仅抓取普通 resolve URL）、多 hub 搜索、
哈希识别、智能收藏、星标、「最近使用」记录与排序、多选、创建文件夹、
直链下载、浏览器内「下载到本地」、剩余空间保护、Civitai 下载安全网、
图集预览、SHA256 重复警告、子目录标签与类型根目录的合计大小、全屏预览
灯箱、日语与繁体中文语言包 —— 已在[功能](#features)中描述；全部为
Neo 侧的工作。

### <img src="https://api.iconify.design/lucide/package.svg?color=%23f97316" width="26" height="26" align="middle" alt=""> 依赖包

- **移除：** `primevue`、`@primevue/themes`、`lodash`、`dayjs`、`js-yaml`
  （最后一个在原版中即已未被使用 —— YAML 工作一直由 `yaml` 承担）。
- **新增 / 替换：** `reka-ui`、`@lucide/vue`、`es-toolkit`（← lodash）、
  `date-fns`（← dayjs）、`vue-sonner`（通知）、
  `class-variance-authority`、`clsx`、`tailwind-merge`。
- **升级：** Vite 5 → **8**（Rolldown）、TypeScript 5 → **6**、Vue i18n 9 →
  **11**、markdown‑it 14 → **15**、`@vueuse/core` 11 → **15**、`yaml` 2.6 →
  **2.9**。
- **Python：** 新增 `huggingface_hub` + `hf_xet` + `modelscope_hub`（原版仅
  需要 `markdownify`）；以 asyncio 任务池取代旧线程池；以共享 aiohttp
  客户端取代所有直接阻塞的 `requests` 调用。
- **Rust：** 新增 `native/` 工作区（`znn-codec` 格式核心 + `mm-core` PyO3
  绑定），以预构建 abi3 / abi3t 二进制分发 —— 扩展本身不安装任何编译型 Python
  包。ZipNN 压缩完全由 Neo 侧实现（原版从未提供）；本 fork 在开发早期
  阶段曾随附的 vendored ZipNN C 源码及其按 CPython 版本划分的 `.so` 文件，
  在 Rust 核心就位后已全部移除。

### <img src="https://api.iconify.design/lucide/sliders-horizontal.svg?color=%2306b6d4" width="26" height="26" align="middle" alt=""> 工具栏 / 按钮职责

管理器头部被重新设计为明确的图标驱动操作：**平铺 ⇄ 文件夹布局切换**、
**卫生扫描**、**显示/隐藏隐藏文件**、**刷新**、**下载列表**，以及
**上传到 Hugging Face / ModelScope**。

### <img src="https://api.iconify.design/lucide/folder-open.svg?color=%23f59e0b" width="26" height="26" align="middle" alt=""> 玻璃资产包（文件夹图标与无预览图案）

界面使用 `assets/` 中手工制作的玻璃拟态资产包：

- **文件夹卡片**静止时显示一只玻璃文件夹；悬停时开始轻柔的 CSS 浮动
  （上下起伏），指针离开后立即恢复静止。SVG 为不含 SMIL 的纯矢量文件，
  通过 HTTP 以 ETag 和一天 max‑age 提供服务，所有卡片共享同一份缓存副本。
- **面包屑**为每一段加上小文件夹字形。
- **没有预览的模型**使用玻璃质感的 NO‑PREVIEW 图案，以矢量
  （`image/svg+xml`）形式提供，因此绝不会被栅格化。
- **模型 hub 标志**（Civitai、Hugging Face、ModelScope）作为**打开模型
  页**按钮的背景，模型来源一眼可辨。

_为什么偏偏是淡绿松石？因为这是 **Neo**。_

### <img src="https://api.iconify.design/lucide/hammer.svg?color=%2365a30d" width="26" height="26" align="middle" alt=""> 工具链

lint 与格式化流水线是一套约定俗成、配置完整的组合：前端 **ESLint 10
flat config** + **Prettier** + **Stylelint 17**，Python 后端 **Ruff** +
**mypy**，Rust 工作区 **clippy `-D warnings`** + **rustfmt**，并由
**dependency‑cruiser**（导入图关卡）与 [Fallow](https://fallow.tools)
（死代码与重复）补全。质量由五层测试金字塔保障：Rust 单元测试、golden
契约测试、**cargo‑fuzz** 目标（7 个表面、每周每目标 3 小时预算）、在
三个 OS 上针对构建产物的完整 pytest 套件，以及官方 `zipnn` 交叉验证
（见[开发](#development)）。

---

<a id="removed-feature"></a>

## <img src="https://api.iconify.design/lucide/trash-2.svg?color=%23ef4444" width="34" height="34" align="middle" alt=""> 被移除的功能：批量扫描

**「批量扫描模型信息」** 功能已被移除，因为它是冗余的：模型详情窗口
直接从 safetensors 头部读取该模型的 `__metadata__`，连同文件旁的
Markdown 笔记一起呈现；没有预览的模型在网格中直接带上随附的玻璃无
预览图案。那种遍历全库、哈希每个模型并向 Civitai 按哈希查询的做法，是
通往同一信息的第二条、慢得多的路径 —— 还附带一个模态对话框、一个
全局 store、websocket 事件、磁盘上的任务文件与它自己的设置，全都需要
维护。

比扫描活得更久的两项设置如今驱动着**模型列表**（哪些类型载入网格、
是否显示以 `.` 开头的文件），设置分类为 **Model List**。它们保留历史
的 `ModelManager.Scan.*` ID 字符串，因为这个 ID 是 ComfyUI 持久化每个
用户取值所用的键 —— 改名会让所有已安装环境保存的设置变成孤儿。

> [!NOTE]
> **放弃的内容：** 按文件哈希从 Civitai _批量回填_ 预览与描述的唯一途径。
> 信息从未获取过的模型会一直保留占位预览，直到手动设置预览/笔记
> （编辑器的图集条），或通过_创建下载任务_重新下载。读取模型信息不受
> 影响 —— 它始终按需从磁盘读取；单个模型仍可通过详情窗口的哈希反查
> 在 Civitai 目录中识别。

---

<a id="documentation"></a>

<a id="removed-feature-copy-node"></a>

## <img src="https://api.iconify.design/lucide/trash-2.svg?color=%23ef4444" width="34" height="34" align="middle" alt=""> 被移除的功能：复制节点到剪贴板

**"复制节点到剪贴板"**按钮（模型详情操作行与卡片悬停列均已移除）已删除：
把半配置的加载器节点复制进 ComfyUI 内部剪贴板，容易与图自身的复制/粘贴
流程冲突；而其真实目的（把加载器节点放到画布上）由拖拽卡片或**添加节点**
按钮更直接地达成。

## <img src="https://api.iconify.design/lucide/book-open.svg?color=%237c3aed" width="34" height="34" align="middle" alt=""> 文档

逐步使用指南，每份都完整自足：

- [`docs/USAGE.md`](docs/USAGE.md) — English
- [`docs/USAGE.ja.md`](docs/USAGE.ja.md) — 日本語
- [`docs/USAGE.zh-CN.md`](docs/USAGE.zh-CN.md) — 中文（简体）
- [`docs/USAGE.zh-TW.md`](docs/USAGE.zh-TW.md) — 中文（繁體）

内容涵盖安装、两种布局、卡片操作与拖拽到节点图、模型编辑器（文件夹
选择器、带文件夹前缀的文件名、预览、描述）、下载与任务列表、hub 上传
（Hugging Face / ModelScope）的阶段与完成消息、ZipNN 压缩、设置与
语言，以及故障排查表。

延伸阅读：

- [`docs/BENCH.md`](docs/BENCH.md) —— 本 README 中所有性能结论背后的
  测量记录。
- [`native/README.md`](native/README.md) —— Rust 工作区：布局、测试
  金字塔、fuzz 配置与预构建二进制的生成方式。

---

<a id="development"></a>

## <img src="https://api.iconify.design/lucide/terminal.svg?color=%230ea5e9" width="34" height="34" align="middle" alt=""> 开发

**构建** Web 打包产物只需要 Node.js；在 ComfyUI 内运行扩展只需要
Python（Rust 核心预构建随附）。

```bash
corepack enable          # 使用锁定的 pnpm 版本（Node 26）
pnpm install
uv sync --frozen         # Python 开发/测试环境（.venv）
```

Python 开发/测试环境（pytest、ruff、mypy、hub SDK、torch‑CPU）由
**[uv]** 管理 —— `uv sync --frozen` 从 `pyproject.toml` 的
`[dependency-groups]` 与已提交的 `uv.lock` 一次性重建。这只是开发上的
便利：_运行时_契约不变 —— ComfyUI 仍会在首次启动时自行安装
`requirements.txt`（两份清单由测试机械地固定为一致）。

开发 Rust 核心时，stable 工具链就足够了 —— debug 构建也是合法的
`mm_core`（API 握手与整个 pytest 套件的行为与 release 一致）：

```bash
cd native && cargo build -p mm-core
cp target/debug/libmm_core.so native-bin/linux-x86_64/mm_core.abi3.so   # 本平台的 tag
```

`scripts/build-native.sh --target <tag> --size-gate` 可复现随附的 release
产物（cargo‑zigbuild 保证 glibc ≥ 2.28 下限、maturin + lipo 生成 macOS
universal2、maturin/MSVC 生成 Windows）；[`native/README.md`](native/README.md)
记录了工作区、测试金字塔与 fuzz 配置。

| 脚本                                  | 用途                                                          |
| ------------------------------------- | ------------------------------------------------------------- |
| `pnpm dev`                            | Vite 开发服务器（为 ComfyUI 热重载写入 `web/manager-dev.js`） |
| `pnpm build`                          | 生产构建到 `web/`                                             |
| `pnpm build:clean`                    | 删除 `web/` 后重新构建                                        |
| `pnpm rebuild`                        | 删除 `node_modules/` **与** `web/`，重新安装后构建            |
| `pnpm typecheck`                      | `vue-tsc --noEmit` 类型检查                                   |
| `pnpm lint` / `pnpm lint:fix`         | ESLint（flat config）                                         |
| `pnpm lint:css` / `pnpm lint:css:fix` | Stylelint 17（CSS + Vue SFC style 块，兼容 Tailwind v4）      |
| `pnpm deps`                           | dependency-cruiser：导入图关卡（需要 Node ≥ 22）              |
| `pnpm deps:graph`                     | 输出模块图 `dependency_graph.svg`                             |
| `pnpm format` / `pnpm format:check`   | Prettier（带 Tailwind 插件）                                  |
| `pnpm py:lint` (`:fix`)               | 后端 Ruff lint（`py/`、`__init__.py`、`tests/`、`scripts/`）  |
| `pnpm py:format` (`:check`)           | 后端 Ruff format                                              |
| `pnpm py:test`                        | pytest 套件（未构建 `mm_core` 时跳过 native 路径测试）        |
| `python -m mypy`                      | 后端静态类型（pyproject 的 `[tool.mypy]`）                    |
| `pnpm rs:fmt` (`:check`) / `rs:lint`  | `native/` 的 rustfmt / clippy `-D warnings`                   |
| `pnpm rs:test`                        | Rust 单元 + 集成测试（mm-core 不带 extension-module）         |
| `pnpm rs:build`                       | `mm-core` 的 release 构建                                     |
| `pnpm fallow`                         | Fallow 完整流水线：死代码 + 重复 + 健康度                     |
| `pnpm fallow:dead` (`:type-aware`)    | 未使用文件/export/类型/依赖、循环 —— 可选的 TS 语义分析       |
| `pnpm fallow:dupes`                   | AST 克隆检测（`mild` 模式，见 `.fallowrc.json`）              |
| `pnpm fallow:health`                  | 复杂度热点、重构目标、0–100 健康分                            |
| `pnpm fallow:fix:dry` / `fallow:fix`  | 自动清理预览 / 应用（永远先 dry-run）                         |
| `pnpm fallow:audit`                   | PR 风格关卡：只报告当前变更引入的问题                         |

**husky** 的 `pre-commit` 钩子会对暂存文件运行 **lint-staged**（前端
ESLint + Stylelint + Prettier，后端 Ruff），外加完整的 `pnpm typecheck`。

### 1. 质量关卡

**Fallow**（Rust 实现，分析器内不含 AI）把仓库读作一张依赖图，报告未
使用的文件/export/类型/依赖、循环导入、克隆组与复杂度热点；代码树保持
**零未使用 export、零重复**，CI 在任何 ERROR 级发现上失败。

**ESLint 10** flat config 串联 `typescript-eslint`、`eslint-plugin-vue`、
`eslint-plugin-import-x`、`eslint-plugin-tailwindcss` 与
`eslint-config-prettier`；**Prettier** 负责格式化与 Tailwind 类排序；
**Stylelint 17** 检查 `src/style.css` 与所有 SFC style 块；
**dependency‑cruiser 18** 把关 `src/` 的导入图（无循环、无孤儿、出货
代码不导入 devDependency 与 Node core）。

**Ruff**（`pyproject.toml [tool.ruff]`）负责后端 lint 与格式化（目标
`py312`、行宽 120、精选规则集），其上再由 **mypy** 检查静态类型。

**CI** 在每次 push 时运行以上全部，外加前端测量关卡
（`scripts/bench/front/k15.mjs`）；`native` 工作流构建八个平台产物
（四个 abi3 + 四个 abi3t）、强制执行尺寸预算、对全部七个 fuzz 目标做
smoke fuzz、在 CPython 3.12 与 3.14 下 import abi3 产物、在 3.15 的
GIL/自由线程两种构建下 import abi3t 产物，并在 Linux、Windows、macOS 上
运行完整 pytest 套件（含自由线程 3.15t 单元）与官方 `zipnn` 交叉验证。

### 2. 项目结构

```
├─ __init__.py            # ComfyUI 入口：安装依赖、注册路由
├─ py/                    # Python 后端（aiohttp 路由、任务、hub 客户端）
│  ├─ manager.py          #   模型 CRUD + native 加速的列表/卫生扫描
│  ├─ download.py         #   下载任务（http + huggingface_hub + modelscope_hub）
│  ├─ upload.py           #   本地文件上传（路径校验）
│  ├─ upload_hf.py        #   上传到 Hugging Face（共享 hub 流水线）
│  ├─ upload_modelscope.py#   上传到 ModelScope
│  ├─ compress.py         #   驱动 native 任务 API 的 ZipNN 路由
│  ├─ information.py      #   Civitai/HF/ModelScope 页面解析、预览服务
│  ├─ search.py           #   多平台模型名搜索 + 头像代理
│  ├─ identify.py         #   Civitai 哈希反查
│  ├─ native.py           #   预构建核心加载器（平台 tag、API 握手）
│  ├─ http_client.py      #   所有 hub 往返共享的 aiohttp 会话
│  ├─ watcher.py          #   可选的模型库监视（native notify，默认关闭）
│  ├─ auth.py · config.py · thread.py · utils.py
├─ native/                # Rust 工作区（GPL-3.0；归属见 native/NOTICE）
│  ├─ crates/znn-codec/   #   ZipNN 格式核心 + scan/hash/header/webp（+ fuzz/）
│  ├─ crates/mm-core/     #   PyO3 abi3 绑定（mm_core 模块）
│  └─ native-bin/         #   按平台 tag 存放的预构建二进制（提交于 main）
├─ src/                   # Vue 3 前端
│  ├─ components/         #   应用组件 + ui/（reka-ui 封装）
│  ├─ hooks/              #   store、models、download、zipnn、upload、config 等
│  ├─ utils/ · types/ · locales/
│  ├─ style.css           #   Tailwind v4 入口 + 设计令牌
│  └─ main.ts             #   注册为 ComfyUI 扩展
├─ scripts/               # native 构建 + 官方 zipnn 交叉验证 + 前端性能关卡
├─ tests/                 # pytest 套件：golden 契约、parity、接合部
└─ web/                   # 提供给 ComfyUI 的预构建打包产物（已提交）
```

---

<a id="credits"></a>

## <img src="https://api.iconify.design/lucide/heart-handshake.svg?color=%23ec4899" width="34" height="34" align="middle" alt=""> 致谢与归属

ComfyUI‑Model‑Manager‑Neo 之所以存在，只因为
**[hayden‑cn](https://github.com/hayden-cn)** 的
**[`ComfyUI-Model-Manager`](https://github.com/hayden-cn/ComfyUI-Model-Manager)**
先存在。这个 fork 中的每一个结构性想法 —— 模型文件夹抽象、带 websocket
进度协议的可恢复下载任务系统、Civitai 与 Hugging Face 页面解析器、把
卡片拖到节点图上的集成、模型编辑器的表单管线，乃至卡片尺寸预设这样的
小细节 —— 都是 hayden‑cn 的设计。Neo 改变的是外表、依赖与大量 bug；
它不必重新发明躯体。阅读原版仍然是理解_这个代码库为何是现在这个形状_
的最快途径，而对架构的诚实归属是：**他们的**。

压缩引擎实现了 **[ZipNN](https://github.com/zipnn/zipnn)** 项目（MIT）的
格式 —— Hershcovitch 等人，_“ZipNN: Lossless Compression for AI Models”_
（[arXiv:2411.05239](https://arxiv.org/abs/2411.05239)）—— 熵编码遵循
zstd huff0/FSE 规范（RFC 8878）与 FiniteStateEntropy（BSD‑2‑Clause）。
原生核心的完整第三方归属见 [`native/NOTICE`](native/NOTICE)。

本 fork 是依据 **GNU General Public License v3.0** 使用与修改的衍生
作品。Neo 中的修改（UI 重建、PrimeVue 移除、Rust 原生核心、ZipNN
压缩、Hugging Face / ModelScope 枢纽集成、多 hub 搜索与哈希识别、包现代化、工具链、
可靠性与安全性加固、批量扫描移除、日语本地化 —— 逐条见
[与原版相比改变了什么](#what-changed)）以相同的 GPL‑3.0 许可证提供。
按许可证要求，原版版权声明与许可证全文保留在 [`LICENSE`](LICENSE) 中。

### <img src="https://api.iconify.design/logos/qwen-icon.svg" width="26" height="26" align="middle" alt=""> Built with Qwen Studio

本 fork 的很大一部分是在与 **[Qwen Studio]** 的紧密协作中完成的：玻璃
拟态 UI 重建、Rust 原生核心、ZipNN 压缩引擎、hub 上传流程、可靠性与
安全性加固，以及大量调试工作。

构建过程中使用了这些优秀项目：[reka-ui]、[Tailwind CSS]、[Lucide]、
[VueUse]、[es-toolkit]、[vue-sonner]、[huggingface_hub]、[hf_xet]、
[modelscope_hub]、[ZipNN]、[zenwebp]。

---

<a id="license"></a>

## <img src="https://api.iconify.design/lucide/scale.svg?color=%2394a3b8" width="34" height="34" align="middle" alt=""> 许可证

**GPL‑3.0‑only** —— 全文见 [`LICENSE`](LICENSE)。

Rust 原生核心（[`native/`](native/)）还为预览 WebP 管线额外链接
**[zenwebp]** —— 纯 Rust WebP 编解码器，**AGPL‑3.0‑only** 或 Imazen
商业双许可。Neo 为 GPL‑3.0‑only，并在 **AGPL‑3.0** 条款下使用 zenwebp
（AGPLv3 §13 明确允许 AGPL 作品与 GPLv3 作品结合，AGPL 部分保持
AGPL）。ComfyUI 是**本地**应用而非网络服务，因此 AGPL 的网络条款在此
实质上不发生作用；分发时的源码可得义务由本公开仓库满足。原生核心的
完整第三方归属：[`native/NOTICE`](native/NOTICE)。

<div align="center">

**如果 Neo 为你节省了时间，请考虑给仓库点个星 <img src="https://api.iconify.design/lucide/star.svg?color=%23eab308" width="19" height="19" align="middle" alt="">，并感谢
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
