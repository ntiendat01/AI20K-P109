from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from src.core.config import Settings, get_settings


def resolve_llm_provider(settings: Settings) -> str:
    """Honor explicit selection; auto selects the first configured provider."""
    if settings.llm_provider != "auto":
        return settings.llm_provider
    if settings.openrouter_api_key.strip():
        return "openrouter"
    if settings.groq_api_key.strip():
        return "groq"
    if settings.qwen_base_url.strip():
        return "qwen"
    return "openai"


def get_llm() -> ChatOpenAI:
    """Build the selected client without switching providers on configuration errors."""
    settings = get_settings()
    provider = resolve_llm_provider(settings)
    if provider == "openrouter":
        if not settings.openrouter_api_key.strip():
            raise ValueError("LLM_PROVIDER=openrouter yêu cầu OPENROUTER_API_KEY trong .env.")
        headers = {}
        if settings.openrouter_site_url:
            headers["HTTP-Referer"] = settings.openrouter_site_url
        if settings.openrouter_app_name:
            headers["X-OpenRouter-Title"] = settings.openrouter_app_name
        return ChatOpenAI(
            model=settings.openrouter_model_name,
            api_key=SecretStr(settings.openrouter_api_key.strip()),
            base_url=settings.openrouter_base_url,
            temperature=0,
            timeout=settings.openrouter_timeout_seconds,
            max_tokens=settings.openrouter_max_tokens,
            default_headers=headers,
            model_kwargs={"response_format": {"type": "json_object"}},
            extra_body={"reasoning": {"enabled": settings.openrouter_reasoning_enabled}},
        )
    if provider == "groq":
        if not settings.groq_api_key.strip():
            raise ValueError("LLM_PROVIDER=groq yêu cầu GROQ_API_KEY trong .env.")
        return ChatOpenAI(
            model=settings.groq_model_name,
            api_key=SecretStr(settings.groq_api_key),
            base_url=settings.groq_base_url,
            temperature=0,
            timeout=settings.groq_timeout_seconds,
            max_tokens=settings.groq_max_tokens,
        )
    if provider == "qwen":
        if not settings.qwen_base_url.strip():
            raise ValueError("LLM_PROVIDER=qwen yêu cầu QWEN_BASE_URL trong .env.")
        return ChatOpenAI(
            model=settings.qwen_model_name,
            api_key=SecretStr(settings.qwen_api_key or "not-required"),
            base_url=settings.qwen_base_url,
            temperature=0,
            timeout=settings.qwen_timeout_seconds,
        )
    if not settings.openai_api_key.strip():
        raise ValueError("LLM_PROVIDER=openai yêu cầu OPENAI_API_KEY trong .env.")
    return ChatOpenAI(
        model=settings.model_name,
        api_key=SecretStr(settings.openai_api_key.strip()),
        temperature=settings.llm_temperature,
        timeout=settings.openai_timeout_seconds,
        reasoning_effort=settings.openai_reasoning_effort,
        model_kwargs={"response_format": {"type": "json_object"}},
    )
