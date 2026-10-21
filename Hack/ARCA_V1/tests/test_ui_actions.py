import pytest

from arca.ui_actions import processing_action


class Context:
    def __init__(self, owner=None): self.owner = owner
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def empty(self): return Slot(self.owner)


class Slot(Context):
    def button(self, label, **kwargs):
        self.owner.calls.append((label, kwargs))
        return self.owner.click and not kwargs.get("disabled") and len(self.owner.calls) == 1


class FakeStreamlit:
    def __init__(self, click=True): self.click, self.calls, self.messages = click, [], []
    def columns(self, *_args, **_kwargs): return Context(self), Context(self)
    def spinner(self, message, **_kwargs): self.messages.append(message); return Context(self)


def test_processing_action_renders_disabled_inline_state_and_restores_button():
    ui = FakeStreamlit()
    with processing_action(ui, "Run Validation", "run", "Validating change...") as clicked:
        assert clicked
        assert ui.calls[-1][1]["disabled"] is True
    assert ui.messages == ["Validating change..."]
    assert ui.calls[-1][1]["disabled"] is False
    assert len([call for call in ui.calls if not call[1]["disabled"] and call[1]["key"] == "run"]) == 1


def test_processing_action_clears_busy_state_after_failure():
    ui = FakeStreamlit()
    with pytest.raises(RuntimeError):
        with processing_action(ui, "Improve Draft", "draft", "Improving draft...") as clicked:
            assert clicked
            raise RuntimeError("simulated")
    assert ui.calls[-1][1]["disabled"] is False


def test_processing_action_does_not_execute_without_click():
    ui = FakeStreamlit(click=False)
    with processing_action(ui, "Run Validation", "run", "Validating change...") as clicked:
        assert not clicked
    assert not ui.messages
