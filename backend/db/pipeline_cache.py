"""Pipeline hash/state cache, TODO-205 Phase 1 (from backend.db, TODO-369 S2)."""

import json
from pathlib import Path

from backend.db import get_connection
from backend.db_queue import get_write_queue

# ── Pipeline hash/state cache (TODO-205 Phase 1) ───────────────────────────────
# Design: instructions/PIPELINE_STRUCTURAL_TIER_DESIGN.md §2–§3. Inert until the
# later phases wire consultation into _pipeline_process_folder; nothing reads
# these tables yet.

_PIPELINE_STEPS = ("verify", "lookup", "lbdir", "rename", "file")


def _norm_folder(raw: str) -> str:
    """Normalise a folder path to the forward-slash cache-key form.

    Mirrors filer.normalise_path (Path.as_posix) without importing filer,
    which would create a backend.filer ↔ backend.db import cycle.
    """
    return Path(raw).as_posix()


def _cacheable(*texts: str) -> bool:
    """Whether all strings can be stored as SQLite TEXT.

    Paths of files whose on-disk names hold undecodable bytes carry lone
    surrogates (os surrogateescape), which sqlite3 cannot bind as TEXT.
    Such paths are simply never cached — a cache miss means a fresh read,
    so skipping them costs speed, never correctness.
    """
    try:
        for t in texts:
            t.encode("utf-8")
        return True
    except UnicodeEncodeError:
        return False


def upsert_file_hash(folder_path: str, rel_path: str, size: int, mtime: float,
                     md5: "str | None" = None, ffp: "str | None" = None,
                     sha256: "str | None" = None, db_path=None) -> None:
    """Insert or refresh one pipeline_file_hash row.

    Hash columns merge: a NULL argument preserves any previously stored value
    ONLY when (size, mtime) are unchanged — a changed file replaces the whole
    row so no stale hash of older content can survive alongside new stats.

    Args:
        folder_path: Absolute folder path (normalised internally).
        rel_path: Posix-style path of the file relative to folder_path.
        size: Current os.stat st_size — validation column.
        mtime: Current os.stat st_mtime — validation column.
        md5: Full-file md5 hex, if computed.
        ffp: FLAC fingerprint hex, if computed (FLAC audio only).
        sha256: Full-file sha256 hex, if computed.
        db_path: Unused; writes route through the shared write queue.
    """
    _fp, _rel = _norm_folder(folder_path), rel_path
    if not _cacheable(_fp, _rel):
        return

    def _run(c):
        row = c.execute(
            "SELECT size, mtime FROM pipeline_file_hash "
            "WHERE folder_path=? AND rel_path=?", (_fp, _rel),
        ).fetchone()
        same = row is not None and row["size"] == size and row["mtime"] == mtime
        if same:
            c.execute(
                "UPDATE pipeline_file_hash SET "
                "md5=COALESCE(?, md5), ffp=COALESCE(?, ffp), "
                "sha256=COALESCE(?, sha256), hashed_at=CURRENT_TIMESTAMP "
                "WHERE folder_path=? AND rel_path=?",
                (md5, ffp, sha256, _fp, _rel),
            )
        else:
            c.execute(
                "INSERT OR REPLACE INTO pipeline_file_hash "
                "(folder_path, rel_path, size, mtime, md5, ffp, sha256, hashed_at) "
                "VALUES (?,?,?,?,?,?,?,CURRENT_TIMESTAMP)",
                (_fp, _rel, size, mtime, md5, ffp, sha256),
            )

    get_write_queue().execute(_run)


def get_file_hash(folder_path: str, rel_path: str, db_path=None) -> "dict | None":
    """Return one pipeline_file_hash row, or None.

    Raw fetch — the caller must validate (size, mtime) against a fresh os.stat
    before trusting any hash (design rule R1: validate at consumption).
    """
    if not _cacheable(_norm_folder(folder_path), rel_path):
        return None
    row = get_connection(db_path).execute(
        "SELECT * FROM pipeline_file_hash WHERE folder_path=? AND rel_path=?",
        (_norm_folder(folder_path), rel_path),
    ).fetchone()
    return dict(row) if row else None


def get_folder_hashes(folder_path: str, db_path=None) -> "dict[str, dict]":
    """Return all pipeline_file_hash rows for a folder, keyed by rel_path.

    Raw fetch (one query for batch consumers like derive_tree_digest); rows
    still need per-file (size, mtime) validation before use.
    """
    if not _cacheable(_norm_folder(folder_path)):
        return {}
    rows = get_connection(db_path).execute(
        "SELECT * FROM pipeline_file_hash WHERE folder_path=?",
        (_norm_folder(folder_path),),
    ).fetchall()
    return {r["rel_path"]: dict(r) for r in rows}


def folder_fingerprint(folder_path: str) -> "str | None":
    """Compute the per-file stat-aggregate fingerprint of a folder (design §3 R2).

    sha256 over sorted "rel_path\\tsize\\tmtime" lines for every file under the
    folder (audio + checksums + art). Pure os.stat sweep — no content reads —
    so it changes on any add/remove/rename/in-place edit, unlike the
    directory's own mtime.

    Returns:
        Hex digest, or None when the folder does not exist.
    """
    import hashlib

    root = Path(folder_path)
    if not root.is_dir():
        return None
    lines = []
    for p in root.rglob("*"):
        if p.is_file():
            st = p.stat()
            lines.append(f"{p.relative_to(root).as_posix()}\t{st.st_size}\t{st.st_mtime}")
    return hashlib.sha256("\n".join(sorted(lines)).encode("utf-8", "surrogatepass")).hexdigest()


def get_folder_state(folder_path: str, db_path=None) -> "dict | None":
    """Return the cached pipeline row state for a folder, or None.

    Returns:
        Dict with keys folder_path, fingerprint, steps (step name → verdict
        dict, JSON already parsed), steps_run (list) and updated_at. Callers
        must recompute folder_fingerprint and compare before trusting any
        verdict (design §3 R3); the file step is never authoritative (P8).
    """

    if not _cacheable(_norm_folder(folder_path)):
        return None
    row = get_connection(db_path).execute(
        "SELECT * FROM pipeline_folder_state WHERE folder_path=?",
        (_norm_folder(folder_path),),
    ).fetchone()
    if not row:
        return None
    steps = {}
    for name in _PIPELINE_STEPS:
        raw = row[f"{name}_json"]
        if raw:
            steps[name] = json.loads(raw)
    return {
        "folder_path": row["folder_path"],
        "fingerprint": row["fingerprint"],
        "steps": steps,
        "steps_run": json.loads(row["steps_json"]) if row["steps_json"] else [],
        "updated_at": row["updated_at"],
    }


def put_folder_state(folder_path: str, fingerprint: str,
                     step_results: "dict[str, dict]", db_path=None) -> None:
    """Upsert cached step verdicts for a folder (design §2b).

    Merge semantics: when the stored fingerprint equals *fingerprint*, steps
    absent from *step_results* keep their previous verdicts (partial re-run).
    When it differs, all previous verdicts are discarded — they described
    different bytes and must not survive under the new fingerprint.

    Args:
        folder_path: Absolute folder path (normalised internally).
        fingerprint: Current folder_fingerprint() of the folder.
        step_results: Step name → verdict dict, for the steps just run.
            Unknown step names raise ValueError.
        db_path: Unused; writes route through the shared write queue.
    """

    bad = set(step_results) - set(_PIPELINE_STEPS)
    if bad:
        raise ValueError(f"Unknown pipeline steps: {sorted(bad)}")
    _fp = _norm_folder(folder_path)
    if not _cacheable(_fp):
        return

    def _run(c):
        row = c.execute(
            "SELECT fingerprint, steps_json FROM pipeline_folder_state "
            "WHERE folder_path=?", (_fp,),
        ).fetchone()
        merge = row is not None and row["fingerprint"] == fingerprint
        if merge:
            prev_run = set(json.loads(row["steps_json"]) if row["steps_json"] else [])
            steps_run = sorted(prev_run | set(step_results))
            sets = ", ".join(f"{n}_json=?" for n in step_results)
            c.execute(
                f"UPDATE pipeline_folder_state SET {sets}, steps_json=?, "
                "updated_at=CURRENT_TIMESTAMP WHERE folder_path=?",
                (*(json.dumps(step_results[n]) for n in step_results),
                 json.dumps(steps_run), _fp),
            )
        else:
            c.execute(
                "INSERT OR REPLACE INTO pipeline_folder_state "
                "(folder_path, fingerprint, verify_json, lookup_json, lbdir_json, "
                "rename_json, file_json, steps_json, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)",
                (_fp, fingerprint,
                 *(json.dumps(step_results[n]) if n in step_results else None
                   for n in _PIPELINE_STEPS),
                 json.dumps(sorted(step_results))),
            )

    get_write_queue().execute(_run)


def derive_tree_digest(folder_path: str, db_path=None) -> str:
    """Reproduce filer.hash_tree() from cached sha256s, byte-for-byte (design §2c).

    Serves the SOURCE side of filing's hash-verify only: enumerates every file
    under the folder exactly as hash_tree does, uses a cached sha256 when the
    row's (size, mtime) still validate against a fresh os.stat (rule R1), and
    reads + hashes the file fresh on any miss (write-through to the cache).
    The DESTINATION digest after a copy must always come from filer.hash_tree
    on real bytes — never from this function.

    Args:
        folder_path: Absolute folder path.
        db_path: Optional DB path for cache reads.

    Returns:
        Hex digest identical to filer.hash_tree(folder_path).
    """
    import hashlib

    root = Path(folder_path)
    cached = get_folder_hashes(folder_path, db_path)
    tree_digest = hashlib.sha256()
    rel_paths = sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())
    for rel_path in rel_paths:
        # Stored rel_path keys are posix-form; str(relative_to) is identical on
        # posix and differs only on Windows.
        key = Path(rel_path).as_posix()
        st = (root / rel_path).stat()
        row = cached.get(key)
        if (row and row["sha256"]
                and row["size"] == st.st_size and row["mtime"] == st.st_mtime):
            digest = bytes.fromhex(row["sha256"])
        else:
            file_digest = hashlib.sha256()
            with open(root / rel_path, "rb") as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    file_digest.update(chunk)
            digest = file_digest.digest()
            upsert_file_hash(folder_path, key, st.st_size, st.st_mtime,
                             sha256=digest.hex(), db_path=db_path)
        tree_digest.update(rel_path.encode("utf-8", "surrogatepass"))
        tree_digest.update(digest)
    return tree_digest.hexdigest()


def prune_pipeline_cache(db_path=None) -> dict:
    """Drop pipeline cache rows for folders that no longer exist.

    Run daily by ``scheduler.start_pipeline_cache_pruner``. A folder counts as
    gone only when its parent directory is still there: an unmounted drive
    makes every folder on it look missing, and pruning then would throw away
    hashes that are still valid. There is no age cap — a cached hash is checked
    against (size, mtime) on every read, so an old row is never a wrong one.

    Args:
        db_path: Optional DB path for the folder-list read.

    Returns:
        {"file_hash_deleted": int, "folder_state_deleted": int}
    """
    with get_connection(db_path) as conn:
        folders = {r[0] for r in conn.execute(
            "SELECT DISTINCT folder_path FROM pipeline_file_hash "
            "UNION SELECT folder_path FROM pipeline_folder_state"
        ).fetchall()}
    gone = [f for f in folders
            if not Path(f).is_dir() and Path(f).parent.is_dir()]

    def _run(c):
        n_hash = n_state = 0
        for f in gone:
            n_hash += c.execute(
                "DELETE FROM pipeline_file_hash WHERE folder_path=?", (f,)
            ).rowcount
            n_state += c.execute(
                "DELETE FROM pipeline_folder_state WHERE folder_path=?", (f,)
            ).rowcount
        return {"file_hash_deleted": n_hash, "folder_state_deleted": n_state}

    return get_write_queue().execute(_run)
