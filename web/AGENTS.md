# web/AGENTS.md — 前端（Gemini 负责）

## 所有权

- 可改：`src/**`、`tailwind.config.js`、`postcss.config.js`、`package.json`
- 禁止：`server/**`、`ui/**`、`core/**`、根目录任何 `.py` / `.bat` / `.spec`

## 硬规则

1. **视觉与交互是已验收的基线**。改数据对接时，不要重写布局、配色、字号、间距；只替换数据来源和事件处理。
2. 所有 mock 数据必须来自 `src/data/mockData.js` 之外的 API 调用。删除某段 mock 前，先确认对应接口已在 `docs/openapi.json` 中。
3. 仅使用 `fetch` + 原生 hooks。不要引入 SWR / React Query / Redux / Zustand。
4. 组件保持 `"use client"`，不要改成 Server Component 后再依赖浏览器 API。
5. 文件上传走 `FormData`，字段名以 `docs/openapi.json` 为准。
6. 进度展示优先使用 `EventSource`（SSE），不要自己实现轮询。

## 本地命令

```bash
npm run dev     # 开发
npm run build   # 合并前必须通过
```

## 对接顺序

1. `TranslateView`：上传 → 创建任务 → 订阅进度 → 下载
2. `LibraryView`：历史列表、删除、重新打开
3. `SettingsView`：服务、Key、语言、输出格式
4. `ReaderView`：段落级对照（依赖后端 `content` 接口）

每完成一项，更新 `../docs/STATUS.md`。
