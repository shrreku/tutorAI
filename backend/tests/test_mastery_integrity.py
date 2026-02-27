from app.services.mastery import apply_mastery_deltas
from app.services.tutor_runtime.step_state import compute_effective_step_type


class _PolicyStub:
    def __init__(self, ad_hoc_step_type=None):
        self.ad_hoc_step_type = ad_hoc_step_type


def test_apply_mastery_deltas_preserves_untouched_concepts():
    current = {"a": 0.4, "b": 0.88, "c": 0.12}
    deltas = {
        "a": {"delta": 0.1, "weight": 1.0, "role": "primary"},
    }

    updated = apply_mastery_deltas(current, deltas)

    assert updated["b"] == current["b"]
    assert updated["c"] == current["c"]
    assert updated["a"] > current["a"]


def test_effective_step_prefers_explicit_ad_hoc_type():
    step = compute_effective_step_type(
        "explain",
        policy_output=_PolicyStub(ad_hoc_step_type="probe"),
    )
    assert step == "probe"


def test_effective_step_falls_back_to_canonical():
    step = compute_effective_step_type("assess", policy_output=_PolicyStub())
    assert step == "assess"
