# GitHub Actions CI

用户已同意先接后端测试和前端静态构建，macOS 打包留待后续。

使用单个 `.github/workflows/ci.yml`，在分支 push、pull_request 和手动 workflow_dispatch 时执行。两个独立 Ubuntu job 并行运行，分别显示 `Backend tests` 与 `Frontend build`。

- 后端：Python 3.12，安装 `server/requirements-dev.txt`，设置 `PDF2ZH_MOCK=1`，执行 `python -m pytest server/tests -q`。安装完整引擎依赖，已有引擎测试以 stub 替代翻译流；不预热模型或使用用户 Key。
- 前端：Node.js 22，工作目录为 `web`，按 `package-lock.json` 执行 `npm ci`，设置 `PDF2ZH_STATIC_EXPORT=1` 并运行 `npm run build`。
- 每个 job 最长 20 分钟，同一分支或 PR 更新时取消旧运行。仓库权限为 `contents: read`，checkout 不保留凭证；仅缓存 pip/npm 下载，不上传产物。

不使用路径过滤，以确保 PR 中始终有这两个检查。失败由 GitHub 显示具体步骤和日志，不自动修复、合并或发布。分支保护需另行设置；添加 workflow 本身不会禁止合并。

验证包括 Actions 配置静态检查、本机后端测试、按 lock 安装后的静态前端构建及提交前 diff 检查。本机验证不等于 Ubuntu runner 已验证；推送后需观察首次云端执行。
