"""
Tests for TODO-205 Phase 6 (P8) — "blocked" collect severity split.

The severity logic lives in `backend.app.compute_pipeline_severity`, a
module-level pure function extracted from `_pipeline_process_folder` (TODO-211)
precisely so this test drives the **real** code rather than a mirror — no drift
is possible. `_pipeline_process_folder` itself is a closure inside
`create_app()` that boots live file/collection/integrity watchers and cannot be
unit-driven, but the extracted function has no such dependencies.
"""

from backend.app import compute_pipeline_severity


def _severity(verify, lookup, lbdir, rename, file_status, file_error_code, lb_number):
    """Thin adapter onto the real function, preserving this test's call order."""
    return compute_pipeline_severity(
        verify, lookup, lbdir, rename, file_status, file_error_code, lb_number,
    )


def _fully_verified_steps():
    """verify/lookup/lbdir/rename all ok/mute — a folder that would land in 'done'
    if not for the file step's blocked status."""
    return {
        "verify": {"status": "ok"},
        "lookup": {"status": "ok"},
        "lbdir":  {"status": "ok"},
        "rename": {"status": "ok", "label": "Correct"},
        "lb_number": 12345,
    }


def test_transient_blocked_code_does_not_escalate_to_attn():
    """mount_offline (and other transient codes) are no longer forced to attn —
    a fully-verified folder blocked only on a transient file-step error lands
    in 'done', which the GUI re-buckets to shelf for live re-resolve (P8)."""
    s = _fully_verified_steps()
    severity = _severity(
        s["verify"], s["lookup"], s["lbdir"], s["rename"],
        file_status="blocked", file_error_code="mount_offline", lb_number=s["lb_number"],
    )
    assert severity == "done"
    assert severity != "attn"


def test_no_date_blocked_code_still_escalates_to_attn():
    """no_date (and no_route) need human config — still true attn."""
    s = _fully_verified_steps()
    severity = _severity(
        s["verify"], s["lookup"], s["lbdir"], s["rename"],
        file_status="blocked", file_error_code="no_date", lb_number=s["lb_number"],
    )
    assert severity == "attn"


def test_unknown_blocked_code_is_treated_as_transient():
    """Whitelist (not blacklist) semantics: an unrecognised error_code must not
    escalate — robust to new/unknown blocked codes added later."""
    s = _fully_verified_steps()
    severity = _severity(
        s["verify"], s["lookup"], s["lbdir"], s["rename"],
        file_status="blocked", file_error_code="some_future_code", lb_number=s["lb_number"],
    )
    assert severity == "done"


def test_bad_status_elsewhere_still_escalates_regardless_of_file_step():
    """A genuine failure in verify/lookup/lbdir/rename still forces attn even
    when the file step itself isn't blocked at all — P8 only narrows the
    file-step escalation, it doesn't touch the "bad" fast path."""
    s = _fully_verified_steps()
    s["verify"] = {"status": "bad"}
    severity = _severity(
        s["verify"], s["lookup"], s["lbdir"], s["rename"],
        file_status="mute", file_error_code=None, lb_number=s["lb_number"],
    )
    assert severity == "attn"
