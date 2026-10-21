#!/usr/bin/env python3
"""Set or clear a translation service API key (optionally base URL / model).

Usage:
    python3 scripts/set_key.py                          # list service ids
    python3 scripts/set_key.py deepseek sk-...          # set key
    python3 scripts/set_key.py deepseek ""              # clear key
    python3 scripts/set_key.py openailiked sk-... \
        --url https://opencode.ai/zen/go/v1 \
        --model deepseek-v4.1-flash
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.services.credentials import BY_ID  # noqa: E402
from ui.config_manager import UserConfigManager  # noqa: E402


def list_services() -> None:
    print("可用服务:")
    for spec in BY_ID.values():
        mark = "需要 Key" if spec.needs_key else "无需 Key"
        print(f"  {spec.id:14} {spec.name:16} {mark}")


def main() -> int:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("service", nargs="?", help="service id")
    parser.add_argument("key", nargs="?", help="API key; empty string clears it")
    parser.add_argument("--url", help="OpenAI-compatible base URL (optional)")
    parser.add_argument("--model", help="model id (optional)")
    args = parser.parse_args()

    if not args.service:
        print(__doc__)
        list_services()
        return 0

    spec = BY_ID.get(args.service)
    if spec is None:
        print(f"未知服务: {args.service}", file=sys.stderr)
        return 1
    if not spec.prefix:
        print(f"{args.service} 不需要 API Key", file=sys.stderr)
        return 1

    cfg = UserConfigManager.load()

    if args.key is not None:
        field = f"api_{spec.prefix}"
        key = args.key.strip()
        if key:
            cfg[field] = UserConfigManager.encode_sensitive(key)
            shown = key[:4] + "..." + key[-4:] if len(key) > 10 else "***"
            print(f"已保存 {spec.name} 的 Key（{shown}）")
        else:
            cfg.pop(field, None)
            print(f"已清除 {spec.name} 的 Key")

    if args.url is not None:
        field = f"url_{spec.prefix}"
        if args.url.strip():
            cfg[field] = args.url.strip()
            print(f"Base URL: {cfg[field]}")
        else:
            cfg.pop(field, None)

    if args.model is not None:
        field = f"model_{spec.prefix}"
        if args.model.strip():
            cfg[field] = args.model.strip()
            print(f"Model: {cfg[field]}")
        else:
            cfg.pop(field, None)

    UserConfigManager.save(cfg)
    print(f"配置文件: {UserConfigManager.path()} (权限 600)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
