from types import SimpleNamespace

from app.ai.metrics import usage_to_token_dict


def test_basic_counts():
    usage = SimpleNamespace(input_tokens=12000, output_tokens=3400, total_tokens=15400)
    assert usage_to_token_dict(usage) == {"input": 12000, "output": 3400, "total": 15400}


def test_total_is_derived_when_absent():
    usage = SimpleNamespace(input_tokens=100, output_tokens=50, total_tokens=0)
    assert usage_to_token_dict(usage)["total"] == 150


def test_cached_and_reasoning_subcounts_kept_when_present():
    usage = SimpleNamespace(
        input_tokens=1000,
        output_tokens=500,
        total_tokens=1500,
        input_tokens_details=SimpleNamespace(cached_tokens=200),
        output_tokens_details=SimpleNamespace(reasoning_tokens=120),
    )
    out = usage_to_token_dict(usage)
    assert out["cached_input"] == 200
    assert out["reasoning"] == 120


def test_missing_fields_degrade_to_zero():
    out = usage_to_token_dict(SimpleNamespace())
    assert out == {"input": 0, "output": 0, "total": 0}
