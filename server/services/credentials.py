"""Translation service catalogue and credential resolution.

Config keys are the same ones the old GUI wrote to ``~/.config/pdf2zh/config.json``:
``api_<prefix>``, ``url_<prefix>``, ``model_<prefix>``. API keys are stored
base64-encoded by ``ui.config_manager.UserConfigManager``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ServiceSpec:
    id: str
    name: str
    needs_key: bool = False
    prefix: str = ""
    api_env: str = ""
    url_env: str = ""
    model_env: str = ""
    default_base_url: str = ""
    default_model: str = ""
    note: str = ""
    extras: tuple[tuple[str, str], ...] = field(default=())


SERVICES: tuple[ServiceSpec, ...] = (
    ServiceSpec("google", "Google", note="免费，无需 Key"),
    ServiceSpec("bing", "Bing", note="免费，无需 Key"),
    # Argos and DeepLX have no pdf2zh-next 2.9 engine. Keep their stored
    # configuration intact, but do not advertise unavailable services.
    ServiceSpec(
        "deepl", "DeepL", True, "DeepL",
        api_env="DEEPL_AUTH_KEY",
    ),
    ServiceSpec(
        "openai", "OpenAI", True, "OpenAI",
        api_env="OPENAI_API_KEY", url_env="OPENAI_BASE_URL", model_env="OPENAI_MODEL",
        default_base_url="https://api.openai.com/v1", default_model="gpt-4o-mini",
    ),
    ServiceSpec(
        "gemini", "Gemini", True, "Gemini",
        api_env="GEMINI_API_KEY", url_env="GEMINI_BASE_URL", model_env="GEMINI_MODEL",
        default_base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        default_model="gemini-1.5-flash",
    ),
    ServiceSpec(
        "deepseek", "DeepSeek", True, "DeepSeek",
        api_env="DEEPSEEK_API_KEY", url_env="DEEPSEEK_BASE_URL", model_env="DEEPSEEK_MODEL",
        default_base_url="https://api.deepseek.com", default_model="deepseek-v4-flash",
    ),
    ServiceSpec(
        "zhipu", "Zhipu", True, "Zhipu 智谱",
        api_env="ZHIPU_API_KEY", url_env="ZHIPU_BASE_URL", model_env="ZHIPU_MODEL",
        default_model="glm-4-flash",
    ),
    ServiceSpec(
        "silicon", "SiliconFlow", True, "Silicon 硅基流动",
        api_env="SILICON_API_KEY", url_env="SILICON_BASE_URL", model_env="SILICON_MODEL",
        default_base_url="https://api.siliconflow.cn/v1",
        default_model="Qwen/Qwen2.5-7B-Instruct",
    ),
    ServiceSpec(
        "groq", "Groq", True, "Groq",
        api_env="GROQ_API_KEY", url_env="GROQ_BASE_URL", model_env="GROQ_MODEL",
        default_base_url="https://api.groq.com/openai/v1",
        default_model="llama-3-3-70b-versatile",
    ),
    ServiceSpec(
        "grok", "Grok", True, "Grok",
        api_env="GROK_API_KEY", url_env="GROK_BASE_URL", model_env="GROK_MODEL",
        default_base_url="https://api.x.ai/v1", default_model="grok-2-1212",
    ),
    ServiceSpec(
        "ollama", "Ollama", False, "Ollama 本地",
        url_env="OLLAMA_HOST", model_env="OLLAMA_MODEL",
        default_base_url="http://127.0.0.1:11434", default_model="gemma2",
    ),
    ServiceSpec(
        "azure-openai", "Azure OpenAI", True, "Azure OpenAI",
        api_env="AZURE_OPENAI_API_KEY", url_env="AZURE_OPENAI_BASE_URL",
        model_env="AZURE_OPENAI_MODEL", default_model="gpt-4o-mini",
    ),
    ServiceSpec(
        "azure", "Azure Translator", True, "Azure",
        api_env="AZURE_API_KEY", url_env="AZURE_ENDPOINT",
        default_base_url="https://api.translator.azure.cn",
    ),
    ServiceSpec(
        "tencent", "Tencent", True, "Tencent 腾讯",
        api_env="TENCENTCLOUD_SECRET_ID",
        extras=(("TENCENTCLOUD_SECRET_KEY", "secret_key"),),
    ),
    ServiceSpec(
        "dify", "Dify", True, "Dify",
        api_env="DIFY_API_KEY", url_env="DIFY_API_URL",
    ),
    ServiceSpec(
        "anythingllm", "AnythingLLM", True, "AnythingLLM",
        api_env="AnythingLLM_APIKEY", url_env="AnythingLLM_URL",
    ),
    ServiceSpec(
        "opencode-go", "OpenCode Go", True, "OpenCode Go",
        api_env="OPENCODE_API_KEY", url_env="OPENCODE_BASE_URL", model_env="OPENCODE_MODEL",
        default_base_url="https://opencode.ai/inference/go/openai/v1",
        default_model="deepseek-v4.1-flash",
        note="OpenAI 兼容；需要 x-opencode-session",
    ),
    ServiceSpec(
        "openailiked", "OpenAI Compatible", True, "OpenAI 兼容",
        api_env="OPENAILIKED_API_KEY", url_env="OPENAILIKED_BASE_URL",
        model_env="OPENAILIKED_MODEL",
    ),
    ServiceSpec(
        "modelscope", "ModelScope", True, "ModelScope",
        api_env="MODELSCOPE_API_KEY", url_env="MODELSCOPE_BASE_URL",
        model_env="MODELSCOPE_MODEL",
        default_base_url="https://api-inference.modelscope.cn/v1",
        default_model="Qwen/Qwen2.5-32B-Instruct",
    ),
    ServiceSpec(
        "xinference", "Xinference", False, "Xinference",
        url_env="XINFERENCE_HOST", model_env="XINFERENCE_MODEL",
        default_base_url="http://127.0.0.1:9997", default_model="gemma-2-it",
    ),
    ServiceSpec(
        "qwen-mt", "Qwen-MT", True, "Qwen 通义千问",
        api_env="ALI_API_KEY", model_env="ALI_MODEL", default_model="qwen-mt-turbo",
    ),
)

BY_ID: dict[str, ServiceSpec] = {spec.id: spec for spec in SERVICES}


def _load_config() -> dict[str, Any]:
    from ui.config_manager import UserConfigManager

    return UserConfigManager.load()


def _decode(value: str) -> str:
    from ui.config_manager import UserConfigManager

    return UserConfigManager.decode_sensitive(value) if value else ""


def build_envs(service_id: str) -> dict[str, str]:
    """Resolve legacy credential names for the pdf2zh-next settings adapter."""
    spec = BY_ID.get(service_id)
    if spec is None:
        raise ValueError(f"未知翻译服务: {service_id}")

    cfg = _load_config()
    envs: dict[str, str] = {}

    if spec.api_env:
        key = _decode(cfg.get(f"api_{spec.prefix}", "")) or os.environ.get(spec.api_env, "").strip()
        if key:
            envs[spec.api_env] = key
    if spec.url_env:
        url = (cfg.get(f"url_{spec.prefix}", "") or "").strip() or os.environ.get(spec.url_env, "").strip()
        if url:
            envs[spec.url_env] = url
    if spec.model_env:
        model = (cfg.get(f"model_{spec.prefix}", "") or "").strip() or os.environ.get(spec.model_env, "").strip()
        if model:
            envs[spec.model_env] = model
    for env_name, cfg_field in spec.extras:
        value = (cfg.get(f"{cfg_field}_{spec.prefix}", "") or "").strip() or os.environ.get(env_name, "").strip()
        if value:
            envs[env_name] = value
    return envs


def service_state(service_id: str) -> dict[str, Any]:
    """Non-secret view of one service for the settings endpoint."""
    spec = BY_ID[service_id]
    cfg = _load_config()
    key = (
        _decode(cfg.get(f"api_{spec.prefix}", ""))
        or os.environ.get(spec.api_env, "").strip()
    ) if spec.api_env else ""
    return {
        "id": spec.id,
        "name": spec.name,
        "needs_key": spec.needs_key,
        "has_key": bool(key) or not spec.needs_key,
        "base_url": (cfg.get(f"url_{spec.prefix}", "") or os.environ.get(spec.url_env, "")).strip(),
        "model": (cfg.get(f"model_{spec.prefix}", "") or os.environ.get(spec.model_env, "")).strip(),
        "default_base_url": spec.default_base_url,
        "default_model": spec.default_model,
        "note": spec.note,
    }
