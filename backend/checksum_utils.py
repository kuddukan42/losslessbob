import hashlib
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

from backend.paths import to_long_path


def _no_window_kwargs() -> dict:
    """Return subprocess kwargs that suppress console windows on Windows."""
    if sys.platform == "win32":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        return {"startupinfo": si, "creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def _find_shntool() -> list[str] | None:
    """Return the command prefix to invoke shntool, or None if unavailable."""
    if sys.platform == "win32":
        if shutil.which("wsl"):
            try:
                r = subprocess.run(
                    ["wsl", "which", "shntool"],
                    capture_output=True, text=True, timeout=10,
                    **_no_window_kwargs(),
                )
                if r.returncode == 0 and r.stdout.strip():
                    return ["wsl", "shntool"]
            except Exception:
                pass
        return None
    if shutil.which("shntool"):
        return ["shntool"]
    return None


_shntool_cmd_checked = False
_shntool_cmd_result: list[str] | None = None


def _get_shntool_cmd() -> list[str] | None:
    global _shntool_cmd_checked, _shntool_cmd_result
    if not _shntool_cmd_checked:
        _shntool_cmd_result = _find_shntool()
        _shntool_cmd_checked = True
    return _shntool_cmd_result


def check_shntool_version() -> str:
    """Return shntool version string, or empty string if unavailable."""
    cmd = _get_shntool_cmd()
    if not cmd:
        return ""
    try:
        r = subprocess.run(
            cmd + ["-v"],
            capture_output=True, text=True, timeout=8,
            **_no_window_kwargs(),
        )
        output = (r.stdout or r.stderr).strip()
        return output.splitlines()[0] if output else ""
    except Exception:
        return ""


class ShntoolNotFoundError(Exception):
    pass


AUDIO_EXTS = {'.flac', '.shn', '.wav', '.ape', '.m4a', '.wv', '.aif', '.aiff'}

_MD5_RE = re.compile(r'^([0-9a-fA-F]{32})\s+\*?(.+)$')
_FFP_RE = re.compile(r'^(.+\.(?:flac|ape|wav))[:=]([0-9a-fA-F]{32,40})$', re.IGNORECASE)
_SHNTOOL_LINE_RE = re.compile(
    r'^([0-9a-fA-F]{32,40})\s+\[shntool\]\s+(.+\.wav)\s*$', re.IGNORECASE
)
# Groups: length, expanded_size, cdr, wave_problems_1, wave_problems_2, fmt, ratio, filename
_SHNTOOL_LEN_RE = re.compile(
    r'^\s*([\d:]+\.[\d]+)\s+([\d]+)\s+B\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+([\d.]+)\s+(.+?)\s*$'
)


def parse_lbdir_file(path):
    """
    Parse a lbdir*.txt file into sections.
    Returns dict: {mode, md5, ffp, shntool, shntool_len}.
      md5/ffp/shntool: list of (filename, hash)
      shntool_len: list of {filename, length, expanded_size, cdr, wave_problems, fmt, ratio}
    shntool entries map .wav -> .shn filename.
    """
    path = Path(path)
    try:
        text = path.read_text(encoding='utf-8', errors='replace')
    except (IOError, OSError) as e:
        return {
            'error': str(e), 'mode': 'flac',
            'md5': [], 'ffp': [], 'shntool': [], 'shntool_len': [],
        }

    result = {'mode': 'flac', 'md5': [], 'ffp': [], 'shntool': [], 'shntool_len': []}
    current_section = None
    has_shn = False
    has_flac = False

    for line in text.splitlines():
        stripped = line.strip()
        sl = stripped.lower()

        # Separator lines are all '=' characters — skip without changing section
        if re.match(r'^=+$', stripped):
            continue

        if sl.startswith('=== md5 for:'):
            current_section = 'md5'
            continue
        elif sl.startswith('=== ffp for:'):
            current_section = 'ffp'
            continue
        elif sl.startswith('=== shntool md5/hash for:'):
            current_section = 'shntool'
            continue
        elif sl.startswith('=== shntool len for:'):
            current_section = 'shntool_len'
            continue
        elif sl.startswith('==='):
            current_section = None
            continue

        if not stripped or stripped.startswith('#'):
            continue

        if current_section == 'md5':
            m = _MD5_RE.match(stripped)
            if m:
                fname = m.group(2).strip().replace('\\', '/')
                ext = Path(fname).suffix.lower()
                if ext == '.shn':
                    has_shn = True
                elif ext == '.flac':
                    has_flac = True
                result['md5'].append((fname, m.group(1).lower()))

        elif current_section == 'ffp':
            m = _FFP_RE.match(stripped)
            if m:
                fname = m.group(1).replace('\\', '/')
                if Path(fname).suffix.lower() == '.flac':
                    has_flac = True
                result['ffp'].append((fname, m.group(2).lower()))

        elif current_section == 'shntool':
            m = _SHNTOOL_LINE_RE.match(stripped)
            if m:
                wav_fname = m.group(2).strip().replace('\\', '/')
                # Only convert .wav -> .shn when the md5 section already confirmed SHN files
                # on disk. WAV-format recordings (e.g. lbdir *.wavf.txt) store .wav files and
                # shntool hashes them directly — no conversion needed in that case.
                if has_shn:
                    fname = re.sub(r'\.wav$', '.shn', wav_fname, flags=re.IGNORECASE)
                else:
                    fname = wav_fname
                result['shntool'].append((fname, m.group(1).lower()))

        elif current_section == 'shntool_len':
            m = _SHNTOOL_LEN_RE.match(line)
            if m:
                raw_fname = m.group(8).strip().replace('\\', '/')
                # Skip the totals summary line
                if raw_fname.startswith('('):
                    continue
                # Map .wav -> .shn only for SHN recordings (same logic as shntool section)
                fname = re.sub(r'\.wav$', '.shn', raw_fname, flags=re.IGNORECASE) if has_shn else raw_fname
                result['shntool_len'].append({
                    'filename': fname,
                    'length': m.group(1),
                    'expanded_size': m.group(2),
                    'cdr': m.group(3),
                    'wave_problems': f"{m.group(4)} {m.group(5)}",
                    'fmt': m.group(6),
                    'ratio': m.group(7),
                })

    if has_shn and has_flac:
        result['mode'] = 'mixed'
    elif has_shn:
        result['mode'] = 'shn'
    return result


def compute_ffp(filepath):
    """
    Read FLAC STREAM_INFO MD5-of-audio (bytes 18-33 of block).
    Scans metadata blocks to find STREAM_INFO regardless of position.
    Returns 32-char hex string or None if not valid FLAC.
    """
    try:
        with open(to_long_path(Path(filepath)), 'rb') as f:
            if f.read(4) != b'fLaC':
                return None
            while True:
                hdr = f.read(4)
                if len(hdr) < 4:
                    return None
                block_type = hdr[0] & 0x7F
                is_last = hdr[0] & 0x80
                block_len = struct.unpack('>I', b'\x00' + hdr[1:4])[0]
                if block_type == 0:  # STREAM_INFO
                    data = f.read(block_len)
                    return data[18:34].hex() if len(data) >= 34 else None
                f.seek(block_len, 1)
                if is_last:
                    return None
    except (IOError, OSError):
        return None


def compute_md5(filepath):
    """MD5 of full file bytes. Returns 32-char hex or None on IOError."""
    try:
        h = hashlib.md5()
        with open(to_long_path(Path(filepath)), 'rb') as f:
            for chunk in iter(lambda: f.read(65536), b''):
                h.update(chunk)
        return h.hexdigest()
    except (IOError, OSError):
        return None


def _compute_shntool_via_ffmpeg(invoke_path: str, cmd: list[str]) -> str | None:
    """
    Decode audio to a temp WAV via ffmpeg, then run shntool hash on the WAV.
    Used as fallback when the shorten decoder is not installed.
    Returns 32-char hex string or None on failure.
    """
    if not shutil.which('ffmpeg'):
        return None
    tmp_fd, tmp_path = tempfile.mkstemp(suffix='.wav')
    try:
        os.close(tmp_fd)
        dec = subprocess.run(
            ['ffmpeg', '-y', '-i', invoke_path, '-f', 'wav', tmp_path],
            capture_output=True, text=True, timeout=600,
            **_no_window_kwargs(),
        )
        if dec.returncode != 0:
            return None
        result = subprocess.run(
            cmd + ['hash', tmp_path],
            capture_output=True, text=True, timeout=120,
            **_no_window_kwargs(),
        )
        for line in result.stdout.splitlines():
            if '[shntool]' in line:
                parts = line.split()
                if parts:
                    return parts[0].lower()
        return None
    except (subprocess.TimeoutExpired, Exception):
        return None
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def compute_shntool(filepath):
    """
    Compute the shntool audio-data MD5 for filepath.

    First attempts shntool hash directly (requires shorten for .shn files).
    If that produces no output and the file is .shn, falls back to decoding
    via ffmpeg then hashing the resulting WAV — handles systems where shorten
    is not installed.

    On Windows, auto-detects shntool via WSL if native binary is unavailable.
    Raises ShntoolNotFoundError if no shntool found by any method.
    Returns None if all methods fail or output is not parseable.
    """
    cmd = _get_shntool_cmd()
    if cmd is None:
        raise ShntoolNotFoundError(
            "shntool not found. "
            "On Windows: install WSL (wsl --install) then run: "
            "wsl sudo apt install shntool"
        )
    invoke_path = str(filepath)
    if sys.platform == "win32" and cmd[0] == "wsl":
        p = Path(filepath).resolve()
        drive = p.drive.rstrip(":").lower()
        rest = str(p)[len(p.drive):].replace("\\", "/")
        invoke_path = f"/mnt/{drive}{rest}"
    try:
        result = subprocess.run(
            cmd + ['hash', invoke_path],
            capture_output=True, text=True, timeout=120,
            **_no_window_kwargs(),
        )
        for line in result.stdout.splitlines():
            if '[shntool]' in line:
                parts = line.split()
                if parts:
                    return parts[0].lower()
    except subprocess.TimeoutExpired:
        return None
    except Exception:
        return None

    # shorten not installed — fall back to ffmpeg decode → shntool hash
    if Path(filepath).suffix.lower() == '.shn':
        return _compute_shntool_via_ffmpeg(invoke_path, cmd)
    return None


def detect_folder_mode(folder_path):
    """Return 'flac', 'shn', or 'mixed' based on audio files present in folder."""
    folder = Path(folder_path)
    has_flac = any(folder.glob('*.flac'))
    has_shn = any(folder.glob('*.shn'))
    if has_flac and has_shn:
        return 'mixed'
    return 'shn' if has_shn else 'flac'


def _lbgen_path(folder, basename, ext):
    """
    Return <folder>/<basename>_lbgen.<ext>, incrementing suffix
    (_lbgen_2, _lbgen_3, ...) until a non-existing path is found.
    """
    folder = Path(folder)
    candidate = folder / f'{basename}_lbgen.{ext}'
    if not candidate.exists():
        return str(candidate)
    n = 2
    while True:
        candidate = folder / f'{basename}_lbgen_{n}.{ext}'
        if not candidate.exists():
            return str(candidate)
        n += 1


def _parse_checksum_file(filepath):
    """
    Parse a standalone .ffp, .md5, or .st5 checksum file.
    Returns list of (filename, hash_type, hash_value).
    hash_type is 'ffp', 'md5', or 'shntool'; shntool entries map .wav -> .shn filename.
    """
    entries = []
    try:
        text = Path(filepath).read_text(encoding='utf-8', errors='replace')
    except (IOError, OSError):
        return entries

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('#') or stripped.startswith(';'):
            continue

        m = _SHNTOOL_LINE_RE.match(stripped)
        if m:
            wav_fname = m.group(2).strip()
            shn_fname = re.sub(r'\.wav$', '.shn', wav_fname, flags=re.IGNORECASE)
            entries.append((shn_fname, 'shntool', m.group(1).lower()))
            continue

        m = _FFP_RE.match(stripped)
        if m:
            entries.append((m.group(1), 'ffp', m.group(2).lower()))
            continue

        m = _MD5_RE.match(stripped)
        if m:
            entries.append((m.group(2).strip(), 'md5', m.group(1).lower()))

    return entries


def _cmp(exp, actual, on_disk):
    if exp is None:
        return 'na'
    if not on_disk:
        return 'missing'
    if actual is None:
        return 'fail'
    return 'pass' if exp.lower() == actual.lower() else 'fail'


def _file_verdict(checks):
    if 'fail' in checks or 'missing' in checks:
        return 'fail'
    if checks and all(s == 'pass' for s in checks):
        return 'pass'
    return 'missing'


def verify_folder(folder_path):
    """
    Verify audio files in a folder against their standalone checksum files (.ffp, .md5, .st5).
    Returns result dict matching the /api/verify response schema.
    """
    folder = Path(folder_path)
    if not folder.exists() or not folder.is_dir():
        return {'folder': str(folder_path), 'error': 'Folder not found'}

    mode = detect_folder_mode(folder_path)
    shntool_ok = _get_shntool_cmd() is not None

    disk_audio = {f.name for f in folder.iterdir() if f.suffix.lower() in AUDIO_EXTS}

    expected = {}  # filename -> {hash_type: hash_value}
    has_ffp = has_md5 = has_shntool_entries = False

    for cf in sorted(folder.iterdir()):
        ext = cf.suffix.lower()
        if ext not in ('.ffp', '.md5', '.st5'):
            continue
        for fname, htype, hval in _parse_checksum_file(cf):
            if fname not in expected:
                expected[fname] = {}
            if ext == '.st5':
                expected[fname]['st5'] = hval
            else:
                expected[fname][htype] = hval
                if htype == 'ffp':
                    has_ffp = True
                elif htype == 'md5':
                    has_md5 = True
                elif htype == 'shntool':
                    has_shntool_entries = True

    audio_in_chk = {f for f in expected if Path(f).suffix.lower() in AUDIO_EXTS}
    extra_names = disk_audio - audio_in_chk

    missing_types = []
    if mode in ('flac', 'mixed'):
        if not has_ffp:
            missing_types.append('ffp')
        if not has_md5:
            missing_types.append('md5')
    if mode in ('shn', 'mixed'):
        if not has_md5 and 'md5' not in missing_types:
            missing_types.append('md5')
        if not shntool_ok and has_shntool_entries:
            missing_types.append('shntool')

    files = []
    n_pass = n_mismatch = n_missing = 0

    for fname in sorted(audio_in_chk):
        fpath = folder / fname
        on_disk = fpath.exists()
        ext = Path(fname).suffix.lower()
        is_flac = ext == '.flac'
        is_shn = ext == '.shn'
        exp = expected.get(fname, {})

        md5_exp = exp.get('md5')
        ffp_exp = exp.get('ffp')
        shn_exp = exp.get('shntool')
        st5_exp = exp.get('st5')

        md5_actual = compute_md5(str(fpath)) if on_disk and md5_exp is not None else None
        ffp_actual = compute_ffp(str(fpath)) if on_disk and is_flac and ffp_exp is not None else None
        shn_actual = None
        if on_disk and is_shn and shn_exp is not None and shntool_ok:
            try:
                shn_actual = compute_shntool(str(fpath))
            except ShntoolNotFoundError:
                pass

        md5_st = _cmp(md5_exp, md5_actual, on_disk)
        ffp_st = _cmp(ffp_exp, ffp_actual, on_disk)
        shn_st = _cmp(shn_exp, shn_actual, on_disk)

        if not on_disk:
            overall = 'missing'
            n_missing += 1
        else:
            checks = []
            if is_flac:
                if ffp_exp is not None:
                    checks.append(ffp_st)
                if md5_exp is not None:
                    checks.append(md5_st)
            elif is_shn:
                if md5_exp is not None:
                    checks.append(md5_st)
                if shn_exp is not None and shntool_ok:
                    checks.append(shn_st)
            else:
                if md5_exp is not None:
                    checks.append(md5_st)

            overall = _file_verdict(checks)
            if overall == 'pass':
                n_pass += 1
            elif overall == 'fail':
                n_mismatch += 1
            else:
                n_missing += 1

        files.append({
            'filename': fname,
            'md5_expected': md5_exp, 'md5_actual': md5_actual, 'md5_status': md5_st,
            'ffp_expected': ffp_exp, 'ffp_actual': ffp_actual, 'ffp_status': ffp_st,
            'shntool_expected': shn_exp, 'shntool_actual': shn_actual, 'shntool_status': shn_st,
            'st5_expected': st5_exp, 'st5_status': 'na',
            'on_disk': on_disk, 'overall': overall,
        })

    for fname in sorted(extra_names):
        files.append({
            'filename': fname,
            'md5_expected': None, 'md5_actual': None, 'md5_status': 'na',
            'ffp_expected': None, 'ffp_actual': None, 'ffp_status': 'na',
            'shntool_expected': None, 'shntool_actual': None, 'shntool_status': 'na',
            'st5_expected': None, 'st5_status': 'na',
            'on_disk': True, 'overall': 'extra',
        })

    if not shntool_ok and mode == 'shn' and has_shntool_entries:
        status = 'shntool_missing'
    elif n_mismatch > 0:
        status = 'fail'
    elif n_missing > 0:
        status = 'incomplete'
    elif not has_ffp and not has_md5 and not has_shntool_entries and disk_audio:
        # Audio files present but no checksum files of any kind found
        status = 'no_checksums'
    else:
        status = 'pass'

    return {
        'folder': str(folder_path),
        'mode': mode,
        'status': status,
        'total': len(audio_in_chk),
        'pass': n_pass,
        'mismatch': n_mismatch,
        'missing': n_missing,
        'extra': len(extra_names),
        'missing_types': missing_types,
        'files': files,
    }


def verify_folder_lbdir(folder_path, lbdir_path):
    """
    Verify all files listed in a parsed lbdir*.txt against actual files on disk.
    Returns result dict matching the /api/lbdir/check response schema (superset of /api/verify).
    """
    folder = Path(folder_path)
    parsed = parse_lbdir_file(lbdir_path)

    if 'error' in parsed:
        return {'folder': str(folder_path), 'error': parsed['error']}

    mode = parsed['mode']
    shntool_ok = _get_shntool_cmd() is not None

    md5_map = dict(parsed['md5'])
    ffp_map = dict(parsed['ffp'])
    shn_map = dict(parsed['shntool'])
    len_map = {e['filename']: e for e in parsed['shntool_len']}

    all_files = set(md5_map) | set(ffp_map) | set(shn_map)
    files = []
    n_pass = n_mismatch = n_missing = 0

    for fname in sorted(all_files):
        fpath = folder / fname
        on_disk = fpath.exists()
        ext = Path(fname).suffix.lower()
        is_flac = ext == '.flac'
        is_shn = ext == '.shn'

        md5_exp = md5_map.get(fname)
        ffp_exp = ffp_map.get(fname)
        shn_exp = shn_map.get(fname)

        md5_actual = compute_md5(str(fpath)) if on_disk and md5_exp is not None else None
        ffp_actual = compute_ffp(str(fpath)) if on_disk and is_flac and ffp_exp is not None else None
        is_wav = ext == '.wav'
        shn_actual = None
        if on_disk and shn_exp is not None and shntool_ok and (is_shn or is_wav):
            try:
                shn_actual = compute_shntool(str(fpath))
            except ShntoolNotFoundError:
                pass

        md5_st = _cmp(md5_exp, md5_actual, on_disk)
        ffp_st = _cmp(ffp_exp, ffp_actual, on_disk)
        shn_st = _cmp(shn_exp, shn_actual, on_disk)

        if not on_disk:
            overall = 'missing'
            n_missing += 1
        else:
            checks = []
            if is_flac:
                if ffp_exp is not None:
                    checks.append(ffp_st)
                if md5_exp is not None:
                    checks.append(md5_st)
            elif is_shn:
                if md5_exp is not None:
                    checks.append(md5_st)
                if shn_exp is not None and shntool_ok:
                    checks.append(shn_st)
            else:
                if md5_exp is not None:
                    checks.append(md5_st)
                if shn_exp is not None and shntool_ok:
                    checks.append(shn_st)

            overall = _file_verdict(checks)
            if overall == 'pass':
                n_pass += 1
            elif overall == 'fail':
                n_mismatch += 1
            else:
                n_missing += 1

        len_info = len_map.get(fname, {})
        files.append({
            'filename': fname,
            'md5_expected': md5_exp, 'md5_actual': md5_actual, 'md5_status': md5_st,
            'ffp_expected': ffp_exp, 'ffp_actual': ffp_actual, 'ffp_status': ffp_st,
            'shntool_expected': shn_exp, 'shntool_actual': shn_actual, 'shntool_status': shn_st,
            'st5_expected': None, 'st5_status': 'na',
            'on_disk': on_disk, 'overall': overall,
            'length': len_info.get('length'),
            'expanded_size': len_info.get('expanded_size'),
            'cdr': len_info.get('cdr'),
            'wave_problems': len_info.get('wave_problems'),
            'fmt': len_info.get('fmt'),
            'ratio': len_info.get('ratio'),
        })

    missing_types = []
    if mode in ('flac', 'mixed') and not ffp_map:
        missing_types.append('ffp')
    if not md5_map:
        missing_types.append('md5')
    if mode in ('shn', 'mixed') and not shntool_ok and shn_map:
        missing_types.append('shntool')

    if not shntool_ok and mode == 'shn' and shn_map:
        status = 'shntool_missing'
    elif n_mismatch > 0:
        status = 'fail'
    elif n_missing > 0:
        status = 'incomplete'
    else:
        status = 'pass'

    return {
        'folder': str(folder_path),
        'mode': mode,
        'status': status,
        'total': len(all_files),
        'pass': n_pass,
        'mismatch': n_mismatch,
        'missing': n_missing,
        'extra': 0,
        'missing_types': missing_types,
        'files': files,
    }


def generate_checksums(folder_path):
    """
    Generate FFP and/or MD5 checksum files for audio in folder.
    Uses _lbgen_path naming to avoid overwriting existing files.
    FLAC: writes _lbgen.ffp (FFP) + _lbgen.md5 (file MD5 of all audio).
    SHN:  writes _lbgen.md5 (shntool hashes in [shntool] line format).
    Returns {'folder': ..., 'generated': [...], 'errors': [...]}.
    """
    folder = Path(folder_path)
    if not folder.exists() or not folder.is_dir():
        return {'folder': str(folder_path), 'generated': [], 'errors': ['Folder not found']}

    mode = detect_folder_mode(folder_path)
    basename = folder.name
    generated = []
    errors = []

    audio_files = sorted(f for f in folder.iterdir() if f.suffix.lower() in AUDIO_EXTS)

    if mode in ('flac', 'mixed'):
        flac_files = [f for f in audio_files if f.suffix.lower() == '.flac']
        if flac_files:
            ffp_lines = []
            for f in flac_files:
                h = compute_ffp(str(f))
                if h:
                    ffp_lines.append(f'{f.name}:{h}')
                else:
                    errors.append(f'FFP failed: {f.name}')
            if ffp_lines:
                out = _lbgen_path(folder, basename, 'ffp')
                try:
                    Path(out).write_text('\n'.join(ffp_lines) + '\n', encoding='utf-8')
                    generated.append(out)
                except OSError as e:
                    errors.append(f'Write FFP: {e}')

        md5_lines = []
        for f in audio_files:
            h = compute_md5(str(f))
            if h:
                md5_lines.append(f'{h}  {f.name}')
            else:
                errors.append(f'MD5 failed: {f.name}')
        if md5_lines:
            out = _lbgen_path(folder, basename, 'md5')
            try:
                Path(out).write_text('\n'.join(md5_lines) + '\n', encoding='utf-8')
                generated.append(out)
            except OSError as e:
                errors.append(f'Write MD5: {e}')

    if mode in ('shn', 'mixed'):
        shn_files = [f for f in audio_files if f.suffix.lower() == '.shn']
        if shn_files:
            md5_lines: list[str] = []
            shn_lines: list[str] = []

            # File MD5 requires no external tool
            for f in shn_files:
                h = compute_md5(str(f))
                if h:
                    md5_lines.append(f'{h}  {f.name}')
                else:
                    errors.append(f'MD5 failed: {f.name}')

            # Shntool audio hash; falls back to ffmpeg decode when shorten is absent
            if _get_shntool_cmd() is None:
                errors.append('shntool not found; cannot generate SHN audio checksums')
            else:
                for f in shn_files:
                    try:
                        h = compute_shntool(str(f))
                        if h:
                            shn_lines.append(f'{h}  [shntool]  {f.stem}.wav')
                        else:
                            errors.append(f'shntool failed: {f.name}')
                    except ShntoolNotFoundError:
                        errors.append('shntool not found')
                        break

            all_lines = md5_lines + shn_lines
            if all_lines:
                out = _lbgen_path(folder, basename, 'md5')
                try:
                    Path(out).write_text('\n'.join(all_lines) + '\n', encoding='utf-8')
                    generated.append(out)
                except OSError as e:
                    errors.append(f'Write MD5: {e}')

    return {'folder': str(folder_path), 'generated': generated, 'errors': errors}
