"""Locate Olof's bobtalk quotes inside our recordings and persist timestamps.

TODO-303. The scoring, confidence and persistence rules live in
``backend/bobtalk.py``; this is the ASR half — it decodes the audio and hands
the token sets over.

Two geometries, and **full-show is the default**:

* ``--full-show`` (default) decodes the recording end to end and slides
  overlapping windows over the utterances. Chosen after the first corpus pass:
  boundary windows hear only about a fifth of a show, and quotes spoken away
  from a track split were unreachable at any threshold. Measured cost on the GPU
  is ~65x realtime (92s for a 100-minute show), so a corpus pass is hours, not
  the minutes the boundary pass took — plan for a resumable overnight run.
* ``--boundaries`` keeps the original pass: one window around every track split.
  Cheaper on CPU, and the geometry the first corpus run used.

The geometries are gated DIFFERENTLY, and the geometry flag carries the gate —
see :func:`backend.bobtalk.gate_for`. Boundary windows keep the best-vs-runner-up
separation rule; full-show drops it (it does not survive the change in window
count) and raises the Dice floor instead.

Why *all* candidate windows are scored either way: inferring WHICH window holds
a given quote from the setlist position was tried and drifts (it failed in both
directions on the 1978-12-16 PoC). Letting each quote pick its own best window
costs one pass and removes the assumption entirely.

Requires ``model: large-v3`` and ``vad_filter: False``: the shipped ``base``
model garbles too heavily to recognise a known line, and Silero VAD silently
discards announcer-over-crowd speech (see CALIBRATION_PROGRESS.md "§3
banter/ASR signal").

Decoded window text is cached in ``data/bobtalk_decodes.db`` (see
``backend/bobtalk_decodes.py``), keyed by model and window geometry, so a
threshold or tokenizer change can be re-scored with ``--rescore`` at no CPU
cost. The cache is derived data and meant to be discarded once the rules
settle: ``--prune-cache``, or delete the file.

Usage:
    .venv/bin/python3 tools/bobtalk_locate.py --lb 212
    .venv/bin/python3 tools/bobtalk_locate.py --lb 212 --boundaries
    .venv/bin/python3 tools/bobtalk_locate.py --date 1978-12-16 --all-sources
    .venv/bin/python3 tools/bobtalk_locate.py --lb 212 --rescore
    .venv/bin/python3 tools/bobtalk_locate.py --cache-summary
    .venv/bin/python3 tools/bobtalk_locate.py --prune-cache large-v3
"""
from __future__ import annotations

import argparse
import logging
import re
import sqlite3
import sys
import time
from pathlib import Path

import yaml

APP_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_ROOT))
sys.path.insert(0, str(APP_ROOT / "tools" / "tapematch"))

from backend import bobtalk as bt  # noqa: E402
from backend import bobtalk_decodes as dec  # noqa: E402
from backend import paths as bpaths  # noqa: E402

log = logging.getLogger("bobtalk_locate")

PRE_SEC = 55.0          # how far before a track boundary to listen (--boundaries)
POST_SEC = 25.0         # ...and after; banter straddles the split either way
DEFAULT_MODEL = "large-v3"
CONFIG_PATH = APP_ROOT / "tools" / "tapematch" / "config.yaml"

# config.yaml's asr block is tuned for the tapematch batch signal, where the
# model is `base` and CPU is the only assumption. This pass is a different
# workload — large-v3, on demand, one recording at a time — so it picks its own
# device instead of inheriting `device: cpu`.
_COMPUTE_BY_DEVICE = {"cuda": "float16", "cpu": "int8"}


# CTranslate2 links cuBLAS and cuDNN at first CUDA use, but the wheels that
# ship them (nvidia-cublas-cu12 / nvidia-cudnn-cu12) install into site-packages
# rather than anywhere the dynamic loader searches. LD_LIBRARY_PATH would have
# to be set before the process starts, so instead they are dlopen'd with
# RTLD_GLOBAL up front, which puts their symbols where CTranslate2 looks.
_CUDA_LIB_DIRS = ("nvidia/cublas/lib", "nvidia/cudnn/lib")
_CUDA_LIBS = ("libcublas.so.12", "libcublasLt.so.12", "libcudnn.so.9")


def preload_cuda_libs() -> bool:
    """Make the pip-installed cuBLAS/cuDNN visible to CTranslate2.

    Returns:
        True if every required library was loaded; False if any is missing, in
        which case CUDA decoding will not work and CPU is the honest fallback.
    """
    import ctypes  # noqa: PLC0415 (only needed on the CUDA path)
    import sysconfig  # noqa: PLC0415

    roots = {sysconfig.get_paths()["purelib"], sysconfig.get_paths()["platlib"]}
    for lib in _CUDA_LIBS:
        for root in roots:
            for sub in _CUDA_LIB_DIRS:
                path = Path(root) / sub / lib
                if path.exists():
                    try:
                        ctypes.CDLL(str(path), mode=ctypes.RTLD_GLOBAL)
                    except OSError as exc:
                        log.warning("cuda: %s failed to load (%s)", lib, exc)
                        return False
                    break
            else:
                continue
            break
        else:
            log.warning("cuda: %s not found; install nvidia-cublas-cu12 and "
                        "nvidia-cudnn-cu12, or pass --device cpu", lib)
            return False
    return True


def detect_device() -> str:
    """Return ``"cuda"`` when CTranslate2 can see a usable GPU, else ``"cpu"``.

    A visible GPU is not enough: the decode also needs cuBLAS and cuDNN, and
    when they are absent CTranslate2 fails *per window* rather than at load, so
    a run looks successful and transcribes nothing. Both are checked here so
    that failure never reaches the decode loop.

    Returns:
        The device string to hand faster-whisper.
    """
    try:
        import ctranslate2  # noqa: PLC0415 (optional, and only needed to decode)
        if ctranslate2.get_cuda_device_count() > 0 and preload_cuda_libs():
            return "cuda"
    except Exception as exc:  # noqa: BLE001 — absent or broken CUDA is just CPU
        log.debug("cuda probe failed (%s); using cpu", exc)
    return "cpu"


def build_asr_cfg(model: str, threads: int, device: str,
                  compute_type: str | None = None) -> tuple[dict, list[str], str]:
    """Build the ASR config block and audio extensions for a locate pass.

    Args:
        model: faster-whisper model name.
        threads: CPU threads to allow the decoder (ignored on CUDA).
        device: ``"cuda"``, ``"cpu"``, or ``"auto"`` to probe.
        compute_type: Quantisation override; defaults to float16 on CUDA and
            int8 on CPU.

    Returns:
        ``(asr_cfg, audio_exts, resolved_device)``.
    """
    if device == "auto":
        device = detect_device()
    elif device == "cuda" and not preload_cuda_libs():
        raise RuntimeError("--device cuda requested but cuBLAS/cuDNN are not loadable")
    ctype = compute_type or _COMPUTE_BY_DEVICE.get(device, "int8")
    raw = yaml.safe_load(CONFIG_PATH.read_text())
    cfg = dict(raw["asr"])
    cfg.update(model=model, cpu_threads=threads, vad_filter=False, enabled=True,
               device=device, compute_type=ctype)
    return cfg, raw["ingest"]["audio_exts"], device


def _event_for_date(conn: sqlite3.Connection, date_str: str) -> tuple[int, str] | None:
    """Return the ``(event_id, bobtalk)`` for a date, preferring the fullest block."""
    row = conn.execute(
        "SELECT event_id, bobtalk FROM olof_events "
        "WHERE date_str = ? AND bobtalk IS NOT NULL AND TRIM(bobtalk) <> '' "
        "ORDER BY LENGTH(bobtalk) DESC LIMIT 1", (date_str,)).fetchone()
    return (row[0], row[1]) if row else None


def _sources_for_date(conn: sqlite3.Connection, date_str: str,
                      require_disk: bool = True) -> list[tuple[int, str]]:
    """Return ``(lb_number, disk_path)`` for every collected recording of a date.

    Args:
        conn: Open main-database connection.
        date_str: Show date, ``YYYY-MM-DD``.
        require_disk: Drop recordings whose folder is not on disk. Re-scoring
            from cached decodes needs no audio, so it passes ``False``.

    Returns:
        Sorted ``(lb_number, disk_path)`` pairs.
    """
    out = []
    for lb, fn, dp in conn.execute(
            "SELECT lb_number, folder_name, disk_path FROM my_collection"):
        if not (fn or "").startswith(date_str):
            continue
        if require_disk and not (dp and Path(dp).is_dir()):
            continue
        out.append((int(lb), dp or ""))
    return sorted(out)


def geometry_key(full_show: bool) -> tuple[float, float]:
    """Return the decode-cache geometry key for a pass.

    Args:
        full_show: Whether the pass decodes the whole recording.

    Returns:
        ``(pre_sec, post_sec)`` as the cache keys them.
    """
    return dec.FULL_SHOW_GEOM if full_show else (PRE_SEC, POST_SEC)


def decode_windows(lb_number: int, disk_path: str, cfg: dict, exts: list[str],
                   model_name: str, cache: sqlite3.Connection | None,
                   full_show: bool = True) -> list[dec.Window]:
    """Return a recording's decodes, from cache when possible.

    The cache key covers the model, the quantisation and the geometry, so a hit
    is only ever served for audio decoded under exactly these settings: a
    boundary pass and a full-show pass of the same recording coexist rather than
    overwriting each other.

    Args:
        lb_number: Recording being decoded.
        disk_path: Folder holding its audio.
        cfg: ASR config block.
        exts: Audio file extensions to ingest.
        model_name: Model identifier, part of the cache key.
        cache: Open decode-cache connection, or ``None`` to bypass the cache.
        full_show: Decode end to end (one entry per utterance) instead of one
            window per track boundary.

    Returns:
        Decoded windows in time order — utterances under *full_show*, boundary
        windows otherwise.

    Raises:
        RuntimeError: If a decode is needed and faster-whisper is unavailable.
    """
    ctype = cfg.get("compute_type", "int8")
    pre, post = geometry_key(full_show)
    if cache is not None:
        cached = dec.load_windows(cache, lb_number, model_name, ctype, pre, post)
        if cached is not None:
            log.info("LB-%05d: %d window(s) from decode cache", lb_number, len(cached))
            return cached

    from tapematch import asr, ingest  # deferred: heavy, and optional for tests

    mono, sr, bounds = ingest.concat_source(Path(disk_path), exts, 16000, mono=True)
    dur = len(mono) / float(sr)
    model = asr.load_model(cfg)
    if model is None:
        raise RuntimeError("faster-whisper unavailable; cannot locate")

    windows: list[dec.Window] = []
    t0 = time.time()
    if full_show:
        # One gap spanning the recording: faster-whisper does its own internal
        # chunking, and handing it the whole stream keeps utterance timestamps
        # on a single clock with no per-window seam to reconcile.
        for i, u in enumerate(asr.transcribe_gaps(mono, sr, [(0.0, dur)], cfg, model=model)):
            windows.append(dec.Window(i, u.t_start, u.t_end, u.text))
    else:
        for i, b in enumerate(bounds):
            ts = b / float(sr)
            w0, w1 = max(0.0, ts - PRE_SEC), min(dur, ts + POST_SEC)
            text = " ".join(u.text for u in
                            asr.transcribe_gaps(mono, sr, [(w0, w1)], cfg, model=model))
            windows.append(dec.Window(i, w0, w1, text))
    elapsed = time.time() - t0
    log.info("LB-%05d: decoded %s in %.0fs (%.0fx realtime)", lb_number,
             f"{len(windows)} utterance(s) over {dur / 60:.0f} min" if full_show
             else f"{len(windows)} windows", elapsed, dur / max(elapsed, 1e-6))

    # A decoder that cannot run at all still returns cleanly: transcribe_gaps
    # swallows per-window failures so one bad window cannot kill a session, so
    # a missing CUDA library reads as "every window is silent". A full show
    # never legitimately yields zero characters, and treating that as a real
    # result is expensive twice over — it caches the emptiness, and it replaces
    # good stored locations with none. This is the same silent-failure shape as
    # the vad_filter bug in TODO-293; fail loudly instead.
    # Under full-show the same failure reads as an EMPTY list rather than as
    # textless windows, because there are no boundaries to enumerate — so zero
    # utterances over a whole show is refused too. A real Dylan tape decoded
    # with vad_filter off never legitimately yields nothing.
    if not any(w.text.strip() for w in windows):
        raise RuntimeError(
            f"decoder produced no text across {len(windows)} window(s) "
            f"({cfg.get('model')} on {cfg.get('device')}/{ctype}) — treating as a "
            "decoder failure, not as silence; nothing cached or saved")

    if cache is not None:
        dec.save_windows(cache, lb_number, model_name, ctype, pre, post, windows,
                         audio_sec=dur, decode_sec=elapsed, device=cfg.get("device"))
    return windows


def locate_one(conn: sqlite3.Connection, lb_number: int, disk_path: str,
               event_id: int, block: str, cfg: dict, exts: list[str],
               model_name: str, cache: sqlite3.Connection | None = None,
               cache_only: bool = False, full_show: bool = True) -> list[bt.Match]:
    """Decode a recording and locate every bobtalk quote in it.

    Tokenisation happens here rather than at decode time, so the cache holds raw
    text and a change to ``content_tokens`` can be re-scored for free.

    Args:
        conn: Open main-database connection.
        lb_number: Recording being searched.
        disk_path: Folder holding its audio.
        event_id: ``olof_events.event_id`` supplying the quotes.
        block: Raw bobtalk text.
        cfg: ASR config block.
        exts: Audio file extensions to ingest.
        model_name: Model identifier, stored for provenance.
        cache: Open decode-cache connection, or ``None`` to bypass the cache.
        cache_only: Skip recordings with no cached decode instead of decoding
            them. Re-scoring a corpus must never silently start ASR work.
        full_show: Search the whole recording rather than track boundaries.

    Returns:
        The matches written (both confident and not).
    """
    quotes = bt.parse_bobtalk(block)
    if not quotes:
        log.warning("LB-%05d: no matchable quotes in event %s", lb_number, event_id)
        return []

    pre, post = geometry_key(full_show)
    if cache_only:
        if cache is None:
            raise RuntimeError("cache_only requires a decode cache")
        decoded = dec.load_windows(cache, lb_number, model_name,
                                   cfg.get("compute_type", "int8"), pre, post)
        if decoded is None:
            log.info("LB-%05d: no cached decode; skipped", lb_number)
            return []
    else:
        decoded = decode_windows(lb_number, disk_path, cfg, exts, model_name, cache,
                                 full_show=full_show)

    geometry = bt.GEOM_FULL if full_show else bt.GEOM_BOUNDARIES
    if full_show:
        # Windows are cut here, not at decode time: the cache holds utterances,
        # so re-cutting at a different length costs nothing but a re-score.
        windows = bt.windows_from_utterances([(w.t_start, w.t_end, w.text) for w in decoded])
    else:
        windows = [(w.t_start, frozenset(bt.content_tokens(w.text))) for w in decoded]
    matches = bt.locate_quotes(quotes, windows, geometry=geometry)
    bt.save_locations(conn, lb_number, event_id, matches, model=model_name,
                      geometry=geometry)
    return matches


def main() -> None:
    """CLI entry point."""
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--lb", type=int, help="locate within one LB recording")
    g.add_argument("--date", help="locate within a date's recordings (YYYY-MM-DD)")
    g.add_argument("--cache-summary", action="store_true",
                   help="report what the decode cache holds, and exit")
    g.add_argument("--prune-cache", nargs="?", const="", metavar="MODEL",
                   help="discard cached decodes (optionally only one model's), and exit")
    p.add_argument("--all-sources", action="store_true",
                   help="with --date, process every source, not just the first")
    p.add_argument("--boundaries", dest="full_show", action="store_false",
                   help="search one window per track boundary instead of the whole show")
    p.add_argument("--rescore", action="store_true",
                   help="re-score from cached decodes only; never runs ASR")
    p.add_argument("--no-cache", action="store_true",
                   help="ignore and do not write the decode cache")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--device", default="auto", choices=("auto", "cuda", "cpu"),
                   help="auto = use the GPU when CTranslate2 can see one")
    p.add_argument("--compute-type", default=None,
                   help="quantisation override (default float16 on cuda, int8 on cpu)")
    p.add_argument("--threads", type=int, default=0, help="0 = all cores (cpu only)")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(message)s")

    if args.cache_summary or args.prune_cache is not None:
        cache = dec.connect()
        try:
            if args.cache_summary:
                for r in dec.summary(cache):
                    geom = ("full-show          "
                            if (r["pre_sec"], r["post_sec"]) == dec.FULL_SHOW_GEOM
                            else f"pre={r['pre_sec']:<6.1f} post={r['post_sec']:<6.1f}")
                    sys.stdout.write(
                        f"{r['model']:<12} {r['compute_type']:<8} {geom} "
                        f"{r['recordings']:>6} rec {r['windows']:>7} win "
                        f"{r['chars'] / 1e6:>7.2f} Mchar {r['decode_hours']:>7.1f} h "
                        f"{r['last_at']}\n")
            else:
                n = dec.prune(cache, model=args.prune_cache or None)
                sys.stdout.write(f"pruned {n} cached recording decode(s)\n")
        finally:
            cache.close()
        return

    if args.rescore and args.no_cache:
        p.error("--rescore reads the cache; it cannot be combined with --no-cache")

    cfg, exts, device = build_asr_cfg(args.model, args.threads, args.device, args.compute_type)
    if not args.rescore:
        log.info("decoding with %s on %s (%s)", args.model, device, cfg["compute_type"])
    conn = sqlite3.connect(str(bpaths.DB_PATH))
    cache = None if args.no_cache else dec.connect()
    try:
        if args.lb is not None:
            row = conn.execute(
                "SELECT folder_name, disk_path FROM my_collection WHERE lb_number = ?",
                (args.lb,)).fetchone()
            # --rescore reads decoded text, never audio, so a recording whose
            # folder has since moved offline can still be re-scored.
            if not row or (not args.rescore and (not row[1] or not Path(row[1]).is_dir())):
                p.error(f"LB-{args.lb:05d}: no collected folder on disk")
            m = re.match(r"(\d{4}-\d{2}-\d{2})", row[0] or "")
            if not m:
                p.error(f"LB-{args.lb:05d}: folder name carries no date")
            targets, date_str = [(args.lb, row[1] or "")], m.group(1)
        else:
            date_str = args.date
            targets = _sources_for_date(conn, date_str, require_disk=not args.rescore)
            if not args.all_sources:
                targets = targets[:1]
            if not targets:
                p.error(f"{date_str}: no collected recordings on disk")

        ev = _event_for_date(conn, date_str)
        if ev is None:
            p.error(f"{date_str}: no olof_events row carries bobtalk")
        event_id, block = ev

        for lb_number, disk_path in targets:
            try:
                matches = locate_one(conn, lb_number, disk_path, event_id, block,
                                     cfg, exts, args.model, cache=cache,
                                     cache_only=args.rescore, full_show=args.full_show)
            except Exception as exc:  # noqa: BLE001 — one bad source, not the run
                log.error("LB-%05d: locate failed (%s)", lb_number, exc)
                continue
            ok = sum(1 for m in matches if m.confident)
            for m in matches:
                flag = "OK " if m.confident else "-- "
                sys.stdout.write(
                    f"{flag}LB-{lb_number:05d} q{m.quote_index:<3} "
                    f"t={m.t_start / 60:7.1f}min dice={m.dice:.2f} "
                    f"runner={m.runner_up:.2f}\n")
            sys.stdout.write(
                f"LB-{lb_number:05d}: {ok}/{len(matches)} quote(s) located "
                f"(event {event_id}, {date_str})\n")
    finally:
        conn.close()
        if cache is not None:
            cache.close()


if __name__ == "__main__":
    main()
