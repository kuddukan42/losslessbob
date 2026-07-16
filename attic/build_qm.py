"""Pure-Python .ts → .qm compiler, matching Qt 6 QTranslator format exactly.

Format derived from Qt 6 src/corelib/kernel/qtranslator.cpp and confirmed by
inspecting real lrelease output.

Structure:
    [16 bytes: QM_MAGIC]
    [section 0x42: Hashes — sorted (hash, offset) pairs, 8 bytes each]
    [section 0x69: Messages — records at offsets referenced by Hashes]

Each message record (no length prefix):
    [1 byte: 3=Translation][4 bytes: len][N bytes: UTF-16BE]
    [1 byte: 8=Comment][4 bytes: 0]
    [1 byte: 6=SourceText][4 bytes: len][N bytes: UTF-8]
    [1 byte: 7=Context][4 bytes: len][N bytes: UTF-8]
    [1 byte: 1=End]

Usage:
    python scripts/build_qm.py
"""
from __future__ import annotations

import struct
import xml.etree.ElementTree as ET
from pathlib import Path

LOCALES_DIR = Path(__file__).parent.parent / "gui" / "locales"
LANGUAGES   = ["de", "fr", "es", "it", "nl"]

# Top-level section tags
SECTION_HASHES   = 0x42
SECTION_MESSAGES = 0x69

# Message record sub-tags (from Qt 6 qtranslator.cpp enum Tag)
TAG_END         = 1
TAG_TRANSLATION = 3
TAG_COMMENT     = 8
TAG_SOURCE      = 6
TAG_CONTEXT     = 7

QM_MAGIC = bytes([
    0x3C, 0xB8, 0x64, 0x18, 0xCA, 0xEF, 0x9C, 0x95,
    0xCD, 0x21, 0x1C, 0xBF, 0x60, 0xA1, 0xBD, 0xDD,
])


# ── Qt ELF hash (from Qt 6 qtranslator.cpp) ──────────────────────────────────

def _qt_hash(source: str, comment: str = "") -> int:
    """Hash matching Qt 6 elfHash_continue(source)+elfHash_continue(comment)+elfHash_finish."""
    h = 0
    for s in (source, comment):
        for byte in s.encode("utf-8"):
            h = ((h << 4) + byte) & 0xFFFFFFFF
            g = h & 0xF0000000
            if g:
                h ^= g >> 24  # Qt uses >>24, not >>23
            h &= (0xFFFFFFFF ^ g)
    if not h:
        h = 1  # elfHash_finish: map 0 → 1
    return h


# ── Binary helpers ────────────────────────────────────────────────────────────

def _u8(n: int) -> bytes:
    return struct.pack(">B", n)

def _u32(n: int) -> bytes:
    return struct.pack(">I", n)

def _subtag(tag: int, data: bytes) -> bytes:
    """1-byte tag + 4-byte big-endian length + data."""
    return _u8(tag) + _u32(len(data)) + data

def _section(tag: int, data: bytes) -> bytes:
    """1-byte section tag + 4-byte big-endian length + data."""
    return _u8(tag) + _u32(len(data)) + data


# ── Message record ────────────────────────────────────────────────────────────

def _message_record(source: str, context: str, translation: str) -> bytes:
    """Build one message record — no outer length prefix."""
    record = bytearray()
    record += _subtag(TAG_TRANSLATION, translation.encode("utf-16-be"))
    record += _subtag(TAG_COMMENT, b"")
    record += _subtag(TAG_SOURCE, source.encode("utf-8"))
    record += _subtag(TAG_CONTEXT, context.encode("utf-8"))
    record += _u8(TAG_END)
    return bytes(record)


# ── Compiler ──────────────────────────────────────────────────────────────────

def compile_ts(ts_path: Path, qm_path: Path) -> None:
    tree = ET.parse(ts_path)
    root = tree.getroot()

    entries: list[tuple[int, str, str, str]] = []  # (hash, source, context, translation)

    for ctx_el in root.findall("context"):
        ctx_name = ctx_el.findtext("name") or ""
        for msg_el in ctx_el.findall("message"):
            source = msg_el.findtext("source") or ""
            trans_el = msg_el.find("translation")
            if trans_el is None:
                continue
            if trans_el.get("type") == "unfinished":
                continue
            translation = trans_el.text or ""
            if not source or not translation:
                continue
            entries.append((_qt_hash(source), source, ctx_name, translation))

    # Build Messages section, recording each record's starting offset
    messages_buf = bytearray()
    hash_offset_pairs: list[tuple[int, int]] = []

    for h, source, context, translation in entries:
        offset = len(messages_buf)
        hash_offset_pairs.append((h, offset))
        messages_buf += _message_record(source, context, translation)

    # Sort by hash for Qt's binary search
    hash_offset_pairs.sort(key=lambda x: x[0])

    # Build Hashes section: [u32(hash)][u32(offset)] per entry
    hashes_buf = bytearray()
    for h, offset in hash_offset_pairs:
        hashes_buf += _u32(h)
        hashes_buf += _u32(offset)

    qm = bytearray()
    qm += QM_MAGIC
    qm += _section(SECTION_HASHES, bytes(hashes_buf))
    qm += _section(SECTION_MESSAGES, bytes(messages_buf))

    qm_path.write_bytes(bytes(qm))
    print(f"  {qm_path.name}: {len(entries)} messages, {len(qm):,} bytes")


def main() -> None:
    for lang in LANGUAGES:
        ts_path = LOCALES_DIR / f"losslessbob_{lang}.ts"
        qm_path = LOCALES_DIR / f"losslessbob_{lang}.qm"
        if not ts_path.exists():
            print(f"  SKIP: {ts_path.name} not found")
            continue
        compile_ts(ts_path, qm_path)
    print("Done.")


if __name__ == "__main__":
    main()
