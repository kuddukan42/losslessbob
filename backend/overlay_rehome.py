"""Re-home TUIT/WTRF seed overlays left behind by a cross-drive move (TODO-376).

A seed overlay (``<mount>/<TRACKER> Seeds/<torrent root>``) hardlinks the
collection's audio. A cross-drive move copies the collection folder and deletes
the source, and hardlinks cannot cross drives, so the overlay stays on the old
drive as the only holder of those bytes: the space is never reclaimed. This
module rebuilds such an overlay on the collection folder's new drive, points
qBittorrent at it and then deletes the old one.

COLLECTION SAFETY — these rules override everything else here:

* Collection files are never opened, written, renamed, chmodded or deleted by
  this module. They are only ``stat``-ed, used as the *source* of ``os.link``,
  and read by the piece verify.
* Every create/rename/delete goes through :func:`guard_path`: the path must sit
  strictly below a ``* Seeds`` directory and must not be, contain, or be inside
  any collection folder or collection mount root.
* The old overlay is never ``rmtree``-d. Only regular files with a link count of
  one are unlinked, one by one; anything else stops the delete.
* Only overlays whose torrent verifies 100% are re-homed, so the client never
  has to download into a hardlinked file. qBittorrent is never asked to move
  files (no ``setLocation``) or to delete them: the torrent is removed with
  ``deleteFiles=false`` and re-added stopped at the new overlay.
* The collection folder is snapshotted before and after. Any change latches
  ``overlay_rehome_disabled`` in ``meta`` and every later run refuses to start.
"""
from __future__ import annotations

import bisect
import hashlib
import json
import logging
import os
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from backend import qbittorrent, tracker_seed
from backend.seed_overlay import collection_is_untouched, snapshot_folder
from backend.torrent_verify import BencodeError, TorrentInfo, read_torrent, verify_folder

logger = logging.getLogger(__name__)

#: Tracker download tables that record a seed folder, by tracker name.
TABLES = {"tuit": "tuit_downloads", "wtrf": "wtrf_downloads"}

#: meta key latched when a collection folder changed during a re-home.
DISABLED_META = "overlay_rehome_disabled"

#: Build directory inside the destination ``* Seeds`` root.
BUILD_DIRNAME = ".rehome-build"

_SEEDS_SUFFIX = " Seeds"
_CHUNK = 1 << 20


class GuardError(Exception):
    """A path failed the collection-safety guard; nothing was done to it."""


class RehomeError(Exception):
    """A re-home step failed; the overlay is left as it was."""


@dataclass
class SeedRecord:
    """One recorded overlay seed, newest row per tracker and folder."""

    tracker: str
    lb_number: int
    overlay: Path
    torrent_path: str


@dataclass
class RehomePlan:
    """What re-homing one overlay would do."""

    record: SeedRecord
    collection: Path
    new_overlay: Path
    links: dict[str, Path] = field(default_factory=dict)   # overlay rel -> collection file
    copies: dict[str, int] = field(default_factory=dict)   # overlay rel -> size
    sizes: dict[str, int] = field(default_factory=dict)    # every overlay rel -> size
    skip: str = ""
    #: overlay rel -> (st_dev, st_ino, st_nlink) for files with more than one link
    shared: dict[str, tuple[int, int, int]] = field(default_factory=dict)
    #: old overlay dirs of the same LB on the same drive (this one included)
    group: list[Path] = field(default_factory=list)

    @property
    def copy_bytes(self) -> int:
        """Bytes that will be duplicated onto the destination drive."""
        return sum(self.copies.values())

    @property
    def freed_bytes(self) -> int:
        """Bytes the old drive gets back once the old overlay is deleted."""
        return sum(self.sizes.values())


# ── Collection-safety guard ──────────────────────────────────────────────────

def _norm(path: str | Path) -> str:
    """Normalise a path string without touching the filesystem."""
    return os.path.normpath(os.path.abspath(str(path)))


class Protected:
    """The set of paths nothing in this module may write to or delete under.

    Args:
        paths: Collection folders and mount roots.
    """

    def __init__(self, paths: Iterable[str | Path]):
        self._set = {_norm(p) for p in paths if p}
        self._sorted = sorted(self._set)

    def add(self, path: str | Path) -> None:
        """Protect one more path (and its resolved form)."""
        for p in {_norm(path), _norm(os.path.realpath(path))}:
            if p not in self._set:
                self._set.add(p)
                bisect.insort(self._sorted, p)

    def hit(self, path: str) -> str | None:
        """Return the protected path ``path`` equals, sits inside, or contains."""
        cur = path
        while True:
            if cur in self._set:
                return cur
            parent = os.path.dirname(cur)
            if parent == cur:
                break
            cur = parent
        prefix = path.rstrip(os.sep) + os.sep
        i = bisect.bisect_left(self._sorted, prefix)
        if i < len(self._sorted) and self._sorted[i].startswith(prefix):
            return self._sorted[i]
        return None


def load_protected(db_path=None) -> Protected:
    """Every collection folder and mount root recorded in the DB.

    Args:
        db_path: Optional DB path override.

    Returns:
        A Protected set.
    """
    from backend import db

    paths: list[str] = []
    with db.get_connection(db_path) as conn:
        paths += [r[0] for r in conn.execute(
            "SELECT disk_path FROM my_collection WHERE disk_path IS NOT NULL")]
        paths += [r[0] for r in conn.execute(
            "SELECT root_path FROM collection_mounts WHERE root_path IS NOT NULL")]
    return Protected(paths)


def guard_path(path: str | Path, protected: Protected, seeds_root: bool = False) -> Path:
    """Refuse any path this module must not create, rename or delete.

    The final component is not resolved, so a symlink is judged as itself and
    never followed.

    Args:
        path: Absolute path about to be acted on.
        protected: Collection folders and mount roots.
        seeds_root: Allow the ``* Seeds`` directory itself (creating it).

    Returns:
        The path with its parent resolved.

    Raises:
        GuardError: The path is unsafe.
    """
    raw = Path(path)
    if not raw.is_absolute() or ".." in raw.parts:
        raise GuardError(f"refused {path}: not a plain absolute path")
    real = Path(os.path.realpath(raw.parent)) / raw.name
    for candidate in (_norm(raw), _norm(real)):
        hit = protected.hit(candidate)
        if hit:
            raise GuardError(f"refused {path}: collection path {hit}")
    parts = real.parts
    seeds = [i for i, part in enumerate(parts) if part.endswith(_SEEDS_SUFFIX)]
    if not seeds:
        raise GuardError(f"refused {path}: not under a '*{_SEEDS_SUFFIX}' directory")
    if seeds[-1] == len(parts) - 1 and not seeds_root:
        raise GuardError(f"refused {path}: is a '*{_SEEDS_SUFFIX}' root")
    if os.path.islink(real):
        raise GuardError(f"refused {path}: is a symlink")
    return real


# ── Records and discovery ────────────────────────────────────────────────────

def is_overlay_dir(folder: str | Path) -> bool:
    """Whether a seed folder is an overlay (its parent is ``* Seeds``)."""
    return Path(folder).parent.name.endswith(_SEEDS_SUFFIX)


def seed_records(lb_number: int | None = None, db_path=None) -> list[SeedRecord]:
    """Overlay seeds recorded by either tracker, newest row per folder.

    Args:
        lb_number: Restrict to one LB, or None for every LB.
        db_path: Optional DB path override.

    Returns:
        SeedRecords for overlay folders only (in-place collection seeds are
        left out: they move with the collection folder).
    """
    import sqlite3

    from backend import db

    out: list[SeedRecord] = []
    with db.get_connection(db_path) as conn:
        for tracker, table in TABLES.items():
            where = "seed_folder IS NOT NULL AND seed_folder <> '' AND lb_number IS NOT NULL"
            args: tuple = ()
            if lb_number is not None:
                where += " AND lb_number=?"
                args = (lb_number,)
            try:
                rows = conn.execute(
                    f"SELECT lb_number, seed_folder, torrent_path FROM {table} "  # noqa: S608
                    f"WHERE {where} ORDER BY attempted_at DESC, id DESC", args,
                ).fetchall()
            except sqlite3.Error:
                continue
            seen: set[str] = set()
            for lb, folder, torrent in rows:
                if folder in seen or not is_overlay_dir(folder):
                    continue
                seen.add(folder)
                out.append(SeedRecord(tracker, int(lb), Path(folder), torrent or ""))
    return out


def collection_folder(lb_number: int, db_path=None) -> Path | None:
    """The LB's current collection folder from ``my_collection``."""
    from backend import db

    with db.get_connection(db_path) as conn:
        row = conn.execute("SELECT disk_path FROM my_collection WHERE lb_number=?",
                           (lb_number,)).fetchone()
    return Path(row[0]) if row and row[0] else None


def same_volume(a: str | Path, b: str | Path) -> bool:
    """Whether two existing paths sit on the same filesystem."""
    return os.stat(a).st_dev == os.stat(b).st_dev


def _walk_files(root: Path) -> dict[str, os.stat_result]:
    """lstat every entry below ``root`` (no symlink following), keyed by rel path.

    Raises:
        RehomeError: The tree holds a symlink or something that is not a file.
    """
    out: dict[str, os.stat_result] = {}
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        for name in dirnames:
            if os.path.islink(os.path.join(dirpath, name)):
                raise RehomeError(f"{os.path.join(dirpath, name)} is a symlink")
        for name in filenames:
            full = os.path.join(dirpath, name)
            st = os.lstat(full)
            if not os.path.isfile(full) or os.path.islink(full):
                raise RehomeError(f"{full} is not a regular file")
            out[os.path.relpath(full, root)] = st
    return out


# ── Pre-delete manifest (called by the filer) ────────────────────────────────

def record_pending(lb_number: int, source: str | Path, dest: str | Path,
                   db_path=None) -> int:
    """Record which overlay files share an inode with the source folder.

    Called by the filer after the verified copy and before the source folder
    is deleted — the last moment the shared/overlay-only split is visible.
    Stat only: nothing is opened or changed. Never raises.

    Args:
        lb_number: LB being moved.
        source: The collection folder about to be deleted.
        dest: Where the verified copy now is.
        db_path: Optional DB path override.

    Returns:
        How many overlay_moves rows were written.
    """
    try:
        records = seed_records(lb_number, db_path)
        if not records:
            return 0
        inodes: dict[tuple[int, int], str] = {}
        for rel, st in _walk_files(Path(source)).items():
            inodes[(st.st_dev, st.st_ino)] = rel
        rows = []
        for rec in records:
            if not rec.overlay.is_dir():
                continue
            manifest = {}
            for rel, st in _walk_files(rec.overlay).items():
                src_rel = inodes.get((st.st_dev, st.st_ino))
                if src_rel is not None:
                    manifest[rel] = src_rel
            rows.append((lb_number, rec.tracker, str(rec.overlay), str(source), str(dest),
                         json.dumps(manifest)))
        if rows:
            _write(lambda c: c.executemany(
                "INSERT INTO overlay_moves(lb_number, tracker, old_overlay, src_folder,"
                " dest_folder, manifest_json, state) VALUES(?,?,?,?,?,?,'pending')", rows))
        return len(rows)
    except Exception as exc:  # bookkeeping must never block filing
        logger.warning("overlay_rehome: could not record LB-%s overlays: %s", lb_number, exc)
        return 0


def _write(fn) -> None:
    """Run one write through the DB write queue."""
    from backend.db_queue import get_write_queue
    get_write_queue().execute(fn)


def _manifest_for(overlay: Path, db_path=None) -> dict[str, str] | None:
    """The newest recorded pre-delete manifest for an overlay, if any."""
    from backend import db

    with db.get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT manifest_json FROM overlay_moves WHERE old_overlay=? "
            "AND manifest_json IS NOT NULL ORDER BY id DESC LIMIT 1", (str(overlay),),
        ).fetchone()
    return json.loads(row[0]) if row else None


def _set_state(rec: SeedRecord, state: str, new_overlay: str = "", error: str = "") -> None:
    """Record the outcome of one re-home against its overlay_moves row."""
    def run(c):
        cur = c.execute(
            "UPDATE overlay_moves SET state=?, new_overlay=?, error=?, "
            "updated_at=CURRENT_TIMESTAMP WHERE id=(SELECT MAX(id) FROM overlay_moves "
            "WHERE old_overlay=?)", (state, new_overlay, error, str(rec.overlay)))
        if cur.rowcount == 0:
            c.execute(
                "INSERT INTO overlay_moves(lb_number, tracker, old_overlay, new_overlay,"
                " state, error) VALUES(?,?,?,?,?,?)",
                (rec.lb_number, rec.tracker, str(rec.overlay), new_overlay, state, error))
    _write(run)


# ── Planning ─────────────────────────────────────────────────────────────────

def _match_links(overlay_files: dict[str, int], collection: Path,
                 manifest: dict[str, str] | None) -> dict[str, Path]:
    """Map overlay files to the collection file holding the same bytes.

    The pre-delete manifest wins; otherwise the same relative path, then a
    unique same-name same-size file anywhere in the folder. Every match must
    also agree on size. The 100% piece verify after the build is what proves
    the bytes, so a wrong match only costs an aborted build.
    """
    coll: dict[str, int] = {}
    by_name: dict[tuple[str, int], list[str]] = {}
    for rel, st in _walk_files(collection).items():
        coll[rel] = st.st_size
        by_name.setdefault((os.path.basename(rel), st.st_size), []).append(rel)

    links: dict[str, Path] = {}
    for rel, size in overlay_files.items():
        cand = (manifest or {}).get(rel)
        if cand is None or coll.get(cand) != size:
            cand = rel if coll.get(rel) == size else None
        if cand is None:
            hits = by_name.get((os.path.basename(rel), size), [])
            cand = hits[0] if len(hits) == 1 else None
        if cand is not None:
            links[rel] = collection / cand
    return links


def plan_rehome(rec: SeedRecord, db_path=None) -> RehomePlan:
    """Decide whether and how one overlay would be re-homed. Read-only.

    Args:
        rec: The overlay seed.
        db_path: Optional DB path override.

    Returns:
        A RehomePlan; ``skip`` says why it would be left as is.
    """
    coll = collection_folder(rec.lb_number, db_path)
    plan = RehomePlan(record=rec, collection=coll or Path(), new_overlay=Path())
    if coll is None:
        plan.skip = "LB has no collection folder"
        return plan
    if not rec.overlay.is_dir():
        plan.skip = "overlay is gone"
        return plan
    if not coll.is_dir():
        plan.skip = f"collection folder missing: {coll}"
        return plan
    if same_volume(rec.overlay, coll):
        plan.skip = "same drive — nothing to do"
        return plan
    root = tracker_seed.overlay_root_for(coll, tracker_seed.SeedOptions(tracker=rec.tracker))
    plan.new_overlay = root / rec.overlay.name
    try:
        files = _walk_files(rec.overlay)
    except RehomeError as exc:
        plan.skip = str(exc)
        return plan
    # Files with other links are judged per LB by find_candidates: a TUIT and a
    # WTRF overlay of the same torrent hardlink each other, which is fine; a
    # link to anything else (a collection copy still on the old drive) is not.
    plan.shared = {rel: (st.st_dev, st.st_ino, st.st_nlink)
                   for rel, st in files.items() if st.st_nlink > 1}
    if not rec.torrent_path or not Path(rec.torrent_path).is_file():
        plan.skip = f"torrent file missing: {rec.torrent_path or '(none recorded)'}"
        return plan
    try:
        info = read_torrent(rec.torrent_path)
    except BencodeError as exc:
        plan.skip = f"unreadable torrent: {exc}"
        return plan
    if info.single_file:
        plan.skip = "single-file torrent"
        return plan
    if info.name != rec.overlay.name:
        plan.skip = f"overlay name differs from the torrent root {info.name!r}"
        return plan
    plan.sizes = {rel: st.st_size for rel, st in files.items()}
    plan.links = _match_links(plan.sizes, coll, _manifest_for(rec.overlay, db_path))
    plan.copies = {rel: size for rel, size in plan.sizes.items() if rel not in plan.links}
    return plan


def find_candidates(lb_numbers: Iterable[int] | None = None,
                    db_path=None) -> list[RehomePlan]:
    """Plan every overlay whose LB now lives on another drive.

    Args:
        lb_numbers: Restrict to these LBs, or None for all recorded seeds.
        db_path: Optional DB path override.

    Returns:
        Plans, skipped ones included, ordered by LB number. Same-drive and
        gone overlays are dropped.
    """
    if lb_numbers is None:
        records = seed_records(None, db_path)
    else:
        records = [r for lb in lb_numbers for r in seed_records(lb, db_path)]
    plans = []
    for rec in sorted(records, key=lambda r: (r.lb_number, r.tracker)):
        try:
            plan = plan_rehome(rec, db_path)
        except (OSError, RehomeError) as exc:
            plan = RehomePlan(record=rec, collection=Path(), new_overlay=Path(),
                              skip=f"cannot inspect: {exc}")
        if plan.skip in ("overlay is gone", "same drive — nothing to do"):
            continue
        plans.append(plan)
    _resolve_groups(plans)
    return plans


def group_inodes(dirs: Iterable[Path]) -> set[tuple[int, int]]:
    """Inodes whose every link is inside ``dirs``, counted fresh from disk.

    Args:
        dirs: Old overlay directories of one LB on one drive.

    Returns:
        ``(st_dev, st_ino)`` of each file whose link count equals the number of
        names it has inside ``dirs`` — no collection folder or anything else
        can share it.
    """
    seen: dict[tuple[int, int], list[int]] = {}
    for d in dirs:
        if not d.is_dir():
            continue
        for st in _walk_files(d).values():
            key = (st.st_dev, st.st_ino)
            entry = seen.setdefault(key, [0, st.st_nlink])
            entry[0] += 1
    return {key for key, (count, nlink) in seen.items() if count == nlink}


def _resolve_groups(plans: list[RehomePlan]) -> None:
    """Accept shared files only when all their links are the LB's own overlays.

    Groups the plans by LB and old drive. A file whose other names all sit in
    sibling overlays of the same group is safe to re-home and later unlink;
    a link to anything outside the group skips every plan in it.
    """
    groups: dict[tuple[int, int], list[RehomePlan]] = {}
    for plan in plans:
        if plan.skip:
            continue
        dev = os.stat(plan.record.overlay).st_dev
        groups.setdefault((plan.record.lb_number, dev), []).append(plan)
    for members in groups.values():
        dirs = [m.record.overlay for m in members]
        if not any(m.shared for m in members):
            continue
        try:
            inside = group_inodes(dirs)
        except (OSError, RehomeError) as exc:
            inside, reason = set(), f"cannot inspect: {exc}"
        else:
            reason = ""
        outside = [(m, rel) for m in members for rel, (dev, ino, _n) in m.shared.items()
                   if (dev, ino) not in inside]
        if outside or reason:
            m0, rel0 = outside[0] if outside else (members[0], "")
            reason = reason or (
                f"{len(outside)} overlay file(s) still hardlinked to something on the "
                f"old drive besides this LB's overlays (e.g. {m0.record.overlay / rel0})")
            for m in members:
                m.skip = reason
            continue
        for m in members:
            m.group = dirs


# ── Building, verifying, deleting ────────────────────────────────────────────

def _copy_file(src: Path, dst: Path) -> None:
    """Byte-copy one old-overlay file, fsync it, and check it read back equal."""
    h_src = hashlib.sha256()
    with src.open("rb") as fin, dst.open("xb") as fout:
        while chunk := fin.read(_CHUNK):
            h_src.update(chunk)
            fout.write(chunk)
        fout.flush()
        os.fsync(fout.fileno())
    h_dst = hashlib.sha256()
    with dst.open("rb") as fh:
        while chunk := fh.read(_CHUNK):
            h_dst.update(chunk)
    if h_src.digest() != h_dst.digest():
        raise RehomeError(f"copy of {src} read back different")


def _remove_tree(root: Path, protected: Protected, allow_shared: bool,
                 allowed_inodes: set[tuple[int, int]] | None = None) -> list[str]:
    """Unlink files one by one, then remove the empty directories. Never rmtree.

    Args:
        root: Directory to remove (must pass the guard).
        protected: Collection folders and mount roots.
        allow_shared: Accept files with a link count above one. True only for a
            build directory this module made (its links point into the
            collection; dropping one name never touches the collection's data).
        allowed_inodes: ``(st_dev, st_ino)`` pairs from :func:`group_inodes` —
            files every one of whose links is in this LB's old overlays.

    Returns:
        Paths that were refused and left in place (empty on success).
    """
    guard_path(root, protected)
    refused: list[str] = []
    real_root = os.path.realpath(root)
    for dirpath, dirnames, filenames in os.walk(root, topdown=False, followlinks=False):
        for name in filenames + [d for d in dirnames
                                 if os.path.islink(os.path.join(dirpath, d))]:
            full = Path(dirpath) / name
            try:
                guard_path(full, protected)
                st = os.lstat(full)
                parent = os.path.realpath(full.parent)
                inside = parent == real_root or parent.startswith(real_root + os.sep)
                if os.path.islink(full) or not os.path.isfile(full) or not inside:
                    raise GuardError(f"refused {full}: not a regular file inside {root}")
                if (st.st_nlink > 1 and not allow_shared
                        and (st.st_dev, st.st_ino) not in (allowed_inodes or set())):
                    raise GuardError(f"refused {full}: still has {st.st_nlink} links")
                os.unlink(full)
            except (GuardError, OSError) as exc:
                refused.append(str(exc))
        if not refused:
            for name in dirnames:
                sub = Path(dirpath) / name
                if os.path.isdir(sub) and not os.path.islink(sub):
                    try:
                        guard_path(sub, protected)
                        os.rmdir(sub)
                    except (GuardError, OSError) as exc:
                        refused.append(str(exc))
    if not refused:
        try:
            os.rmdir(guard_path(root, protected))
        except (GuardError, OSError) as exc:
            refused.append(str(exc))
    return refused


def build(plan: RehomePlan, build_dir: Path, protected: Protected) -> dict[str, int]:
    """Create the new overlay under ``build_dir/<torrent root>``.

    Links point at the new collection copy; every other file is copied from
    the old overlay. Collection files are only the source of ``os.link``.

    Returns:
        Counts of ``linked`` and ``copied`` files.
    """
    target = build_dir / plan.record.overlay.name
    guard_path(target, protected)
    target.mkdir(parents=True)
    linked = copied = 0
    for rel in sorted(plan.sizes):
        dst = guard_path(target / rel, protected)
        if not dst.parent.exists():
            guard_path(dst.parent, protected)
            dst.parent.mkdir(parents=True)
        src = plan.links.get(rel)
        if src is not None:
            os.link(src, dst)
            linked += 1
        else:
            _copy_file(plan.record.overlay / rel, dst)
            copied += 1
    return {"linked": linked, "copied": copied}


def _layout(infohash: str) -> dict:
    return qbittorrent.get_torrent_layout(infohash, **tracker_seed._qbt_connection())


def rehome(plan: RehomePlan, protected: Protected, db_path=None) -> dict:
    """Re-home one overlay: build, verify, swap the torrent, delete the old one.

    Any failure before the torrent is swapped leaves the old overlay and the
    torrent exactly as they were. A failure after the swap puts the torrent
    back on the old overlay.

    Args:
        plan: A plan from :func:`plan_rehome` with no ``skip``.
        protected: Collection folders and mount roots.
        db_path: Optional DB path override.

    Returns:
        Dict with ``ok``, ``new_overlay``, ``linked``, ``copied``, ``freed``,
        ``leftover`` (paths the old-overlay delete refused) and ``error``.

    Raises:
        RehomeError: The collection folder changed — the latch is set.
    """
    from backend import db

    if db.get_meta(DISABLED_META, db_path):
        return {"ok": False, "error": f"disabled: {db.get_meta(DISABLED_META, db_path)}"}
    rec = plan.record
    out = {"ok": False, "new_overlay": str(plan.new_overlay), "linked": 0, "copied": 0,
           "freed": 0, "leftover": [], "error": ""}
    protected.add(plan.collection)
    seeds_root = plan.new_overlay.parent
    build_dir = seeds_root / BUILD_DIRNAME
    before = snapshot_folder(plan.collection)

    def fail(msg: str) -> dict:
        out["error"] = msg
        _set_state(rec, "failed", str(plan.new_overlay), msg)
        logger.error("LB-%05d %s: %s", rec.lb_number, rec.tracker, msg)
        return out

    def check_collection() -> None:
        changed = collection_is_untouched(plan.collection, before)
        if changed:
            msg = f"collection folder {plan.collection} changed: {', '.join(changed[:5])}"
            db.set_meta(DISABLED_META, msg, db_path)
            logger.critical("overlay rehome DISABLED — %s", msg)
            raise RehomeError(msg)

    try:
        if plan.new_overlay.exists():
            return fail(f"destination already exists: {plan.new_overlay}")
        info: TorrentInfo = read_torrent(rec.torrent_path)
        infohash = qbittorrent.torrent_file_infohash(rec.torrent_path) or ""
        if not infohash:
            return fail("cannot read the torrent's infohash")
        layout = _layout(infohash)
        if not layout.get("ok"):
            return fail(f"qBittorrent: {layout.get('error') or 'query failed'}")
        present = bool(layout.get("present"))
        if present:
            here = _norm(os.path.realpath(layout["save_path"]))
            # A TUIT and a WTRF overlay of the same LB can share one infohash,
            # so qBittorrent holds a single torrent: when it seeds from a
            # sibling overlay (old or already re-homed), leave it alone.
            siblings = {_norm(os.path.realpath(g.parent)) for g in plan.group
                        if g != rec.overlay}
            siblings |= {_norm(plan.new_overlay.parent.parent / g.parent.name)
                         for g in plan.group if g != rec.overlay}
            if here in siblings:
                present = False
            elif here != _norm(os.path.realpath(rec.overlay.parent)):
                return fail(f"qBittorrent seeds it from {layout['save_path']}, "
                            "not the overlay")
        was_stopped = str(layout.get("state", "")).startswith(("stopped", "paused"))
        states = layout.get("piece_states") or []
        if present and not (states and all(s == 2 for s in states)):
            # An unfinished seed would fail the 100% verify anyway; leave it
            # alone without stopping a batch over it.
            msg = "torrent incomplete in qBittorrent — left as is"
            _set_state(rec, "skipped", "", msg)
            out.update(error=msg, skipped=True)
            return out

        free = tracker_seed._free_bytes(seeds_root if seeds_root.exists() else
                                        seeds_root.parent)
        need = plan.copy_bytes + tracker_seed.OVERLAY_FREE_RESERVE_BYTES
        if free is not None and free < need:
            return fail(f"{seeds_root} has {free / 1e9:.1f} GB free, needs {need / 1e9:.1f} GB")

        if not seeds_root.exists():
            guard_path(seeds_root, protected, seeds_root=True)
            seeds_root.mkdir()
        if not same_volume(seeds_root, plan.collection):
            return fail(f"{seeds_root} is not on the collection folder's drive")
        if build_dir.exists():
            left = _remove_tree(build_dir, protected, allow_shared=True)
            if left:
                return fail(f"stale build dir could not be cleared: {left[0]}")
        guard_path(build_dir, protected)
        build_dir.mkdir()
        built_dir = build_dir / rec.overlay.name

        counts = build(plan, build_dir, protected)
        out.update(counts)
        check_collection()
        result = verify_folder(info, built_dir)
        check_collection()
        if not result.complete:
            _remove_tree(build_dir, protected, allow_shared=True)
            return fail(f"new overlay does not verify: {result.summary()}")
        os.rename(guard_path(built_dir, protected), guard_path(plan.new_overlay, protected))
        os.rmdir(guard_path(build_dir, protected))
        _set_state(rec, "built", str(plan.new_overlay))

        if present:
            removed = qbittorrent.remove_torrent(infohash, **tracker_seed._qbt_connection())
            if not removed.get("ok"):
                _remove_tree(plan.new_overlay, protected, allow_shared=True)
                return fail(f"qBittorrent remove failed: {removed.get('error')}")
            opts = tracker_seed.SeedOptions(tracker=rec.tracker, paused=was_stopped)
            added = tracker_seed.qbt_seed(rec.torrent_path, str(plan.new_overlay), opts)
            now = _layout(infohash)
            moved = (added.get("ok") and now.get("ok") and now.get("present")
                     and _norm(now["save_path"]) == _norm(plan.new_overlay.parent)
                     and now.get("piece_states") and all(s == 2 for s in now["piece_states"]))
            if not moved:
                qbittorrent.remove_torrent(infohash, **tracker_seed._qbt_connection())
                back = tracker_seed.qbt_seed(
                    rec.torrent_path, str(rec.overlay),
                    tracker_seed.SeedOptions(tracker=rec.tracker, paused=was_stopped))
                _remove_tree(plan.new_overlay, protected, allow_shared=True)
                check_collection()
                return fail("qBittorrent did not take the new overlay "
                            f"({added.get('error') or 'not complete after recheck'}); "
                            f"put back on the old overlay: {'ok' if back.get('ok') else back}")

        old = str(rec.overlay)
        for table in TABLES.values():
            _write(lambda c, t=table: c.execute(
                f"UPDATE {t} SET seed_folder=? WHERE seed_folder=?",  # noqa: S608
                (str(plan.new_overlay), old)))

        # A sibling overlay of the same LB may still hold some of these inodes;
        # re-count right now and accept only links that stay inside that group.
        allowed = group_inodes(plan.group) if plan.group else set()
        out["leftover"] = _remove_tree(rec.overlay, protected, allow_shared=False,
                                       allowed_inodes=allowed)
        out["freed"] = plan.freed_bytes if not out["leftover"] else 0
        check_collection()
        _set_state(rec, "done" if not out["leftover"] else "done_leftover",
                   str(plan.new_overlay), "; ".join(out["leftover"][:3]))
        out["ok"] = True
        return out
    except GuardError as exc:
        return fail(str(exc))
    except (OSError, BencodeError) as exc:
        if build_dir.exists():
            _remove_tree(build_dir, protected, allow_shared=True)
        return fail(f"{type(exc).__name__}: {exc}")
