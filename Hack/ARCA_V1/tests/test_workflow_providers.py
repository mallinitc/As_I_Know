import pytest

from arca.providers import get_provider
from arca.workflow import build


@pytest.mark.parametrize("provider_name", ["azure", "aws"])
def test_workflow_routes_provider_from_state(provider_name, monkeypatch):
    monkeypatch.setenv("ARCA_MODE", "mock")
    adapter = get_provider(provider_name)
    bundle = adapter.load_bundle()
    change = bundle["changes"][0]
    request = adapter.access_for_change(bundle, change["change_id"])

    result = build().invoke({
        "provider": provider_name,
        "change": change,
        "access_request": request,
        "events": bundle["events"],
        "context": bundle,
    })

    assert result["stage1"]["status"] == "VALID"
    assert result["stage2"]["status"] in {"APPROPRIATE", "OVERPRIVILEGED"}
    assert result["stage3"]["status"] in {"POTENTIAL_MATCH", "DEVIATION_DETECTED", "EVIDENCE_INCOMPLETE"}
    assert result["narrative"].startswith("MOCK NARRATIVE")


def test_explicit_build_provider_remains_backward_compatible(monkeypatch):
    monkeypatch.setenv("ARCA_MODE", "mock")
    adapter = get_provider("azure")
    bundle = adapter.load_bundle()
    change = bundle["changes"][0]
    result = build("azure").invoke({
        "change": change,
        "access_request": adapter.access_for_change(bundle, change["change_id"]),
        "events": bundle["events"],
        "context": bundle,
    })
    assert result["stage1"]["provider"] == "azure"
