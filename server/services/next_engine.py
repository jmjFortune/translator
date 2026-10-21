"""Translate the server's existing options into pdf2zh-next 2.9 settings.

Imports stay lazy so mock mode does not need the translation runtime.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from .credentials import BY_ID


# These providers use the same OpenAI protocol, but keep their existing IDs
# and credential names in the public settings API.
_OPENAI_PROVIDERS = {
    "openai": "OpenAI", "gemini": "Gemini", "deepseek": "DeepSeek",
    "zhipu": "Zhipu", "groq": "Groq",
    "grok": "Grok", "modelscope": "ModelScope",
}
_NATIVE_PROVIDERS = {
    "google": ("Google", {}),
    "bing": ("Bing", {}),
    "deepl": ("DeepL", {"deepl_auth_key": "DEEPL_AUTH_KEY"}),
    "silicon": ("SiliconFlow", {
        "siliconflow_api_key": "SILICON_API_KEY",
        "siliconflow_base_url": "SILICON_BASE_URL",
        "siliconflow_model": "SILICON_MODEL",
    }),
    "ollama": ("Ollama", {"ollama_host": "OLLAMA_HOST", "ollama_model": "OLLAMA_MODEL"}),
    "xinference": ("Xinference", {"xinference_host": "XINFERENCE_HOST", "xinference_model": "XINFERENCE_MODEL"}),
    "azure-openai": ("AzureOpenAI", {
        "azure_openai_api_key": "AZURE_OPENAI_API_KEY",
        "azure_openai_base_url": "AZURE_OPENAI_BASE_URL",
        "azure_openai_model": "AZURE_OPENAI_MODEL",
    }),
    "azure": ("Azure", {"azure_api_key": "AZURE_API_KEY", "azure_endpoint": "AZURE_ENDPOINT"}),
    "tencent": ("Tencent", {
        "tencentcloud_secret_id": "TENCENTCLOUD_SECRET_ID",
        "tencentcloud_secret_key": "TENCENTCLOUD_SECRET_KEY",
    }),
    "dify": ("Dify", {"dify_apikey": "DIFY_API_KEY", "dify_url": "DIFY_API_URL"}),
    "anythingllm": ("AnythingLLM", {"anythingllm_apikey": "AnythingLLM_APIKEY", "anythingllm_url": "AnythingLLM_URL"}),
    "qwen-mt": ("QwenMt", {"qwenmt_api_key": "ALI_API_KEY", "qwenmt_model": "ALI_MODEL"}),
}


def engine_settings(service: str, envs: dict[str, str]):
    from pdf2zh_next.config import translate_engine_model as models

    spec = BY_ID[service]
    values = dict(envs)
    for env_name, default in ((spec.url_env, spec.default_base_url), (spec.model_env, spec.default_model)):
        if env_name and default:
            values.setdefault(env_name, default)

    if service in _OPENAI_PROVIDERS:
        native_type = _OPENAI_PROVIDERS[service]
        native_cls = getattr(models, f"{native_type}Settings")
        # Native transforms supply the provider's default endpoint. Explicit
        # saved URLs still take precedence, as they did before the migration.
        native = native_cls(**{f"{service}_api_key": values.get(spec.api_env)})
        defaults = native if service == "openai" else native.transform()
        return models.OpenAISettings(
            openai_api_key=values.get(spec.api_env),
            openai_base_url=values.get(spec.url_env) or defaults.openai_base_url,
            openai_model=values.get(spec.model_env) or defaults.openai_model,
        )

    if service in {"openailiked", "opencode-go"}:
        if not values.get(spec.url_env):
            raise ValueError(f"「{spec.name}」的 API 地址未配置")
        if not values.get(spec.model_env):
            raise ValueError(f"「{spec.name}」的模型未配置")
        return models.OpenAISettings(
            openai_api_key=values.get(spec.api_env),
            openai_base_url=values[spec.url_env],
            openai_model=values[spec.model_env],
        )

    native_type, fields = _NATIVE_PROVIDERS[service]
    return getattr(models, f"{native_type}Settings")(**{
        field: values[name] for field, name in fields.items() if values.get(name)
    })


def build_settings(job: dict[str, Any], envs: dict[str, str], pages: list[int] | None, formats: list[str]):
    from pdf2zh_next.config.model import PDFSettings, SettingsModel, TranslationSettings
    from pdf2zh_next.config.translate_engine_model import TRANSLATION_ENGINE_METADATA_MAP

    options = job["options"]
    output = Path(job["output_dir"])
    output.mkdir(parents=True, exist_ok=True)
    engine = engine_settings(options.get("service", "bing"), envs)
    supports_glossary = TRANSLATION_ENGINE_METADATA_MAP[engine.translate_engine_type].support_llm
    glossary_path = None
    if (glossary := options.get("glossary")) and supports_glossary:
        path = output / "glossary.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["source", "target"])
            writer.writerows(glossary.items())
        glossary_path = str(path)

    workers = max(1, min(int(options.get("thread", 4)), 32))
    settings = SettingsModel(
        translate_engine_settings=engine,
        translation=TranslationSettings(
            lang_in=options.get("lang_in", "en"),
            lang_out=options.get("lang_out", "zh"),
            output=str(output),
            qps=workers,
            pool_max_workers=workers,
            glossaries=glossary_path,
            no_auto_extract_glossary=not bool(options.get("auto_glossary")),
            save_auto_extracted_glossary=bool(options.get("auto_glossary")),
        ),
        pdf=PDFSettings(
            pages=",".join(str(page + 1) for page in pages) if pages is not None else None,
            only_include_translated_page=pages is not None,
            use_alternating_pages_dual=True,
            dual_translate_first=False,
            no_mono="mono" not in formats,
            no_dual=not any(kind in formats for kind in ("dual", "side_by_side")),
            watermark_output_mode="no_watermark",
            ocr_workaround=bool(options.get("ocr")),
            translate_table_text=bool(options.get("translate_tables")),
        ),
    )
    settings.validate_settings()
    return settings
