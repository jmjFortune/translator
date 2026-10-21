# STATUS

> 唯一进度来源。每次工作结束前更新本文件。格式见根目录 `AGENTS.md`。

## 当前阶段

**阶段 2：pdf2zh-next 前后端联调已完成，Reader 使用真实 PDF；段落对照与复杂文档回归待继续**

## 2026-10-20 Claude（server skeleton）

- 做了什么：
  - 新增 `server/`：FastAPI + SSE + SQLite
  - 任务接口：上传、状态、进度流、取消、下载（mono / dual / side_by_side）
  - 历史接口：列表、详情、删除、段落内容（`paragraphs` 表已建，等待 hook 填充）
  - 设置接口：22 个服务、Key 只写不回显、默认语言/线程/输出格式
  - 术语库接口：读取、整体替换、增删
  - `PDF2ZH_MOCK=1` 时走模拟翻译，前端可在没有 pdf2zh 的机器上联调
  - `docs/openapi.json` 已导出，14 个路径，前端以此为唯一契约
  - `server/tests/test_api.py`：6 个冒烟测试全部通过
- 改了哪些文件：`server/**`、`scripts/export_openapi.py`、`docs/openapi.json`、`.gitignore`
- 没做完 / 已知问题：
  - 真实 `pdf2zh` 调用尚未在本机验证（macOS 缺 `fitz` / `pdf2zh` 依赖）
  - 表格翻译、自动术语提取、OCR 独立管线暂未接入（参数已保留）
  - 段落 hook 尚未写入 `converter.py`，`/content` 目前返回空 sections
- 下一个接手的人先看：`server/AGENTS.md`、`docs/DECISIONS.md` D-003

## 2026-10-20 Claude（真实 pdf2zh 验证）

- 验证样本：Zotero `storage/K5IUW8QF/Mikolov et al. - Distributed Representations...pdf`，只翻第 1 页，服务 `bing`
- 结果：
  - `mono` 1 页，596 个汉字，标题/作者/摘要/正文位置保留
  - `dual` 2 页（原文页 + 译文页）
  - `side_by_side` 1 页，左原文右中文，肉眼确认排版未破坏
  - 通过 HTTP 全链路复验：上传 → 任务 → 下载，返回合法 PDF
- 过程中修掉的问题：
  - 任务快照缺少 `source_path`，真实翻译启动即 `KeyError`
  - `JobOut` 和 SSE `done` 事件会返回绝对磁盘路径，改为下载 URL
  - Google 在本机被 429，默认服务改为 `bing`（免费、可用）
- 复现方式（macOS，使用仓库内 vendored pdf2zh）：
  ```bash
  # 临时目录按 core/site-packages 结构挂载，保证 assets 字体路径可解析
  V=/tmp/pdf2zh-root && mkdir -p $V/core/site-packages
  ln -s $PWD/core/site-packages/pdf2zh $V/core/site-packages/pdf2zh
  ln -s $PWD/assets $V/assets
  PYTHONPATH=$V/core/site-packages:$PWD PDF2ZH_DATA_DIR=/tmp/pdf2zh-data \
    .venv312/bin/python -m uvicorn server.main:app --port 8000
  ```

## 2026-10-21 Claude（版面保真）

- 做了什么：
  - `server/services/fidelity.py`：翻译后从原页按 bbox 裁切渲染图片块，贴回 mono / dual 对应页
  - `core/site-packages/pdf2zh/converter.py`：居中段落检测 + 按译文实际宽度重新居中
  - 处理了 stencil mask（1×1 横线）直接拷字节会变白的问题，改为渲染区域
- 验证：
  - Mikolov 第 1 页：标题居中（中心 306.1 / 页心 306），上下两条横线恢复
  - Zhou 第 3 页：插图、表格线、公式、(1) 编号全部保留
  - Ou 第 2 页：多面板插图、照片、450 条矢量图元全部保留
- 已知问题：页脚页码 `3` 被当成正文翻成「三」；页眉页脚纯数字需要跳过
- 下一个接手的人先看：`docs/DECISIONS.md` D-007

## 下一步（按顺序）

1. ~~`server/` 骨架：FastAPI + 健康检查 + `docs/openapi.json`~~（已完成）
2. ~~上传 / 创建任务 / SSE 进度 / 下载（mock 模式）~~（已完成）
3. 在 Windows 运行时验证真实 `pdf2zh` 路径
4. `TranslateView` 改接真实接口（Gemini）
5. 历史记录 + `LibraryView`（后端已就绪）
6. 设置页 + 术语库（后端已就绪）
7. 段落级对照 hook + `ReaderView`

## 运行方式

```bash
# 模拟模式（无需 pdf2zh，适合前端联调）
PDF2ZH_MOCK=1 .venv/bin/python -m uvicorn server.main:app --reload --port 8000

# 测试
.venv/bin/python -m pytest server/tests -q

# 重新导出接口契约
.venv/bin/python scripts/export_openapi.py
```

## 阻塞项

- 真实翻译需要在装好 `pdf2zh` + `PyMuPDF` 的运行时里验证（Windows 端 `core/runtime` 具备）
- 段落 hook 需要修改 `core/site-packages/pdf2zh/converter.py`，改动前先记录到 `DECISIONS.md`

## 2026-10-21 Claude（数字与高分辨率）

- 做了什么：
  - 正文管线增加纯数字/罗马数字过滤（页脚 `3` 不再变「三」）
  - 图片恢复改为优先拷原始像素，只有 stencil mask/内联图才栅格化
- 验证：
  - Zhou p3 页脚输出 `3`；公式编号 `(1)` 原样
  - Zhou p7 的 10962×3210 三联图输出后仍为 10962×3210，文件 3.8 MB
  - Pezzato p4 公式 (16)–(25)、矩阵、希腊字母全部保留
- 已知问题：斜体小标题（`A. Generative Models…`）被公式字体规则误判，保留英文

## 2026-10-21 Claude（OpenCode Go / DeepSeek V4.1 Flash）

- 做了什么：
  - 新增 `opencode-go` 服务与 `OpenCodeGoTranslator`，处理 UA + `x-opencode-session`
  - 用本机 OpenCode OAuth 凭证完成配置（到期 2026-11-06）
  - `scripts/set_key.py` 支持 `--url` / `--model`
- 验证：
  - Pezzato p4：公式 (16)–(25) 完整，中文明显比 Bing 自然
  - Zhou p3：插图、表格、公式 (1)、页码 `3` 全部保留
  - 速度：约 40–50 秒/页（Bing 约 20–30 秒）
- 注意：OpenCode Go 面向 coding agent，批量翻译可能触碰其使用条款

## 2026-10-21 Claude（目录页）

- 做了什么：接回 toc_fix 目录重排（仅目录，不改人名）
- 验证：Buckley 干净英文原版第 2 页，目录条目/缩进/点线/页码待复验

## 2026-10-21 Gemini（前端 ReaderView Tooltip 气泡）

- 做了什么：
  - 双语阅读器顶栏文档标题增加悬浮气泡（Tooltip 卡片）与点击交互。
  - 解决标题过长被省略号截断（`Attentio...`）后无法展开查看的问题。
  - 气泡展示：论文完整英文名、中文译名、来源/会议标签、全部作者列表、页数大小与翻译模型。
- 改了哪些文件：`web/src/components/ReaderView.jsx`
- 没做完 / 已知问题：无
- 下一个接手的人先看：`web/src/components/ReaderView.jsx`

## 2026-10-21 Claude（目录重排验证）

- 验证样本：Buckley 干净英文原版第 2 页（16 条目录，页码 56–68）
- 结果：层级缩进、点线、右对齐页码全部恢复；条目不再合并
- 实现：toc_fix 解析器兼容整行 span；目录标题默认 Bing，正文仍 DeepSeek
- 已知：作者名仍按原逻辑音译（未改）

## 2026-10-21 Codex（pdf2zh-next 后端迁移）

- 做了什么：
  - 经用户确认，真实服务改用 `pdf2zh_next.high_level.do_translate_async_stream()`（2.9.0 / BabelDOC 0.6.2），旧 `pdf2zh` 不再作为服务依赖。
  - 保持现有 HTTP 请求字段和 SSE 结构；将引擎总进度映射为 current/total 百分比，支持无事件时的取消。
  - 保留旧配置键与 21 个服务；OpenCode Go 通过任务级 loopback 转发补充必需请求头。移除新版不支持的 Argos / DeepLX 可选项，旧配置不删除；不可用的历史默认服务回退显示 Bing。
  - 适配选页、术语库 CSV、自动术语提取、表格文字和扫描件白底选项；不支持术语功能的引擎通过 status 明确报告跳过。
  - 保持 mono / 交替页 dual / side_by_side 三种下载；退出旧版 fidelity / TOC / crop 专用后处理，由新引擎处理排版。
  - `.venv312` 已装新依赖，移除与新版 BabelDOC 冲突的旧发行包 pdf2zh 1.9.11，并约束 bitstring<5；未修改旧内核源码、前端或用户凭证。
- 改了哪些文件：
  - `server/services/translate.py`、`next_engine.py`、`opencode_proxy.py`、`credentials.py`
  - `server/api/settings.py`、`server/config.py`、`server/requirements.txt`、`server/AGENTS.md`
  - `server/tests/test_api.py`、`test_next_engine.py`、`test_opencode_proxy.py`
  - `docs/DECISIONS.md` D-013、`docs/pdf2zh-next/**`、本文件。没有新增接口，`docs/openapi.json` 无需变更。
- 验证：
  - `.venv312/bin/python -m pytest server/tests -q`：44 passed；Python 3.14 mock 环境：8 passed、1 skipped（真实引擎测试）。两者各有一个现有依赖弃用警告。
  - `uv pip check --python .venv312/bin/python`：所有依赖兼容；`compileall` 和 `git diff --check` 通过。
  - 实际 Bing + BabelDOC：两页样本文档只翻第 2 页，mono/dual/side_by_side 为 1/2/1 页，译文均可提取到 322 个汉字。
  - 启动实际 Uvicorn，上传 → SSE(status/progress/done) → 查询 → 三种 PDF 下载通过；另一个真实任务取消后进入 cancelled。使用隔离数据目录，验证服务已关闭。
- 没做完 / 已知问题：
  - 真实运行要求 Python 3.11–3.13，默认 `.venv` 的 Python 3.14 仅用于不加载引擎的 mock；当前启动使用 `.venv312`。
  - 未验证全部付费服务的在线可用性；OpenCode Go 转发使用本机模拟上游验证，未调用私人 Key。
  - 复杂公式、目录、扫描件、Windows 打包环境需专项回归；新版排版与旧定制补丁不保证逐项一致。
  - 段落捕获/ReaderView 内容接口保持原来未实现状态，未额外扩展。
- 下一个接手的人先看：`docs/pdf2zh-next/README.md`（安装、启动、行为映射）、D-013、`server/AGENTS.md`。此前 STATUS 中旧内核的启动和 hook 方案属于历史记录。

## 2026-10-21 Claude（清理旧引擎）

- 删除 `core/site-packages/pdf2zh/`、`pdf2zh-1.9.9.dist-info`、`server/services/fidelity.py`
- 确认 `server/` 已无旧 `pdf2zh` 引用；`.venv312` 中也无旧包
- `server/tests` 44 项全部通过
- 待处理：`ui/translate_worker.py`、`_launcher.py` 仍引用旧引擎，已是死代码

## 2026-10-21 Codex（Gemini 前端对接）

- 做了什么：
  - 按用户授权及 D-014 跨目录对接 Gemini 页面，保留现有组件布局、配色、字号与样式。
  - TranslateView 使用原生 File/FormData 和后端语言/服务 ID，EventSource 驱动真实进度；支持错误提示、取消、后台切页、断线重连和刷新恢复。
  - LibraryView 使用真实历史，支持搜索、打开、下载和持久删除；删除后清理对应页面选择。
  - SettingsView 使用真实服务配置，Key 空白保留/明确清除，保存不回显；术语库增删即时持久化。修正环境 Key 的 has_key 和 Ollama 无需 Key 的状态。
  - 用户确认 Reader 先接真实 PDF：原文/译文、页面映射、缩放、标题气泡和导出均对接实际任务；移除示例论文与模拟进度，只保留静态引用语句。
  - Next 同源代理支持开发/常规生产服务；静态导出可由 FastAPI 直接提供页面，实现单服务使用。
  - 已关闭隔离验证服务与浏览器，并用正常配置启动实际服务 `http://127.0.0.1:8000`，页面和 API 健康检查均通过。
- 改了哪些文件：
  - `web/src/app/page.jsx`、Translate/Reader/Library/Settings/Sidebar/Navbar、`web/src/lib/api.js`、`web/src/data/mockData.js`、`web/next.config.js`
  - `server/api/jobs.py`、`server/services/credentials.py`、`server/tests/test_api.py`
  - `docs/openapi.json`、`docs/DECISIONS.md` D-014、`docs/frontend-integration/**`、本文件。
- 接口契约：
  - 现有下载支持 `kind=original` 和 `inline=true`；默认仍为附件。历史原文按持久化任务目录读取，服务重启后可用。
  - SSE 接受 `Last-Event-ID`，支持原生 EventSource 断点重连；契约已导出，无新增 HTTP 路由。
- 验证：
  - `npm run build` 以及 `PDF2ZH_STATIC_EXPORT=1 npm run build` 均通过。
  - Python 3.12 后端：47 passed；Python 3.14 mock：11 passed、1 skipped。各有一个既有依赖弃用警告。
  - 浏览器验证上传失败、SSE 完成、PDF 模式/导出、历史搜索/打开/删除、切页后台任务、刷新、断线重连、取消、Key 与术语持久化，以及删除当前任务后的选择清理。
  - 静态页面 + 实际 Bing/BabelDOC：两页输入只翻第 2 页，三种产出为 1/2/1 页、322 个汉字，Reader 对应原文第 2 页/译文第 1 页。真实服务重启后再次验证历史预览。
  - 原文重启读取的回归测试曾复现 source_path KeyError，修复后通过；compileall / diff 检查通过。
  - 测试配置与数据使用隔离目录，未修改实际用户凭证；日志、PDF、截图和构建产物均留在被忽略的目录。
- 没做完 / 已知问题：
  - 按用户确认范围，段落联动/高亮/公式内容仍待后端数据接入；当前阅读真实 PDF。
  - 未验证全部付费服务、Zotero 旧插件协议和 Windows 打包环境。
  - 正常配置服务需使用 Python 3.11–3.13；前端重建后需保留 `web/out`，该产物不入库。
- 下一个接手的人先看：`docs/frontend-integration/README.md`（启动方式与契约）、D-014、`docs/openapi.json`。

## 2026-10-21 Codex（macOS 桌面入口修复）

- 做了什么：确认用户截图来自旧 PyInstaller/PyQt 2.3.37 安装包，补上 Swift + AppKit/WKWebView 原生入口，连接 Gemini 静态页面和真实 pdf2zh-next 后端。已有真实 8000 服务时复用，否则自动启动随机 loopback 端口的私有服务；退出只清理自己的服务和进程组。实现原生选 PDF、JS 确认和下载保存代理。
- 改了哪些文件：`scripts/macos_app.swift`、`scripts/build_macos_app.py`、`server/desktop.py`、`server/tests/test_desktop.py`、D-015、`docs/macos-launcher/**`、本文件。没有新增 HTTP 接口或修改前端视觉。
- 安装：已打开 `/Applications/pdf2zh.app`（启动壳 3.0.0），编译和本地签名验证通过。安装时旧包已不在 Applications，在废纸篓找到旧 2.3.37，额外复制到 `~/Library/Application Support/pdf2zh/backups/pdf2zh-2.3.37-from-Trash-20261021.app`，未动废纸篓原件。正常服务恢复于 8000，供已有网页与 App 使用。
- 验证：后端 50 passed，1 个既有依赖弃用警告。新 App 实际进程的 WebKit 主页面导航完成；后端日志显示页面、JS/CSS 和真实 API 加载。已验证服务复用及退出保留、冷启动自建真实服务及退出清理；安装备份和复制失败恢复有测试。
- 没做完 / 已知问题：这是依赖当前仓库、`.venv312` 和 `web/out` 的本机开发包，未捆绑运行时、未做独立分发或公证。电脑控制工具没有权限，原生文件选择/保存、JS 确认和内嵌 PDF 的实际点击验收未完成；此前网页验收不能替代它。不可再用网页成功笼统宣称桌面 App 全部可用。
- 下一个接手的人先看：`docs/macos-launcher/README.md`（构建、日志、回滚和验证边界）、任务计划中未勾选项。

## 2026-10-21 Codex（服务名称英文）

- 做了什么：按截图去掉服务名称中的中文，显示为 Zhipu、SiliconFlow、Ollama、Tencent、OpenAI Compatible、Qwen-MT。
- 改了哪些文件：`server/services/credentials.py`、D-016、本文件。保留历史配置 prefix 和服务 ID，未修改前端样式、用户设置或 HTTP 契约。
- 验证：API 测试 10 passed；重启正常 8000 服务，实际 `/api/settings` 返回的全部 21 个服务名均为英文。无需重建前端或 App，已有页面刷新后读取新名称。
- 没做完 / 已知问题：本次名称调整无遗留；桌面原生交互的既有验收限制见上一条。
- 下一个接手的人先看：`server/services/credentials.py` 的 name 与 prefix 用途不同，不要为调整显示名而修改配置键。

## 2026-10-21 Codex（排版格式多选）

- 做了什么：按用户要求将三个排版按钮改为独立多选，沿用样式，aria-pressed 表达选择状态；最后一项不可取消。初始选择来自后端默认值，实际请求只提交勾选格式，不再合并未选中的默认格式。
- 改了哪些文件：`web/src/components/TranslateView.jsx`、D-017、`docs/frontend-integration/README.md`、本文件。没有修改后端接口或用户全局设置。
- 验证：静态生产构建通过。隔离 mock 服务与 Playwright 浏览器验证 mono 单选、mono+dual 双选、三种全选；各次提交参数、完成文件集合与选择完全一致，文件均可下载为 PDF，最后一项不可取消。正常真实服务 8000 已加载新页面，三个默认格式均高亮。
- 没做完 / 已知问题：本次多选修改无遗留；未重复调用真实翻译引擎，因为引擎与输出处理均未修改。桌面原生交互的既有限制仍见 macOS 入口记录。
- 下一个接手的人先看：D-017、TranslateView 中 layoutModes 与 output_formats 的直接映射。验证产物在被忽略的 `pdf2zh_files/layout-multiselect/`。

## 2026-10-21 Codex（项目更名 translator）

- 做了什么：按用户明确要求，将当前产品名统一为小写 translator，更新网页侧栏/导航/About/标题、npm 包名及锁文件根名称、项目元数据、API/OpenAPI 标题、OpenCode 请求 User-Agent 和 macOS 包/可执行文件/菜单。项目目录大小写改为 `/Users/shiyun/Desktop/translator`，原大小写路径仍兼容。中英文 README 增加当前项目入口，将原文明确标为上游旧版资料。
- 改了哪些文件：`web/src/app/layout.jsx`、Sidebar/Navbar/AboutView、`web/package*.json`；`config/app.json`；`server/config.py`、`server/services/opencode_proxy.py` 及其现有测试；`scripts/build_macos_app.py`、`scripts/macos_app.swift`；根 README 中英文、OpenAPI、D-018、`docs/rename-translator/**`、前端/macOS 使用说明及本文件。
- 兼容：保留真实 pdf2zh-next 依赖名、PDF2ZH_*、历史配置前缀、pdf2zh_files、浏览器存储键和原 bundle ID；未修改 Git remote、用户凭证或翻译记录。旧版脚本、插件协议及上游链接保留原归属。
- 验证：静态生产构建通过；后端 50 passed、1 个既有依赖弃用警告。浏览器验证新标题、侧栏/导航、About、插件路径和多选；API 元数据与文档一致（静态页面替代条件性 JSON 根路由）。新 macOS 包编译、签名和实际 WebKit 加载通过，安装包元数据与项目绝对路径正确，正常真实服务仍使用原数据目录。
- 安装：已安装并打开 `/Applications/translator.app`，旧生成包归档至 `~/Library/Application Support/pdf2zh/backups/pdf2zh-launcher-before-translator-20261021.app`。真实服务已用新名称重启于 8000。
- 没做完 / 已知问题：仍为本机开发 App，不是独立分发包；原生文件弹窗/PDF 预览的既有验收限制不变。没有修改旧 Windows/PyQt 入口为新版产品或重命名远端仓库。
- 下一个接手的人先看：`docs/rename-translator/README.md`、D-018；当前根 README 是启动入口，历史上游说明不能当作新包发布说明。

## 2026-10-21 Codex（translator 图标设计）

- 做了什么：按用户要求设计新的双文档图标，使用暖白、陶土橙、深灰和相连纸带表达原文/译文。内置 imagegen 生成；两次透明稿外缘有杂点，最终交付干净的不透明方形设计母版。
- 改了哪些文件：新增 `assets/translator-icon-v1.png`、`docs/translator-icon.md`（最终提示词、方式与导出边界）；追加 D-019 和本文件。
- 验证：目视检查主体、无文字和画布边缘；Pillow 只读解码验证 PNG 完整、正方形，原样复制入项目，未用 Python 编辑图片。
- 没做完 / 已知问题：本次为设计交付，尚未导出圆角透明遮罩、ICNS 或替换现有 App 图标；现有资源/安装包均未覆盖，未声称已完成 Dock 小尺寸实机验收。
- 下一个接手的人先看：`docs/translator-icon.md` 和新 PNG；若用户选定方案，再做各平台导出与安装更新。

## 2026-10-21 Codex（Gemini C1 圆角预览）

- 做了什么：读取 Gemini 的 C1 PNG/SVG 与规范；按用户要求用内置 imagegen 将书页外角、底部边缘、书签末端变圆润，保留黑白双页、陶土橙书签和原构图。
- 改了哪些文件：新增 `assets/translator-icon-c1-rounded-preview.png`、`docs/translator-icon-c1-rounded.md`；追加 D-021、本文件。没有修改 Gemini 未提交的 `assets/icon.png` 与 `assets/icon.svg`，未覆盖平台资产或安装包。
- 验证：目视对比圆角变化，Pillow 只读验证生成 PNG 可解码，1254 × 1254 RGBA；新图原样复制进项目。
- 没做完 / 已知问题：当前为预览，外缘透明区有生成杂点，未做平台导出或小尺寸/原生显示验收；保留 Gemini 原有未提交修改，不将它们混入本次提交。
- 下一个接手的人先看：新预览与修改说明；用户认可后再清理边缘并导出平台资源。

## 2026-10-21 Codex（论文文献变体）

- 做了什么：按用户要求保留已认可的圆角书卷，新增更接近学术文献的薄双页方案；去掉书脊和层叠厚度，加入双栏正文骨架、短橙标记，并恢复外框完整顶部圆角。
- 改了哪些文件：新增 `assets/translator-icon-paper-preview.png`、`docs/translator-icon-paper.md`；追加 D-022、本文件。已有书卷、Gemini 原稿、平台资源均未覆盖。
- 验证：目视对比薄页/双栏/外框四角，Pillow 只读验证 PNG 完整，1254 × 1254 RGBA；确认原圆角书卷文件仍在。
- 没做完 / 已知问题：当前为视觉比较稿，透明区仍有零散杂点，未导出或安装；保留他人原有未提交文件状态。
- 下一个接手的人先看：两种预览及各自说明，等待用户比较选择后再做平台资产。

## 2026-10-21 Codex（保留轮廓的轻微精简稿）

- 做了什么：用户否定双栏文献稿后，以原来认可的圆角书卷重新生成，保留稀疏横线与整体轮廓，仅削薄底部厚度、缩短书签。
- 改了哪些文件：新增 `assets/translator-icon-c1-refined-preview.png`；在圆角版说明中追加对应提示词；追加 D-023、本文件。原来认可的预览未改动。
- 验证：目视确认回归原轮廓与少量横线，Pillow 只读解码验证 1254 × 1254 RGBA。
- 没做完 / 已知问题：仍为视觉预览，透明杂点未清理，不作为最终平台资产；未替换安装包，保留 Gemini 未提交改动。
- 下一个接手的人先看：圆角原版与 refined 预览，用户对本次微调尚未确认。

## 2026-10-21 Codex（图标视觉定稿）

- 做了什么：用户回复“就这个吧”，将 `assets/translator-icon-c1-refined-preview.png` 锁定为最终视觉方案，保留前面的圆角原稿。
- 改了哪些文件：D-024、本文件、圆角图标说明及 C1 设计规范中的最终选择说明；未修改图片或他人未提交的资源。
- 验证：确认选定 PNG 文件存在且可解码，原圆角稿保留。
- 没做完 / 已知问题：视觉设计阶段已选定；外缘清理、平台图标导出与安装替换未进行，不宣称 App 图标已更新。
- 下一个接手的人先看：D-024 和选定图稿；平台导出时保持其轮廓、稀疏排版和短橙书签。

## 2026-10-21 Codex（清理旧图标候选）

- 做了什么：按用户要求删除之前的圆角原稿和已否定的双栏文献候选，保留最终选定 refined 图稿；说明文档明确旧图已删除。
- 改了哪些文件：删除 `assets/translator-icon-c1-rounded-preview.png`、`assets/translator-icon-paper-preview.png`；更新两份设计说明、D-025、本文件。
- 验证：两张旧候选不存在，最终选定 PNG 可正常解码；App 构建依赖的 ICNS 等现有资源仍在。
- 没做完 / 已知问题：不涉及代码、平台导出或安装替换；Gemini 原有未提交 PNG/SVG 保持原样，历史决策与生成记录保留。
- 下一个接手的人先看：最终图 `assets/translator-icon-c1-refined-preview.png`，按此图进行后续平台导出。


## 2026-10-21 Codex（独立 App、字体及构建缓存修复）

- 做了什么：完成选定图标的平台导出和前端品牌引用，增加可搬移 Python/API 依赖/前端/引擎资源打包；按用户确认保留 15 个中英文/通用字体并同步过滤引擎引用。去除网页模拟窗口按钮，保留系统控件；OpenCV 已按用户要求恢复 5.0.0.93。
- 改了哪些文件：scripts/build_macos_app.py、macos_app.swift、release_bundle.py、font_profile.py、export_app_icons.swift；server/desktop.py、desktop_assets.py、requirements.txt、requirements-macos.lock、tests/test_release.py；平台图标与 web/public 图标；Sidebar.jsx、layout.jsx；README 和 docs/macos-release。
- 验证：前端生产构建通过，后端 63 项测试通过；此前移出项目的 15 字体版本完成真实 Bing 英译中及三格式下载，空 HOME 缓存仅出现白名单字体。静态库/CPU 切片精简和深度签名验证通过。
- 构建问题：首轮依赖复制范围过大；一次 -I 导入自检曾因环境变量被忽略而产生约 40 MiB 字节码，已改显式 -B，增加成品缓存/私有数据阻断。构建副本、wheel 探测、开发 .next 不属于 App 内容，将清理本次会话产生的临时项。
- 没做完 / 已知问题：最终 OpenCV 5.0 + 窗口按钮修复版正重建，安装/图标替换和最终冒烟结果后续追加。签名为 ad-hoc，未公证；原生文件选择/保存弹窗尚无电脑控制权限实点验收。GitHub 未推送；历史扫描在旧版前端发现一个带遮罩的 Key 前缀字面量，发布历史仍需处理/复核，不暴露值。
- 下一个接手的人先看：docs/macos-release/README.md、D-026 至 D-030 和同目录 task_plan.md；保留用户已有 ~/.config/pdf2zh、历史和引擎缓存；assets/icon.svg 是原有未跟踪稿，不纳入本次发布提交。


## 2026-10-21 Codex（完成安装与缓存核查）

- 做了什么：最终 OpenCV 保持 5.0.0.93；独立 App 已安装到 /Applications/translator.app 并重新打开。选定图标通过安装后摘要核对；图标资源名改为 TranslatorIcon.icns，构建号 3.0.1。网页模拟窗口按钮已移除，浏览器 DOM 检查数量为 0。
- 验证：最新前端生产构建通过；后端 63 项测试通过。使用已安装 App 的解释器、全新 HOME/缓存完成真实 Bing 英译中和中译英、各三种格式，验证页数/文字及常用中英/希腊/数学符号。原历史及原文/译文下载通过。上次退出已关闭私有端口并删除 readiness 文件；删除构建环境后 App 仍独立启动。
- 体积：已安装 App 磁盘占用 656,876 KiB（约 641.5 MiB），文件内容 646,525,263 字节；分发 ZIP 305,181,982 字节（约 291.0 MiB）。App 内字节码/开发缓存/用户数据库数量为 0。压缩资源解包后的运行缓存另计，既有引擎缓存保留。
- 清理：删除本会话的 3 个测试 App 副本、wheel/压缩探测、web/.next、.venv-release、重复构建 App 和隔离 QA 缓存；保留已安装 App、单一 ZIP/校验报告、原图资源备份、用户配置/历史和旧安装回滚备份。后续构建需按发布说明重建 .venv-release。
- 代码与发布：App 由 8b2d755 构建；后续提交仅补充所有构建探测的 -B 标志和最终验证记录。GitHub origin 已配置为 jmjFortune/translator，未推送或创建 Release。当前源码变更的凭证扫描通过；历史中的带遮罩 Key 前缀尚需复核后再决定发布历史。保留原有未跟踪 assets/icon.svg。
- 已知边界：ad-hoc 本地签名，未公证；Apple Silicon/macOS 15+；原生选文件/保存弹窗没有电脑控制权限实点验收。详情见 docs/macos-release/README.md 和构建报告。


## 2026-10-21 Codex（核心项目清理与推送准备）

- 做了什么：按用户要求移出旧版 BAT/VBS/EXE、PyInstaller/Qt 入口、mac 镜像、宣传站点/旧教程、重复 XPI/平台图标、旧模型/字体及不再使用的配置清单。61 个旧路径已归档到本地 Application Support/translator/project-archive/cleanup-20261021-193523.noindex；清理前历史仍在 agent/codex/macos-release。
- 保留核心：web、server、两个 ui 配置/术语库模块、8 个开发/构建脚本、当前 3 个图标源/平台资源、必要 docs 和 tests。插件只保留当前页面下载的一个 XPI，匹配的源码移到 integrations/zotero。用户配置、PDF/历史、已安装 App、开发依赖与 Git/Jujutsu 元数据保留。
- 改了哪些文件：重写 README/.gitignore/.gitattributes，新增 NOTICE、docs/development.md、docs/macos.md 和 requirements-dev.txt；删除旧路径，移除 ui/config_manager.py 的零调用骰子/旧历史类，图标脚本不再生成已删除的 Windows/冗余图标；前端视觉和接口不改。
- 验证：后端 63 项测试通过；前端静态生产构建通过；Swift 脚本类型检查与隔离图标导出通过；实际后端打包复制与缓存阻断通过；当前插件源码与 XPI 内容一致，活动 Markdown 本地链接检查通过。
- 没做完 / 已知问题：即将以精简后的独立初始快照推送空 GitHub 仓库，历史中的旧遮罩凭证和删除的旧大文件不进入该快照。旧历史保留在本地，不强推；不会推送用户数据或 App ZIP。Zotero 新版自动回写仍未联调；App 本地签名未公证等既有边界不变。
- 下一个接手的人先看：README、docs/development.md、docs/macos.md 和 D-031；本地清理计划/归档清单位于被忽略的 pdf2zh_files/project-cleanup。


## 2026-10-21 Codex（源码与依赖精简，GitHub 已建立）

- 做了什么：初始核心源码快照 7b1ddd9 已成功推送并在 GitHub 核对，远端分支为 agent/codex/translator-core；仅当前源码进入该历史。继续按用户要求精简当前代码，保留翻译/取消/SSE、三种格式、历史、真实 PDF、配置、术语库及 Zotero 下载。
- 改了哪些文件：web/package.json 与 lock 删除 4 个未使用直接依赖和 2 个独占间接依赖，保留依赖的已解析版本不变；globals.css/Tailwind 仅清理无引用或无效定义。GlossaryManager 从 184 行缩到 53 行，清除旧 Qt 文件导入导出/替换方法及不可达预设词条，仅保留 API 使用的名称；删除未使用的事件模型、段落写入助手、无效参数、导入与重复 server/run.py，开发启动统一 uvicorn。同步 development、D-032 和本文件。
- 验证：后端 63 项测试通过；Next.js 静态生产构建通过；npm ci 锁文件预检通过。按与契约导出相同的 API-only 条件逐字段比较，全部 14 个 OpenAPI 路径和 schema 一致；静态挂载模式仅隐藏原有根路径提示接口。生成样式的 AST 排除已核实无用的声明后完全相同，前端组件和交互代码未改。
- 清理结果：当前入库文件 76 个（最初 177 个），约 4.3 MB（最初约 25.2 MB）；本轮删除约 300 行冗余内容。缓存、虚拟环境、用户数据、模型和构建产物不入库；旧资源仍可从归档恢复，已有配置/历史不动。OpenCV 继续保留 5.0.0.93。
- 没做完 / 已知问题：本轮为源码/开发依赖清理，已安装 App 和分发 ZIP 未重建，体积仍以上次构建报告为准。段落对照、Zotero 新版回写、Apple 公证等既有边界见 development/macos；没有新增 API 或功能。
- 下一个接手的人先看：README、docs/development.md、docs/macos.md、D-031/D-032；后续源码继续在 agent/codex/translator-core 普通快进提交/推送，不推 main、不强推。

## 2026-10-21 Codex（GitHub Actions 适用性评估）

- 做了什么：检查现有测试、静态前端构建与 macOS 打包流程；当前没有 Actions workflow，建议先接 PR/推送时的后端 mock 测试和静态前端构建，再按需接手动 macOS ARM64 打包。
- 改了哪些文件：仅本交接记录；未新增 workflow、修改代码或触发发布。
- 没做完 / 已知问题：本次仅评估，未执行构建/测试；云端打包仍需核实 runner 架构、依赖和资源下载，Apple 签名/公证需另行配置。
- 下一个接手的人先看：README、docs/macos.md、server/requirements-dev.txt；实施 .github/workflows 前按根 AGENTS.md 追加跨目录决策。

## 2026-10-21 Codex（接入 GitHub Actions CI）

- 做了什么：按用户确认新增 CI，分支 push、PR 和手动触发两个并行 Ubuntu job：Python 3.12 的后端 mock/引擎桩测试，以及 Node.js 22 的前端静态生产构建；配置包下载缓存、只读权限、20 分钟超时与旧运行自动取消。
- 改了哪些文件：`.github/workflows/ci.yml`、`docs/development.md`、`docs/superpowers/specs/2026-10-21-github-actions-design.md`、D-033、本文件；没有新增 API。
- 验证：本机 Python 3.12.13 后端 63 项测试通过（1 项现有依赖弃用警告）；Node.js 22.23.3 / npm 10.9.9 下 npm ci 与静态生产构建通过；actionlint 1.7.12 与 git diff --check 通过。GitHub 仓库 Actions 已启用；云端结果待推送后追加。
- 没做完 / 已知问题：本次没有 macOS 云端打包、签名、公证或发布，也未改分支保护。npm ci 报告现有依赖 9 项漏洞（2 moderate、6 high、1 critical），包含 Next.js 14.2.15 的升级提示；本次未扩大范围升级依赖。
- 下一个接手的人先看：`.github/workflows/ci.yml` 和 docs/development.md 的 GitHub Actions 小节；默认分支仍为 agent/codex/translator-core，不直接改 main、不强推。

### GitHub 推送结果

- CI 配置已提交为 `a764512`，但 GitHub 拒绝普通推送：当前 OAuth 凭证没有 `workflow` scope，不允许创建 `.github/workflows/ci.yml`。远端没有本次 workflow，首次云端运行尚未发生。
- 需用户在终端运行 `gh auth refresh -h github.com -s workflow` 并完成 GitHub 授权，再执行 `git push origin HEAD:agent/codex/translator-core`；随后查看 `gh run list --workflow ci.yml`。本次没有改变凭证权限或改用其他方式绕过拒绝。
