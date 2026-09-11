"""Show Dossier QC subsystem (TODO-342 Phase 2).

Rules are pure functions ``(conn) -> Iterable[Finding]`` registered in
:data:`backend.qc.rules.RULES`. :mod:`backend.qc.store` runs them against
``qc_findings``/``qc_decision_log``/``qc_runs`` and answers quarantine
lookups. See ``instructions/SHOW_DOSSIER_REDESIGN_PLAN.md`` "Phase 2" for the
schema and rule table, and "Decision vocabulary" for the finding status state
machine.
"""
