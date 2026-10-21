# AGENTS.md

本文件是本仓库对 AI agent 的**唯一权威约定**。子目录的 `AGENTS.md` 只能补充，不能覆盖这里的硬规则。

## 1. 角色与文件所有权

| 角色 | 可改目录 | 只读 / 禁止 |
|---|---|---|
| Gemini（前端） | `web/src/**`、`web/*.config.js`、`web/package.json` | `server/**`、`ui/**`、`core/**` |
| Claude / 当前会话（后端） | `server/**`、`ui/*.py`、`scripts/**` | `web/src/**` 的视觉与交互 |
| ChatGPT（方案/审阅） | `docs/**`（仅写方案与评审） | 任何代码、任何构建脚本 |
| 人类 | 全部，含合并与发布 | — |

跨目录修改必须先改 `docs/DECISIONS.md` 记录原因，再动手。

## 2. 项目结构

```
web/                     Next.js 14 前端（Gemini 产出，视觉层冻结）
server/                  FastAPI 后端（本次重写新增）
ui/                      保留的 Python 后端逻辑，禁止再加 UI 代码
core/site-packages/pdf2zh/   vendored 翻译内核，改动必须最小且有注释
config/                  运行时配置；config/user.json 不入库
docs/                    协作状态、决策、既有文档
```

## 3. 技术栈约束

- 后端：Python 3.11+ / FastAPI / Uvicorn / SQLite / SSE。不要引入 Celery、Redis、Django。
- 前端：Next.js 14 App Router + Tailwind。不要引入新的状态管理或 UI 框架。
- 接口契约以 `docs/openapi.json` 为准；前端不得臆造字段。
- 翻译内核：调用 `pdf2zh.high_level.translate()`，不要复制翻译逻辑。

## 4. 禁止事项

- 禁止提交任何 API Key、token、`.env`、`config/user.json`。
- 禁止 `git push --force` / `--force-with-lease`。
- 禁止直接提交到 `main`；所有改动走 `agent/<name>/<task>` 分支或 worktree。
- 禁止删除 `core/site-packages/pdf2zh/` 下的文件，除非在 `DECISIONS.md` 有记录。
- 禁止把 `web/node_modules`、`web/.next`、模型文件（`*.onnx`）提交入库。

## 5. 命令

```bash
# 前端
cd web && npm run dev        # http://localhost:3000
cd web && npm run build      # 合并前必须通过

# 后端（从仓库根目录运行；mock 模式不需要 pdf2zh）
PDF2ZH_MOCK=1 .venv/bin/python -m uvicorn server.main:app --reload --port 8000
.venv/bin/python -m pytest server/tests -q

# 起一个隔离工作区
scripts/agent.sh <task-name> <codex|gemini|opencode> ["prompt"]
```

## 6. 交接协议

每次工作结束前必须更新 `docs/STATUS.md`：

```markdown
## <日期> <agent 名>
- 做了什么：
- 改了哪些文件：
- 没做完 / 已知问题：
- 下一个接手的人先看：
```

决策写 `docs/DECISIONS.md`，**只追加，不修改历史条目**。

## 7. 完成定义（DoD）

- 改动可构建/可启动：`npm run build` 或后端能起。
- 新增接口写进 `docs/openapi.json` 并在 `docs/STATUS.md` 注明。
- 没有把临时文件、日志、密钥带入 diff。
- `git status` 干净（除有意保留的未跟踪文件）。
