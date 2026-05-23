# losslessbob_linux.spec
# Run: pyinstaller losslessbob_linux.spec
# Linux build — includes fingerprinting stack (numpy/scipy/librosa/soundfile/numba).

import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        # data/ dir is NOT bundled — it's user-specific (DB, attachments, flat files)
    ],
    hiddenimports=[
        # Flask / Werkzeug internals PyInstaller misses
        'flask',
        'flask_cors',
        'werkzeug',
        'werkzeug.serving',
        'werkzeug.debug',
        # PyQt6 WebEngine — not always auto-detected
        'PyQt6.QtWebEngineWidgets',
        'PyQt6.QtWebEngineCore',
        'PyQt6.QtWebChannel',
        # lxml backend for BeautifulSoup
        'lxml',
        'lxml.etree',
        'lxml._elementpath',
        # bs4
        'bs4',
        'bs4.builder._lxml',
        'bs4.builder._htmlparser',
        # Waitress WSGI
        'waitress',
        'waitress.task',
        'waitress.server',
        # Watchdog — Linux inotify observer
        'watchdog',
        'watchdog.observers',
        'watchdog.observers.inotify',
        # Requests
        'requests',
        'urllib3',
        'charset_normalizer',
        'certifi',
        # SQLite3 (stdlib, belt-and-suspenders)
        'sqlite3',
        '_sqlite3',
        # Fingerprinting stack (excluded from Windows build; included here)
        'numpy',
        'scipy',
        'scipy.signal',
        'scipy.fft',
        'scipy.ndimage',
        'librosa',
        'librosa.core',
        'soundfile',
        'numba',
        'llvmlite',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'pandas',
        'cv2',
        'test',
        'unittest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='LosslessBob',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='LosslessBob',
)
