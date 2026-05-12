# losslessbob.spec
# Run: pyinstaller losslessbob.spec
# Tested with PyInstaller 6.x + Python 3.11

import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        # data/ dir is NOT bundled — it's user-specific (DB, attachments, flat files)
        # Keep data/ alongside the exe after packaging
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
        # Watchdog — platform-specific observers
        'watchdog',
        'watchdog.observers',
        'watchdog.observers.inotify',       # Linux
        'watchdog.observers.fsevents',      # macOS
        'watchdog.observers.read_directory_changes',  # Windows
        # Requests
        'requests',
        'urllib3',
        'charset_normalizer',
        'certifi',
        # SQLite3 (stdlib, but belt-and-suspenders)
        'sqlite3',
        '_sqlite3',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'PIL',
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
    exclude_binaries=True,        # use COLLECT (dir) rather than onefile
    name='LosslessBob',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,                # no console window (GUI app)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='tools/icon.ico',      # uncomment and add icon.ico to tools/ if desired
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
