from __future__ import annotations

import pytest

from src.experimentation.shadow_deployment import ShadowDeploymentPolicy


def build_observations(
    count: int,
    *,
    probability_delta: float,
    disagreement: bool,
    latency_overhead_ms: float,
    candidate_error: bool = False,
) -> list[dict[str, object]]:
    return [
        {
            "probability_abs_delta": probability_delta,
            "decision_disagreement": disagreement,
            "latency_overhead_ms": latency_overhead_ms,
            "candidate_error": candidate_error,
        }
        for _ in range(count)
    ]


def test_shadow_selection_is_deterministic() -> None:
    policy = ShadowDeploymentPolicy(
        enabled=True,
        sample_rate=0.10,
    )

    request_ids = [f"request-{index}" for index in range(1_000)]

    first_selection = [
        request_id for request_id in request_ids if policy.should_shadow(request_id)
    ]

    second_selection = [
        request_id for request_id in request_ids if policy.should_shadow(request_id)
    ]

    assert first_selection == second_selection
    assert 50 <= len(first_selection) <= 150


def test_kill_switch_disables_shadow_routing() -> None:
    policy = ShadowDeploymentPolicy(
        enabled=False,
        sample_rate=1.0,
    )

    assert not policy.should_shadow("request-always-selected")


def test_insufficient_evidence_blocks_progression() -> None:
    policy = ShadowDeploymentPolicy(
        minimum_observations=10,
    )

    observations = build_observations(
        9,
        probability_delta=0.01,
        disagreement=False,
        latency_overhead_ms=10.0,
    )

    result = policy.evaluate(observations)

    assert result["decision"] == "INSUFFICIENT_EVIDENCE"
    assert result["gates"]["minimum_observations"] is False


def test_all_gates_allow_controlled_canary() -> None:
    policy = ShadowDeploymentPolicy(
        minimum_observations=10,
        maximum_candidate_error_rate=0.01,
        maximum_mean_probability_delta=0.03,
        maximum_decision_disagreement_rate=0.02,
        maximum_p95_latency_overhead_ms=75.0,
    )

    observations = build_observations(
        10,
        probability_delta=0.01,
        disagreement=False,
        latency_overhead_ms=25.0,
    )

    result = policy.evaluate(observations)

    assert all(result["gates"].values())
    assert result["decision"] == "ELIGIBLE_FOR_CONTROLLED_CANARY"


@pytest.mark.parametrize(
    (
        "observations",
        "failed_gate",
    ),
    [
        (
            build_observations(
                10,
                probability_delta=0.08,
                disagreement=False,
                latency_overhead_ms=25.0,
            ),
            "mean_probability_delta",
        ),
        (
            build_observations(
                10,
                probability_delta=0.01,
                disagreement=True,
                latency_overhead_ms=25.0,
            ),
            "decision_disagreement_rate",
        ),
        (
            build_observations(
                10,
                probability_delta=0.01,
                disagreement=False,
                latency_overhead_ms=125.0,
            ),
            "p95_latency_overhead_ms",
        ),
        (
            build_observations(
                10,
                probability_delta=0.01,
                disagreement=False,
                latency_overhead_ms=25.0,
                candidate_error=True,
            ),
            "candidate_error_rate",
        ),
    ],
)
def test_failed_gate_retains_active_model(
    observations: list[dict[str, object]],
    failed_gate: str,
) -> None:
    policy = ShadowDeploymentPolicy(
        minimum_observations=10,
        maximum_candidate_error_rate=0.01,
        maximum_mean_probability_delta=0.03,
        maximum_decision_disagreement_rate=0.02,
        maximum_p95_latency_overhead_ms=75.0,
    )

    result = policy.evaluate(observations)

    assert result["gates"][failed_gate] is False
    assert result["decision"] == "RETAIN_ACTIVE_MODEL"


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("sample_rate", -0.01),
        ("sample_rate", 1.01),
        ("minimum_observations", 0),
        (
            "maximum_p95_latency_overhead_ms",
            -1.0,
        ),
    ],
)
def test_invalid_policy_is_rejected(
    field_name: str,
    field_value: float | int,
) -> None:
    with pytest.raises(ValueError):
        ShadowDeploymentPolicy(**{field_name: field_value})
