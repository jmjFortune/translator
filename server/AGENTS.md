# server/AGENTS.md — 后端（Claude / 当前会话负责）

## 目标

把 `ui/` 里与 PyQt 绑定的逻辑改造成可被 Next.js 调用的 HTTP/SSE 服务。

## 结构约定

```
server/
├── main.py            # FastAPI 实例、静态文件挂载、CORS
├── api/               # 路由：jobs / papers / settings / glossary
├── services/          # translate.py（由 ui/translate_worker.py 改造）
├── jobs.py            # 任务队列、取消、进度广播
├── db.py              # SQLite（历史、任务、段落）
├── models.py          # Pydantic 请求/响应
└── requirements.txt
```

## 硬规则

1. 不 `import PyQt5`。原 `translate_worker.py` 的 `pyqtSignal` 一律换成回调或队列事件。
2. `translate()` 在独立线程执行；FastAPI 主线程不得阻塞。
3. 进度通过 SSE 推送，事件格式固定：
   `{"type":"progress|status|done|error","job_id":"...","current":1,"total":10,"message":"..."}`
4. 所有产出文件放在 `pdf2zh_files/<job_id>/`，不得写系统临时目录后依赖其存活。
5. 取消必须真正生效：设置 `cancellation_event`，并检查 `cancelled` 标志。
6. API Key 只从 `config/user.json` 或环境变量读取，绝不回传给前端明文（返回 `has_key: true/false`）。

## 当前翻译引擎（2026-10-21，用户授权迁移，见 D-013）

- 调用 `pdf2zh_next.high_level.do_translate_async_stream()`；异步循环运行在任务工作线程里，默认由上游隔离翻译子进程。
- 配置适配在 `services/next_engine.py`。保留服务 ID 和旧凭证字段；OpenCode Go 的任务级 header 转发在 `services/opencode_proxy.py`。
- `dual` 保持原文/译文交替页，通过 `use_alternating_pages_dual=True` 配置；`side_by_side` 再从交替页合成。
- 旧版专用的 fidelity / TOC / crop 后处理不再用于真实服务。不得重新调用旧 `pdf2zh` 作为隐式兜底。
- 段落对照目前尚未实现；后续通过新引擎提供的数据接入，不再修改旧 `converter.py` 挂 hook。
- 真实运行用 Python 3.11–3.13；开发启动方式与已验证范围见 `docs/pdf2zh-next/README.md`。
