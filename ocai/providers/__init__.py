from ocai.providers.base import Provider, Suggestion, ProviderError


def get_provider(name: str, *, model: str | None = None) -> Provider:
    name = name.lower()
    if name == "claude":
        from ocai.providers.claude import ClaudeProvider
        return ClaudeProvider(model=model)
    if name == "openai":
        from ocai.providers.openai_provider import OpenAIProvider
        return OpenAIProvider(model=model)
    if name == "ollama":
        from ocai.providers.ollama import OllamaProvider
        return OllamaProvider(model=model)
    raise ProviderError(f"unknown provider: {name!r} (expected claude|openai|ollama)")


__all__ = ["Provider", "Suggestion", "ProviderError", "get_provider"]
