"""Reusable Streamlit action controls with an inline, visibly disabled busy state."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator


@contextmanager
def processing_action(st, label: str, key: str, message: str, *, button_type: str = "primary",
                      disabled: bool = False, width: str = "content") -> Iterator[bool]:
    """Render an action and replace it inline with a disabled control while its body runs."""
    button_column, progress_column = st.columns([1, 2], vertical_alignment="center")
    button_slot, progress_slot = button_column.empty(), progress_column.empty()
    clicked = button_slot.button(label, key=key, type=button_type, disabled=disabled, width=width)
    if not clicked:
        yield False
        return
    button_slot.empty()
    button_slot.button(label, key=f"{key}-running", type=button_type, disabled=True, width=width)
    try:
        with progress_slot:
            with st.spinner(message, show_time=True):
                yield True
    finally:
        progress_slot.empty()
        button_slot.empty()
        button_slot.button(label, key=f"{key}-complete", type=button_type, disabled=False, width=width)
