# 开发与运行

## 运行方式

- **静态前端 + 后端**：在 web 中运行 `PDF2ZH_STATIC_EXPORT=1 npm run build`，再从项目根启动 `.venv312/bin/python -m uvicorn server.main:app --port 8000`。FastAPI 直接服务 web/out。
- **前端开发**：先启动 8000 后端，再在 web 中运行 `npm run dev`，打开 3000。Next.js 将 /api 请求代理到后端。
- **无真实引擎的 API 演示**：加环境变量 `PDF2ZH_MOCK=1`。真实模式使用 Python 3.11–3.13 和 server/requirements.txt；测试另安装 server/requirements-dev.txt。
- **独立 macOS App**：见 [macOS 构建说明](macos.md)。已安装 App 不依赖源码、node_modules 或开发 Python。

## 核心边界

server/api 提供配置、术语库、任务和文献 API；server/jobs.py 管理线程队列、取消与 SSE 事件；server/db.py 持久化任务；server/services/next_engine.py 适配 pdf2zh-next 的配置和服务商。翻译运行调用 `pdf2zh_next.high_level.do_translate_async_stream()`，沿用上游独立翻译子进程。旧 pdf2zh/Qt 内核不作为回退。

后端只保留两个 ui 兼容模块：UserConfigManager 读写现有配置，GlossaryManager 读写术语库并提供预设名称。保留模块名和用户目录，避免升级丢失已有设置。

前端使用 fetch 与 SSE；服务字段以 [docs/openapi.json](openapi.json) 为准。新增或变更接口后运行 `.venv312/bin/python scripts/export_openapi.py` 并提交契约。

三种输出沿用 API ID：mono、dual、side_by_side。dual 对应页面中的 Interleaved；side_by_side 从交替页结果合成。用户选择的格式可以同时生成。

## 数据与凭证

| 内容 | 位置 |
|---|---|
| 源码运行的任务/文档 | 默认项目 pdf2zh_files；可由 PDF2ZH_DATA_DIR 指定 |
| 独立 App 的任务/文档 | ~/Library/Application Support/translator/pdf2zh_files |
| 既有服务配置与术语库 | ~/.config/pdf2zh |
| BabelDOC 公共资源/翻译缓存 | ~/.cache/babeldoc |
| 桌面启动日志 | ~/Library/Logs/pdf2zh |

API 只返回 has_key 状态，不向前端回传明文 Key。不要提交 config/user.json、.env、凭证、用户文档或数据库。用户数据与依赖/构建输出已被 .gitignore 排除。

## 保留的集成与限制

- About 页继续提供 Zotero 插件下载；公开的 XPI 与 integrations/zotero 对应源码一致。新版自动启动/回写链路尚未完成端到端验收，保留下载不代表该链路已联调。
- 阅读器使用真实 PDF。结构化段落对照数据仍未实现；内容接口不会伪造段落。
- 当前 macOS 字体配置保留简体中文、拉丁文字及通用兜底。日文、韩文和繁体专用字体不再随包附带，地区专用字形不作保证。
- 原生文件选择/保存弹窗尚未获得电脑控制权限实点验收；浏览器上传/下载验收不能代替原生弹窗验收。
- 当前本地 App 为 ad-hoc 签名，未经过 Apple 公证。

## 检查

```bash
.venv312/bin/python -m pytest server/tests -q
cd web
PDF2ZH_STATIC_EXPORT=1 npm run build
```

依赖、测试缓存、web/.next、node_modules、web/out 和 App/ZIP 都可重建，不进入源码提交。Windows 启动/构建支持已从当前核心项目移除。

## GitHub Actions

[CI workflow](../.github/workflows/ci.yml) 在每次分支推送、PR 创建/更新时并行执行：

- `Backend tests`：Ubuntu / Python 3.12，安装 `server/requirements-dev.txt`，以 `PDF2ZH_MOCK=1` 执行全部后端测试。真实引擎适配测试仍安装引擎依赖，翻译流使用 stub；不需要用户 API Key，也不预热模型或字体。
- `Frontend build`：Ubuntu / Node.js 22，在 `web` 中执行 `npm ci` 和 `PDF2ZH_STATIC_EXPORT=1 npm run build`。

到仓库的 Actions 页面查看日志；工作流进入默认分支后，也可选择 CI → Run workflow 手动运行。同一分支或 PR 的旧运行会被新提交取消，每个任务最多运行 20 分钟。仅缓存 pip/npm 下载，不上传产物。

本工作流不构建 macOS App、不签名/公证、不发布或部署，也不自动合并。需要阻止检查失败的 PR 合并时，由仓库管理员将这两个检查加入目标分支的保护规则。
