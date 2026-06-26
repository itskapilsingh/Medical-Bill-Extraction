import pytest

from app.ai.config import (
    ALLOWED_EXTRACTION_MODELS,
    EXTRACTION_AGENT_CONFIG,
    PDF_FILE_EXTRACTION_CONFIG,
    validate_extraction_model,
)


@pytest.mark.parametrize("model", sorted(ALLOWED_EXTRACTION_MODELS))
def test_allowed_extraction_models(model):
    assert validate_extraction_model(model) == model


@pytest.mark.parametrize(
    "model",
    ["gpt-5.4-pro", "gpt-5.4-mini-pro", "gpt-5.4-nano-pro", "gpt-5.5-mini"],
)
def test_rejects_pro_and_unapproved_extraction_models(model):
    with pytest.raises(ValueError):
        validate_extraction_model(model)


def test_configured_extraction_paths_use_allowed_non_pro_models():
    configured = [EXTRACTION_AGENT_CONFIG.model, PDF_FILE_EXTRACTION_CONFIG.model]
    assert configured
    for model in configured:
        assert "-pro" not in model
        assert model in ALLOWED_EXTRACTION_MODELS
