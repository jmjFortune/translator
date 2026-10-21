"""当前术语库 API 的 JSON 持久化与预设名称。"""

import json


PRESET_NAMES = ("学术通用", "计算机科学", "金融经济", "医学生物", "不使用术语库")


class GlossaryManager:
    """读写 ~/.config/pdf2zh/glossary.json，保持已有用户数据路径。"""

    @staticmethod
    def path():
        from ui.config_manager import _config_dir
        return _config_dir() / "glossary.json"

    @classmethod
    def load(cls):
        """加载当前激活的术语库"""
        p = cls.path()
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    @classmethod
    def get_preset_names(cls):
        return list(PRESET_NAMES)

    @classmethod
    def save(cls, glossary: dict):
        """保存术语库"""
        cls.path().write_text(
            json.dumps(glossary, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    @classmethod
    def add_term(cls, source: str, target: str):
        """添加一条术语"""
        g = cls.load()
        g[source] = target
        cls.save(g)

    @classmethod
    def remove_term(cls, source: str):
        """删除一条术语"""
        g = cls.load()
        if source in g:
            del g[source]
            cls.save(g)
