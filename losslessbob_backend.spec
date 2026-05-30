# losslessbob_backend.spec
# Backend-only onefile build — bundled inside the Electron AppImage (Linux) or
# Windows installer/portable. Run: pyinstaller losslessbob_backend.spec

import sys

# Platform-specific Watchdog observer
_watchdog = ['watchdog', 'watchdog.observers']
if sys.platform == 'linux':
    _watchdog += ['watchdog.observers.inotify']
elif sys.platform == 'darwin':
    _watchdog += ['watchdog.observers.fsevents']
elif sys.platform == 'win32':
    _watchdog += ['watchdog.observers.read_directory_changes']

# Fingerprinting stack: Linux only — large deps, matches old losslessbob_linux.spec.
_fp = []
if sys.platform == 'linux':
    _fp = [
        'numpy', 'scipy', 'scipy.signal', 'scipy.fft', 'scipy.ndimage',
        'librosa', 'librosa.core', 'soundfile', 'numba', 'llvmlite',
    ]

_excludes = ['tkinter', 'matplotlib', 'pandas', 'cv2', 'PyQt6', 'test', 'unittest']
if sys.platform != 'linux':
    _excludes += ['numpy', 'scipy', 'librosa', 'soundfile', 'numba', 'llvmlite']

# shntool.exe bundled on Windows (GPL-2 binary for SHN verification)
_datas = []
if sys.platform == 'win32':
    _datas = [('tools/shntool.exe', 'tools')]

block_cipher = None

a = Analysis(
    ['run_backend.py'],
    pathex=['.'],
    binaries=[],
    datas=_datas,
    hiddenimports=[
        'flask',
        'flask_cors',
        'werkzeug',
        'werkzeug.serving',
        'werkzeug.debug',
        'lxml',
        'lxml.etree',
        'lxml._elementpath',
        'bs4',
        'bs4.builder._lxml',
        'bs4.builder._htmlparser',
        'waitress',
        'waitress.task',
        'waitress.server',
        'requests',
        'urllib3',
        'charset_normalizer',
        'certifi',
        'sqlite3',
        '_sqlite3',
    ] + _watchdog + _fp,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=_excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='LosslessBobBackend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
