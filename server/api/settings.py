"""Settings endpoints. Secrets are write-only: reads return has_key only."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..models import Defaults, ServiceOut, SettingsOut, SettingsPatch
from ..services.credentials import SERVICES, BY_ID, service_state
from ..services.translate import parse_formats

router = APIRouter(prefix="/settings", tags=["settings"])


def _load() -> dict:
    from ui.config_manager import UserConfigManager

    return UserConfigManager.load()


def _save(cfg: dict) -> None:
    from ui.config_manager import UserConfigManager

    UserConfigManager.save(cfg)


def _defaults(cfg: dict) -> Defaults:
    return Defaults(
        lang_in=cfg.get("lang_in", "en") or "en",
        lang_out=cfg.get("lang_out", "zh") or "zh",
        service=cfg.get("service") if cfg.get("service") in BY_ID else "bing",
        thread=int(cfg.get("thread", 4) or 4),
        output_formats=parse_formats(cfg.get("output_formats")),
    )


def _glossary_count() -> int:
    try:
        from ui.glossary_manager import GlossaryManager

        return len(GlossaryManager.load())
    except Exception:
        return 0


@router.get("", response_model=SettingsOut)
async def get_settings() -> SettingsOut:
    cfg = _load()
    return SettingsOut(
        services=[ServiceOut(**service_state(spec.id)) for spec in SERVICES],
        defaults=_defaults(cfg),
        glossary_count=_glossary_count(),
    )


@router.put("", response_model=SettingsOut)
async def update_settings(patch: SettingsPatch) -> SettingsOut:
    from ui.config_manager import UserConfigManager

    cfg = _load()

    for item in patch.services:
        spec = BY_ID.get(item.id)
        if spec is None:
            raise HTTPException(status_code=400, detail=f"未知翻译服务: {item.id}")
        if item.api_key is not None and spec.prefix:
            key_name = f"api_{spec.prefix}"
            if item.api_key:
                cfg[key_name] = UserConfigManager.encode_sensitive(item.api_key)
            else:
                cfg.pop(key_name, None)
        if item.base_url is not None and spec.prefix:
            value = item.base_url.strip()
            key_name = f"url_{spec.prefix}"
            if value:
                cfg[key_name] = value
            else:
                cfg.pop(key_name, None)
        if item.model is not None and spec.prefix:
            value = item.model.strip()
            key_name = f"model_{spec.prefix}"
            if value:
                cfg[key_name] = value
            else:
                cfg.pop(key_name, None)

    if patch.defaults is not None:
        if patch.defaults.service not in BY_ID:
            raise HTTPException(status_code=400, detail="默认翻译服务无效")
        cfg["lang_in"] = patch.defaults.lang_in
        cfg["lang_out"] = patch.defaults.lang_out
        cfg["service"] = patch.defaults.service
        cfg["thread"] = max(1, min(int(patch.defaults.thread), 32))
        cfg["output_formats"] = ",".join(parse_formats(patch.defaults.output_formats))

    _save(cfg)
    return await get_settings()
