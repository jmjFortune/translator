# DECISIONS

> 只追加，不修改历史条目。每条包含：日期、决策、理由、影响。

## D-001 删除旧 PyQt 界面层，保留后端逻辑

- 日期：2026-10-20
- 决策：删除 `ui/main_window.py`、`quotes.py`、`caring.py`、`mac/ui/`、`pdf2zh/gui_pyqt5.py`；保留 `ui/` 下的翻译与配置模块。
- 理由：前端改由 `web/` 承担；PyQt 界面与业务逻辑耦合在单个 8000 行文件里，无法复用。
- 影响：`_launcher.py` 与三个 `.spec` 暂时失效，待新打包方案确定后重写。

## D-002 后端使用 Python + FastAPI

- 日期：2026-10-20
- 决策：`server/` 使用 FastAPI + Uvicorn + SQLite + SSE，不使用 Flask + Celery + Redis。
- 理由：翻译内核是 Python 生态（pdf2zh / babeldoc / onnxruntime / PyMuPDF）；桌面端不应依赖 Redis；SSE 足够表达单向进度。
- 影响：`ui/translate_worker.py` 需要去掉 `QThread` / `pyqtSignal`。

## D-003 段落对照通过 converter hook 捕获，不重新解析 PDF

- 日期：2026-10-20
- 决策：在 `pdf2zh/converter.py` 的 `news = list(executor.map(worker, sstk))` 之后、排版之前挂回调，直接输出 `(page, bbox, source, translated)`。
- 理由：`sstk` 与 `news` 在内存中严格一一对应，捕获成本接近于零；重新解析 dual PDF 做对齐既慢又不准。
- 影响：需要给 `TranslateConverter` 增加可选回调参数，并从 `high_level.translate()` 透传；回调用 try/except 包裹，失败不影响 PDF。

## D-004 PDF 导出保持 pdf2zh 原生，不自行重排

- 日期：2026-10-20
- 决策：mono / dual / side-by-side 继续由 pdf2zh 生成；后端只负责调度、存储、分发。
- 理由：版面、公式、字体处理是 pdf2zh 的核心价值；重写必然退化。
- 影响：前端下载接口直接流式返回生成好的 PDF。

## D-005 公式 LaTeX 暂不作为一期能力

- 日期：2026-10-20
- 决策：`ReaderView` 的公式先返回裁图 + 原文，`latex` 字段允许为空；不在一期引入 pix2tex / Mathpix。
- 理由：pdf2zh 只保留公式矢量字形，不产出 LaTeX；引入 OCR 会显著增加依赖与安装体积。
- 影响：前端公式弹窗需兼容 `latex === null` 的展示。

## D-007 原文图形与居中段落的保真处理

- 日期：2026-10-21
- 决策：
  1. 新增 `server/services/fidelity.py`：pdf2zh 生成译文页后，从原页按 bbox 裁切渲染图片块（含 stencil mask），贴回译文页同一位置。
  2. `pdf2zh/converter.py` 增加居中段落检测：用出现频率最高的正文左右边界判断段落是否左右留白对称，是则按译文实际宽度重新居中。
- 理由：pdf2zh 重建页面时只保留文字和 `LTLine`，内联图片/蒙版横线会丢；译文变短后从段首 `x0` 起排会整体偏左。
- 影响：只改渲染，不改翻译内容；图片区域以 300 dpi 栅格化后贴回，文件体积会略增。

## D-006 多 agent 协作以仓库为唯一媒介

- 日期：2026-10-20
- 决策：不依赖聊天记录传递上下文；角色、所有权、接口契约、进度全部落在 `AGENTS.md` / `docs/STATUS.md` / `docs/openapi.json`。
- 理由：聊天上下文无法跨工具共享，且会失真；GitHub Agent HQ 不支持 ChatGPT / Gemini / OpenCode 订阅混用。
- 影响：每个 agent 在自己的 `agent/<name>/<task>` 分支或 worktree 工作，产出 diff / PR 后由人合并。

## D-008 主翻译管线跳过纯数字段落

- 日期：2026-10-21
- 决策：`converter.py` 的 `worker()` 在送翻译器前过滤掉整段只有数字/符号、罗马数字、单字符的段落。
- 理由：页脚 `3` 被 Bing 翻成「三」。根因是表格管线早有 `_should_translate`，正文管线没有；不能靠“页边距位置”打补丁。
- 影响：只影响整段数字（页码、公式编号、年份）。句中和句尾数字随正文一起翻译，实测 `12`、`95.3%`、`3.2` 均保留。

## D-009 图片默认保留原始像素

- 日期：2026-10-21
- 决策：`fidelity.py` 对非蒙版图片直接 `extract_image` 原始字节插入；stencil mask / 内联图仍按 300 dpi 渲染区域。
- 理由：统一 300 dpi 会把 10962×3210 的图缩到约 2550 宽，超清图明显变软。
- 影响：普通图片不再降质，文件体积会增大（样例单页 3.8 MB）。

## D-010 新增 OpenCode Go 翻译服务

- 日期：2026-10-21
- 决策：新增 `opencode-go` 服务（`OpenCodeGoTranslator`），默认模型 `deepseek-v4.1-flash`。
  - Endpoint：`https://opencode.ai/inference/go/openai/v1`
  - 必须发送 `User-Agent: pdf2zh-desktop/1.0` 与 `x-opencode-session: <uuid>`
- 理由：OpenCode Go 强制要求会话头，默认 SDK UA 会被网关拒绝；专用服务比塞进 `openailiked` 更清晰。
- 影响：每个翻译页面实例生成一个 session id；配置 Key 用 `python3 scripts/set_key.py opencode-go <key>`。
- 注意：OpenCode Go 面向 coding agent，批量翻译是否合规需自行确认；OAuth 凭证会过期，长期应使用 Console API Key。

## D-011 目录页排版重排

- 日期：2026-10-21
- 决策：
  1. `run_real` 接回 `pdf2zh.toc_fix.fix_toc_pages`，与旧桌面版同款，重排「标题 …… 页码」的目录页。
- 理由：目录被当正文翻译会丢缩进/点线/页码。
- 影响：目录页按原排版重排；人名仍按原逻辑翻译。

## D-012 目录页解析兼容合并行，标题走 Bing

- 日期：2026-10-21
- 决策：
  1. `toc_fix.extract_toc_entries` 改为先按视觉行拼接全文，再用正则拆 `标题 / 点线 / 页码`，兼容「三段分离」和「整行一个 span」两种 PDF。
  2. 目录标题默认用 Bing 翻译（`toc_service`），正文仍用主服务。
- 理由：Elsevier 等 PDF 把 `...... 56` 放在同一行；OpenCode Go 对 16 条标题的批量请求会长时间超时。
- 影响：目录页可正确恢复缩进/点线/右对齐页码；目录标题质量略低于主模型，但稳定。

## D-013 后端迁移至 pdf2zh-next

- 日期：2026-10-21
- 决策：按用户明确授权，将 `server/` 的真实翻译内核迁移到已发布的 `pdf2zh-next==2.9.0`，通过 `pdf2zh_next.high_level.do_translate_async_stream()` 调用；此决策替代根约定中调用旧 `pdf2zh.high_level.translate()` 的要求。
- 理由：使用 BabelDOC 排版管线，保留 FastAPI、线程任务队列、SQLite、现有 HTTP/SSE 契约及 mono / dual / side_by_side 下载。
- 影响：跨目录修改限于 `server/**`、必要的 `scripts/**` 和协作文档；前端、旧桌面端和 vendored `core/site-packages/pdf2zh/` 不改。旧引擎专用的图形恢复、TOC 重排和裁页补丁退出服务管线，由新引擎处理排版及选页。旧配置字段继续解析，服务映射与不支持项需明确报告。真实运行使用 Python 3.11–3.13（本机使用 `.venv312`）；默认 Python 3.14 环境仅能运行不加载引擎的 mock 测试。

## D-013 删除旧 pdf2zh 引擎与 fidelity 补丁

- 日期：2026-10-21
- 决策：迁移到 pdf2zh-next 后，删除 `core/site-packages/pdf2zh/`、`pdf2zh-1.9.9.dist-info` 和 `server/services/fidelity.py`。
- 理由：新翻译链路只调用 `pdf2zh_next.high_level`；旧引擎专用的图片恢复、目录重排、公式居中、数字过滤补丁不再参与翻译。
- 影响：`ui/translate_worker.py`、`_launcher.py` 仍引用旧 `pdf2zh`，目前是死代码，待单独清理。

## D-014 对接 Gemini 前端与真实服务

- 日期：2026-10-21
- 决策：根据用户“对接 Gemini 做的前端”的授权，允许当前会话跨目录修改 `web/src/**` 的数据来源和事件处理、必要的 Next.js 连接配置，以及后端预览/下载契约和测试。沿用现有布局、配色、字号和组件样式，不重做视觉层。
- 理由：当前前端完全使用 mock 数据和定时器，服务、语言、排版标识与已有 FastAPI 契约不一致，尚不能操作真实翻译任务。
- 影响：按 `docs/openapi.json` 对接上传、SSE、取消、下载、历史、服务设置和术语库；新增契约必须先导出再用于前端。阅读器数据能力边界需明确：现有 content 接口尚无段落数据，不能以示例论文冒充真实结果。浏览器验证使用隔离配置和数据，避免修改真实凭证或术语库。

## D-015 修正 macOS 桌面 App 仍启动旧界面的问题

- 日期：2026-10-21
- 决策：用户截图确认 `/Applications/pdf2zh.app` 仍为旧 PyQt 2.3.37 安装包。新增 `scripts/` 下的原生 AppKit/WebKit 启动壳与本机构建脚本，连接已验收的 Gemini 页面和 pdf2zh-next 后端；先验证新壳，再备份并更新本机桌面 App。
- 理由：之前只验证了网页和 HTTP 服务，没有更新已安装桌面应用的可执行入口；用户双击 App 因而仍看到旧界面。此修复属于已授权迁移与前端对接的桌面启动补全。
- 影响：源文件限定在 `scripts/**`、必要的 `server/**` 测试和协作文档，不修改前端视觉、不再引入 Python UI。支持原生选文件、下载和确认弹窗；本机启动壳依赖当前仓库、已构建 `web/out` 和受支持的 Python 环境，不冒充可脱离项目分发的独立安装包。旧安装包备份后才替换，用户配置不迁移或清除。

## D-016 翻译服务名称使用英文

- 日期：2026-10-21
- 决策：按用户截图中“去掉中文”的要求，将服务目录的六个中英混合显示名改为英文，由现有接口直接提供给前端。
- 理由与影响：仅修改 `server/services/credentials.py` 的 name；保留服务 ID、历史配置 prefix 和凭证读取方式，不改布局、交互或接口结构。

## D-017 排版格式改为多选

- 日期：2026-10-21
- 决策：用户在说明三种排版后明确要求“改成多选”，授权当前会话修改 `web/src/components/TranslateView.jsx` 的选择状态与提交行为。沿用三个按钮的布局与样式，多项可同时高亮，通过 aria-pressed 表达状态；至少保留一种，最后一项不可取消。
- 数据流：初始选中后端 defaults.output_formats 中的格式；提交时 output_formats 只包含当前选项，不再偷偷合并全部默认格式。现有后端契约已支持多格式，不新增接口或更改全局默认设置。
- 验证：静态生产构建；浏览器检查多选、取消、至少一项，以及单选/双选/三选的实际请求与生成文件一致。采用隔离 mock 数据目录，不消耗用户凭证。

## D-018 项目更名为 translator

- 日期：2026-10-21
- 决策：按用户“将这个项目改名为translator”的明确要求，跨目录更新当前产品的前端标题/品牌、npm 包名与锁文件元数据、API 名称与 OpenAPI 标题、macOS 应用/可执行文件/菜单名称、项目元数据与中英文 README 入口。保留布局和功能。
- 兼容：pdf2zh-next 是实际依赖名称，上游链接、旧版文档/启动器、插件协议、已有 pdf2zh_files 数据目录、~/.config/pdf2zh 配置、浏览器存储键及原 bundle ID 均保留，避免名称替换破坏已有状态或上游归属。当前文件系统大小写不敏感，项目目录仅将 Translator 的显示大小写改为 translator，旧大小写路径仍能解析；不修改 Git remote。
- 桌面：构建/安装为 translator.app，继续使用当前仓库与 Python；依旧属于本机开发包。当前旧 App 从构建目录运行且已安装旧路径不存在，验证后切换到新的 /Applications/translator.app。
- 验证：构建、后端测试、实际网页名称/API 与新 App 启动；检查现有配置与数据仍使用原路径。

## D-019 translator 图标设计

- 日期：2026-10-21
- 决策：按用户“给这个项目设计一个icon”的请求，允许当前会话新增 `assets/` 下的独立图标设计稿及 `docs/` 下的设计说明。使用内置 imagegen，沿用产品的暖白、陶土橙、深灰，以两张相接文档表达翻译；无文字，适合 macOS 小尺寸展示。
- 范围：本次交付新的版本化 PNG 设计稿，不覆盖现有 AppIcon.icns 或其他旧资源，不自动替换安装包；最终提示词和生成方式随设计保存，便于迭代。

## D-021 Gemini C1 图标圆角变体

- 日期：2026-10-21
- 决策：按用户“看看 Gemini 的设计图，修改生成新图”和“能圆角一些”的明确要求，以当前 `assets/icon.png` 为唯一编辑底图，使用内置 imagegen 生成独立圆角预览；允许新增 `assets/` 变体和说明文档。
- 保留：黑白双页、陶土橙书签、文字横线、原布局和暖白底板；主要软化书页外角、底部边缘、书签尖端。不覆盖 Gemini 的 PNG/SVG、平台图标或安装包。

## D-022 保留圆角书卷并探索文献变体

- 日期：2026-10-21
- 决策：用户认可上一版并要求保留，同时希望更像文献而非书。原圆角书卷预览完整保留；基于它生成独立论文双页变体，恢复外框完整四角，去除书脊/书页厚度，使用双栏正文骨架和短橙色阅读标记。
- 范围：新增版本化 PNG 与提示词说明，不覆盖已认可预览、Gemini 原稿或已安装 App 图标。本次仍是视觉方案比较。

## D-023 回到已认可轮廓进行轻微精简

- 日期：2026-10-21
- 决策：用户否定密集双栏的文献变体后，回到已认可的圆角书卷作为底图，只削薄底部层叠、适当缩短橙色书签，并保留原有稀疏横线和双页弧线。新增独立微调预览，认可原版继续保留。

## D-024 选定精简圆角版作为最终视觉方案

- 日期：2026-10-21
- 决策：用户对上一张精简圆角稿明确回复“就这个吧”，最终视觉方案锁定为 `assets/translator-icon-c1-refined-preview.png`。不再生成新方向，前面的圆角原稿继续保留。
- 边界：本次记录视觉定稿，不将预览文件误称为已完成的平台图标；透明外缘清理、ICNS/favicon 导出及安装替换尚未进行。

## D-025 清理旧图标候选

- 日期：2026-10-21
- 决策：用户明确要求“前面的icon删掉”，删除之前保留的圆角原稿与已否定的双栏文献稿，只保留最终选定的 refined 候选。同步标注设计说明，避免指向已删除的候选图。
- 范围：不删除 App 构建使用的 ICNS、Windows ICO、README 正在引用的原图或 Gemini 的未提交源文件；本次清理的是对话中的候选预览。

## D-026 构建独立 macOS App 并准备 GitHub

- 日期：2026-10-21
- 决策：用户要求“编译成正式app，然后准备推送到github”，授权跨目录完成选定图标的平台导出、前端品牌图标引用、独立运行时打包、必要的后端数据路径/资源初始化、构建脚本与发布文档。沿用已经选定的图案，不重新生成设计；导出阶段用系统图形工具进行尺寸/透明轮廓规范化。
- 打包：Swift + 系统 WebKit 壳内置可搬移 CPython、固定版本 Python 依赖、必要后端源码、静态前端和经上游摘要验证的 BabelDOC 静态资源。不包含用户 Key、配置、翻译缓存、文档或数据库。正式包使用用户 Application Support 存放任务数据；本机安装迁移旧历史，源数据保留。
- 兼容：保留引擎包名、既有凭证路径和 bundle ID；开发启动模式继续可用。构建中间目录使用 .noindex 避免 Spotlight 出现同名构建副本。
- GitHub：当前无远端，先完成构建、测试、源码/历史敏感内容与大文件审查及发布说明，再按用户给定仓库准备远端；本次未获公开仓库或发布 Release 的具体目标授权，不擅自创建公开仓库或发布。
- 签名：仅检查到 Apple Development 身份，没有 Developer ID；本次不将本地签名描述为已公证的公开分发签名。

### D-027 · 2026-10-21 · Standalone release size
- 用户要求解释并缩减首轮 1.2 GB App。发布包使用明确的 API-only dependency closure：仅跳过 pdf2zh-next 的 Gradio GUI 三项依赖及其独占间接依赖，保留翻译内核、所有服务商和实际需要的科学计算库；不改上游翻译逻辑。
- BabelDOC 当前字体映射会加载跨语言回退字体，不能仅删除非中文字体而保持首次翻译行为。完整的哈希校验公共模型/字体以 ZIP 压缩资源入包，启动时按清单校验并写入用户缓存；不包含翻译缓存数据库。
- 运行时按已锁定 wheel 的文件清单复制，仅排除测试目录、字节码缓存；发布清单记录实际包含的软件包，并注明不包含上游 Gradio GUI。压缩下载大小与展开 App 大小分开报告。

### D-028 · 2026-10-21 · Approved simplified font profile
- 用户明确同意仅保留简体中文、拉丁文字和通用回退字体（原始字体约 104 MiB），移除日文、韩文和港/台繁体专用字体（约 150 MiB）。此项取代 D-027 中保留全部字体的发布范围。
- 构建脚本使用显式文件白名单同步过滤静态资源清单和打包副本中 BabelDOC 的字体家族/元数据，保留原字体优先顺序；不改开发环境或旧 vendored 内核，不要求首次翻译下载已移除的字体，不删除用户既有缓存。
- App 内记录字体配置与上游适配原因。中英文输出保留宋体/黑体、粗体/斜体、楷体及通用补字；其他目标语言不再附带地区专用字形，不能沿用完整字体包的排版保证。
- 验证在与源码分离、空 HOME/缓存的环境进行，确认所有字体列表仅引用白名单、资源预热不会下载其他字体，且实际翻译与三种 PDF 导出通过。

### D-029 · 2026-10-21 · Further runtime size audit
- 用户要求继续检查整个 App 的体积，而不只精简字体。针对当前 arm64 发行版，允许在构建副本中移除 universal2 的 Intel 切片、pip/ensurepip/IDLE 等开发工具和 ONNX 的 C/C++ 构建源码；保留所有许可证与 Python API。
- Python 推理扩展未链接独立 C API 的 libonnxruntime，当前静态链接解释器及扩展也未链接额外的 libpython dylib。仅在扫描其余 Mach-O 的加载依赖确认没有引用时，才可排除这两项，并须通过隔离运行和真实翻译验证。
- 静态模型/字体资源可改用 ZIP/LZMA 压缩，仍完整内置、逐文件哈希验证，无首次使用下载替代；用户已有缓存不删。
- 可对满足引擎版本约束的较小 OpenCV/ONNX Runtime wheel 做隔离体积与兼容性比较；只有通过真实翻译及包内自检后才更新锁文件采用，不静默删功能或用空模块替代。

### D-030 · 2026-10-21 · Correct installed identity and audit build caches
- 用户指出原生窗口与网页模拟窗口按钮重复、已安装 App 图标仍旧，并明确要求保留较新 OpenCV，重点排查构建方法及缓存。恢复锁文件中的 OpenCV 5.0.0.93，不以降低版本作为后续体积优化。
- 授权范围：删除 Sidebar 中纯装饰的三枚模拟 macOS 按钮，保留系统窗口控件；安装选定图标的独立 App，备份旧本地启动器，更新 LaunchServices 身份缓存所用的图标资源名/构建号。先确认没有运行中的用户任务再关闭旧入口。
- 当前安装仍是 508 KiB 的开发入口，引用源码目录和 .venv312；新图标仅在测试构建中。不能把“已导出图标”描述成“已安装新图标”。
- 构建排查确认：首轮范围过大；一次隔离导入自检的 -I 会忽略 PYTHONDONTWRITEBYTECODE 环境变量，曾在测试副本生成字节码，改为显式 -B。当前成品没有字节码、开发/前端缓存或用户数据库；增加缓存/私有文件打包阻断检查。
- 仅清理当前会话创建的明确测试 App、副本、wheel 探测和过期构建中间文件；保留用户配置、历史、原始 PDF、既有引擎缓存、选定图标和原资源备份。模型/字体运行缓存与构建缓存分别说明。

### D-031 · 2026-10-21 · Keep only the current translator core
- 用户在授权推送后要求清理项目、保留核心。允许跨目录移除当前 Next.js/FastAPI/pdf2zh-next/macOS App 不再使用的 Windows BAT/VBS/EXE/PyInstaller 入口、旧 Qt 模块、mac 镜像、宣传站点/旧教程、重复插件与图标导出、旧字体/模型及配置清单；保留现有前端视觉与接口、测试、固定依赖、当前图标源文件/平台资产、实际被引用的插件下载及对应源码。
- 特别记录：按根 AGENTS.md 的例外要求，允许将旧 core/runtime 与 core/site-packages（含其中 pdf2zh 文件）移出项目。它们已经不被真实翻译服务调用；不再以旧内核作兜底。未跟踪的旧资源/运行时归档到用户 Application Support/translator/project-archive，保留可恢复副本；已跟踪旧代码可从本地清理前分支恢复。
- 后端仍依赖的 ui/config_manager.py、glossary_manager.py 保留兼容包名与 ~/.config/pdf2zh 路径；仅移除零调用的旧游戏/历史管理代码和导入。AGENTS.md 本身不改，DECISIONS/STATUS 历史保留；根说明改为当前产品使用方式，并保留上游归属。
- 当前 Qt/Windows 资产不再由导出脚本重新生成；当前插件源码移到 integrations/zotero，下载 URL 不变。用户数据、pdf2zh_files、已安装 App、Git/Jujutsu 元数据、开发环境和依赖均不作为旧代码删除。
- 推送策略：目标为空仓库时，推送清理后的独立初始源码快照到 agent/codex/translator-core 分支；完整旧提交和清理提交保留在本地分支，不重写或强推远端，不直接提交 main。如此避免将已删除旧资产和历史遮罩凭证字面量一并上传。只推源码，不自动发布二进制 Release。


### D-032 · 2026-10-21 · Simplify the retained source and dependencies
- 用户进一步要求对项目、代码和文件精简。允许在 D-031 基础上跨目录清理经当前调用关系核实的死代码、未使用依赖及无效样式；前端布局、视觉与交互保持验收基线，HTTP/SSE 契约不变。
- 前端移除未导入的 canvas-confetti、clsx、framer-motion、tailwind-merge 及其独占间接依赖；清理无引用的 Tailwind 色值/阴影和 CSS 声明，保留实际使用的颜色、字体、纹理与滚动条。
- 后端仅保留当前术语库 API 使用的读取、保存、预设名称、添加和删除操作；移除旧 Qt 端专用的 CSV/JSON 文件导入导出、预设加载、自定义扫描、字符串替换等零调用方法。当前 API 整库替换和翻译术语传递继续保留。
- 移除未使用的 JobEvent/EventType、数据库段落写入助手与空置参数、无引用导入，以及重复的 server/run.py 启动入口；统一使用文档中的 python -m uvicorn。保留段落读取/API/数据表与测试，不删除既有数据。
- OpenCV 5.0.0.93、所有实际使用的翻译服务商与 App 构建流程保持；本轮精简源码和开发依赖，不把源码缩减声称为已安装 App 体积缩减。继续普通提交/推送 agent/codex/translator-core，不改写历史或 main。
