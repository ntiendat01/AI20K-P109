from src.infrastructure.quotation.ai_extraction import (
    ConfiguredExtraction,
    GeminiAPIExtractionClient,
    GroqAPIExtractionClient,
    QwenAPIExtractionClient,
)


def test_extraction_clients_keep_langsmith_trace_wrappers() -> None:
    """Extraction tracing remains direct and independent of the deleted monitor package."""
    clients = (
        ConfiguredExtraction,
        GeminiAPIExtractionClient,
        GroqAPIExtractionClient,
        QwenAPIExtractionClient,
    )

    for client in clients:
        assert hasattr(client.extract_items, "__wrapped__")
