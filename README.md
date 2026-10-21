# translator

学术 PDF 翻译与阅读工具，使用 Next.js 前端、FastAPI 后端和 pdf2zh-next 翻译引擎。

支持翻译任务与进度、取消任务、历史记录、真实 PDF 预览、服务配置和术语库。输出可多选：**Mono**（仅译文）、**Interleaved**（原文/译文交替页）、**Side by Side**（左右并排）。

## 项目结构

```text
web/                  前端源码和实际使用的公开资源
server/               API、任务队列、数据库、翻译适配与测试
ui/                   配置/术语库兼容模块，不包含桌面 UI
scripts/              macOS App 构建、图标导出、接口导出及开发工具
assets/               选定图标原稿、PNG 和 macOS ICNS
integrations/zotero/  当前下载插件的对应源码
docs/                接口契约、开发/构建说明及决策记录
```

旧版 Windows/Qt 启动器、旧翻译内核、重复插件、宣传站点和内置旧模型已清理。模型与字体由构建脚本按 BabelDOC 的公开资源元数据校验准备，不存入 Git。

## 开发运行

需要 Python 3.11–3.13 和 Node.js/npm；已验证环境为 Python 3.12.13。以下命令使用 `uv`：

```bash
uv venv --python 3.12.13 .venv312
uv pip install --python .venv312/bin/python -r server/requirements-dev.txt
cd web
npm ci
PDF2ZH_STATIC_EXPORT=1 npm run build
cd ..
.venv312/bin/python -m uvicorn server.main:app --host 127.0.0.1 --port 8000
```

打开 [本地应用](http://127.0.0.1:8000)。服务商 API Key 在应用设置中填写。前后端开发模式及数据路径见 [开发说明](docs/development.md)。

```bash
# 后端测试
.venv312/bin/python -m pytest server/tests -q
# 前端构建
cd web && PDF2ZH_STATIC_EXPORT=1 npm run build
```

## macOS App

当前独立 App 目标为 **Apple Silicon / macOS 15+**，使用 Swift/AppKit + 系统 WebKit，内置 Python 与运行依赖。构建、安装、签名和资源策略见 [macOS 构建说明](docs/macos.md)。当前本地构建未经过 Apple 公证。

运行时配置、Key、用户 PDF、数据库、虚拟环境、模型和构建产物均不入库。数据位置及已验证边界见 [开发说明](docs/development.md)。

## 上游与协作

本项目基于 [pdf2zh-desktop](https://github.com/AaronGIG/pdf2zh-desktop) 整理迁移，翻译由 [PDFMathTranslate-next](https://github.com/PDFMathTranslate-next/PDFMathTranslate-next) 和 [BabelDOC](https://github.com/funstory-ai/BabelDOC) 提供。归属信息见 [NOTICE](NOTICE.md)。

接口以 [OpenAPI](docs/openapi.json) 为准；协作约定见 [AGENTS.md](AGENTS.md)，后续技术决策与交接记录保留在 [DECISIONS](docs/DECISIONS.md) 和 [STATUS](docs/STATUS.md)。
