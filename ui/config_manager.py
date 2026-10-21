"""用户配置与旧版路径迁移 — 持久化到 ~/.config/pdf2zh/ 目录"""

import json
import base64
import shutil
from pathlib import Path


def _config_dir():
    """统一配置目录 ~/.config/pdf2zh/，首次使用自动创建 + 迁移旧文件"""
    d = Path.home() / ".config" / "pdf2zh"
    d.mkdir(parents=True, exist_ok=True)
    # 自动迁移旧版散落在 ~/ 下的配置文件
    _migrations = {
        "pdf2zh_gui_config.json": "config.json",
        "pdf2zh_history.json": "history.json",
        "pdf2zh_glossary.json": "glossary.json",
        "pdf2zh_prompts.json": "prompts.json",
    }
    for old_name, new_name in _migrations.items():
        old = Path.home() / old_name
        new = d / new_name
        if old.exists() and not new.exists():
            shutil.move(str(old), str(new))
    # 迁移术语库目录
    old_gdir = Path.home() / "pdf2zh_glossaries"
    new_gdir = d / "glossaries"
    if old_gdir.exists() and not new_gdir.exists():
        shutil.move(str(old_gdir), str(new_gdir))
    return d


class UserConfigManager:
    """用户偏好配置（翻译服务、语言、线程、分块等）"""

    @staticmethod
    def path():
        return _config_dir() / "config.json"

    @classmethod
    def load(cls):
        p = cls.path()
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    @classmethod
    def save(cls, cfg: dict):
        p = cls.path()
        p.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
        try:
            p.chmod(0o600)  # 配置里有 API Key，只允许当前用户读写
        except OSError:
            pass

    @staticmethod
    def encode_sensitive(v: str) -> str:
        return base64.b64encode(v.encode()).decode()

    @staticmethod
    def decode_sensitive(v: str) -> str:
        try:
            return base64.b64decode(v).decode()
        except Exception:
            return ""
