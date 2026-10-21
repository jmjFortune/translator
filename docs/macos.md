# translator standalone macOS App

当前发行目标为 Apple Silicon、macOS 15+。界面使用 Swift/AppKit + 系统 WebKit，翻译引擎为 pdf2zh-next 2.9.0 / BabelDOC 0.6.2。App 包含 CPython 3.12.13、API 运行依赖、静态前端、模型和简化字体，不依赖源码目录或开发虚拟环境。OpenCV 保持 5.0.0.93。

## 构建

需 macOS、Xcode Command Line Tools、Node/npm、uv。以下命令从仓库根目录运行；如需重新导出图标，运行 `xcrun swift scripts/export_app_icons.swift`。

```bash
uv python install 3.12.13
uv venv --python 3.12.13 .venv-release
uv pip sync --python .venv-release/bin/python server/requirements-macos.lock --link-mode copy
cd web
npm ci
PDF2ZH_STATIC_EXPORT=1 npm run build
cd ..
# 只下载公开静态引擎资源；不需要用户 Key。
.venv-release/bin/python -c 'from babeldoc.assets.assets import warmup; warmup()'
.venv-release/bin/python scripts/build_macos_app.py
```

输出：`pdf2zh_files/release.noindex/translator.app`。添加 `--install` 可安装到 `/Applications/translator.app`，安装前退出正在运行的 App、等待翻译完成。原 App 备份到 `~/Library/Application Support/pdf2zh/backups/`。源码模式使用 `--development --python .venv312/bin/python`，仅供本机开发，不可独立分发。

图标来源为用户选定的 `assets/translator-icon-c1-refined-preview.png`，平台资产由 `scripts/export_app_icons.swift` 导出。发行包的图标文件名为 `TranslatorIcon.icns`，构建号为 3.0.1，显示版本为 3.0.0。

## 体积与缓存边界

- 从固定 lock 环境按 wheel 文件清单复制 API 依赖，排除 Gradio GUI、测试和字节码；上游未声明但 API 实际需要的 tomlkit 显式保留。
- 只保留当前 CPU 的原生代码切片。清理 pip、IDLE、Tcl/Tk 和 C/C++ 构建源文件；独立 C API 库只有在其他原生组件均未链接它时才排除。
- 构建自检使用 `python -I -B`。`-I` 会忽略禁止字节码的环境变量，因此不能仅依靠 PYTHONDONTWRITEBYTECODE。签名前拒绝 `__pycache__`、pyc、.next、node_modules、日志、数据库和用户配置。
- 只复制 `web/out`，不复制 `web/.next` 或 node_modules。开发虚拟环境、wheel 下载缓存、构建日志和测试 App 都在发行 App 外；不能把这些目录的总大小当作 App 大小。
- 模型、CMap、分词资源和 15 个字体以 ZIP/LZMA 完整内置；首次启动校验后写入 `~/.cache/babeldoc`，这是运行资源缓存，会额外占用磁盘，不是构建缓存。翻译缓存数据库和用户文档不入包。
- 字体简化白名单为简体中文、拉丁文字及 GoNoto 兜底，共 104.1 MiB 原始字体；同步过滤打包副本中的字体家族与下载元数据，避免后台重新下载已移除的日/韩/港/台专用字体。非中英文目标语言不再保证地区专用字形。

可用 `du -sh translator.app` 检查展开体积，用 `ditto -c -k --sequesterRsrc --keepParent translator.app translator.zip` 创建下载包；两个数字分别报告。源码和大体积二进制发布文件分开，App/ZIP/模型不提交 Git。

## 数据与服务

发行 App 总是启动自己的随机 loopback 端口，不复用开发端口 8000。退出时清理自有后端和翻译子进程。任务数据在 `~/Library/Application Support/translator/pdf2zh_files`；本机安装只复制旧任务历史和文档到这里，原文件保留，已有目标数据库不会被覆盖。既有 `~/.config/pdf2zh` 凭证保持原路径，不复制到 App。

日志在 `~/Library/Logs/pdf2zh/desktop-launcher.log` 和 `desktop-backend.log`。网页不再绘制模拟窗口按钮，只显示 macOS 的原生控件。

## 验证与发布边界

后端测试：`.venv312/bin/python -m pytest server/tests -q`。前端：`PDF2ZH_STATIC_EXPORT=1 npm run build`。构建脚本执行包内引擎导入、缓存阻断和 `codesign --verify --deep --strict`。真实冒烟检查需移出源码目录、使用全新 HOME/数据目录，完成翻译和三种格式下载，检查退出后服务端口关闭。

当前仅有 ad-hoc 本地签名，没有 Developer ID 签名或 Apple 公证；不能称为已公证的公开发行包。原生文件选择/保存弹窗未获电脑控制权限，不能以浏览器验证代替原生弹窗验收。源码仓库为 `https://github.com/jmjFortune/translator`。源码推送与 App 二进制发布分开，推送不会自动创建 Release。
