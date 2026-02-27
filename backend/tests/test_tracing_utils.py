from app.services.tracing import (
    normalize_trace_metadata,
    redact_text_for_trace,
    should_sample_trace,
)


def test_redact_text_for_trace_masks_pii_and_truncates():
    text = "Contact me at alice@example.com or +1 555 123 4567. " + ("x" * 300)
    out = redact_text_for_trace(text, max_chars=80)
    assert "alice@example.com" not in out
    assert "[redacted-email]" in out
    assert "[redacted-phone]" in out
    assert "[truncated:" in out


def test_normalize_trace_metadata_caps_lists_and_dicts():
    data = {
        "student_message": "hello",
        "nested": {str(i): f"value-{i}" for i in range(50)},
        "arr": list(range(20)),
    }
    out = normalize_trace_metadata(data)
    assert isinstance(out, dict)
    assert len(out["nested"]) <= 20
    assert len(out["arr"]) <= 8


def test_should_sample_trace_deterministic_for_key():
    key = "session-a:turn-b"
    a = should_sample_trace(key, 0.35)
    b = should_sample_trace(key, 0.35)
    assert a == b


def test_should_sample_trace_bounds():
    assert should_sample_trace("k", 1.0) is True
    assert should_sample_trace("k", 0.0) is False
