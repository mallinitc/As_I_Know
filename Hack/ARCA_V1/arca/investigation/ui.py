"""Small UI helpers shared by Ask ARCA entry points and tests."""


def choose_question(*, main_submitted=False, main_text="", suggested_text=None,
                    followup_submitted=False, followup_text=""):
    """Return at most one normalized submission, using visible UI priority."""
    if main_submitted and main_text.strip():
        return main_text.strip()
    if suggested_text:
        return suggested_text.strip()
    if followup_submitted and followup_text.strip():
        return followup_text.strip()
    return None
