from types import SimpleNamespace

from app.ai.metrics import usage_from_exception, usage_to_token_dict


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


def _exc_with_usage(usage):
    # Shape mirrors agents SDK: exc.run_data.context_wrapper.usage
    exc = RuntimeError("agent blew up")
    exc.run_data = SimpleNamespace(context_wrapper=SimpleNamespace(usage=usage))
    return exc


def test_usage_recovered_from_exception():
    usage = SimpleNamespace(input_tokens=10, output_tokens=4, total_tokens=14)
    assert usage_from_exception(_exc_with_usage(usage)) is usage


def test_usage_recovered_through_cause_chain():
    usage = SimpleNamespace(input_tokens=1, output_tokens=1, total_tokens=2)
    inner = _exc_with_usage(usage)
    outer = RuntimeError("wrapped after retries")
    outer.__cause__ = inner  # our retry wrapper re-raises `from` the original
    assert usage_from_exception(outer) is usage


def test_usage_absent_returns_none():
    assert usage_from_exception(ValueError("corrupt PDF")) is None
