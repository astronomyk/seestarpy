#!/usr/bin/env python3
r"""
extract_seestar_api.py
======================

Catalogue the ZWO Seestar JSON-RPC API (port 4700) from the decompiled APKs and
regenerate the three reference docs at the repo top level:

    seestar_api_methods_summary_v3.0.2.md
    seestar_api_methods_summary_v3.2.0.md
    seestar_api_changes.md

Run from the repo root with the venv python:

    python tools/extract_seestar_api.py            # regenerate all three .md files
    python tools/extract_seestar_api.py --json     # dump the raw catalogue as JSON

------------------------------------------------------------------------------
WHERE THE API IS DEFINED  (so a future run on the next firmware drop is trivial)
------------------------------------------------------------------------------

Each decompiled APK contains BOTH the Android app and the device firmware (the
app uploads the firmware to the scope), so the JSON-RPC contract appears twice.

FIRMWARE  -- authoritative: what the device actually accepts.
    D:\Seestar_v<ver>\assets\iscope   is a nested package:
        iscope            bzip2          (magic "BZh9")
          -> tar
               -> deb/asiair_armhf.deb  (ar archive)
                    -> data.tar.xz      (xz)
                         -> ./home/pi/ASIAIR/bin/zwoair_imager  <- main JSON-RPC dispatch
                         -> ./home/pi/ASIAIR/bin/zwoair_guider  <- guiding / streaming
                         -> ./home/pi/ASIAIR/bin/bsa_server, air_ble, ...
    Method names are embedded as ASCII string literals in those ELF binaries.
    iscope_64 is the aarch64 build of the same firmware (identical API).
    (assets/Soft03Cmt_*.txt are comet-orbit databases, NOT changelogs.)

APP  -- supplies parameters, push-event names and error codes.
    v3.0.2  decompiled Java at  D:\Seestar_v3.0.2_decompiled\sources\ :
        com/zwoasi/kit/cmd/CmdMethod.java                 enum  -> method strings
        com/zwo/seestar/socket/MainCameraConstants.java   CMD_* / EVENT_* constants
        com/zwo/commiscope/share/MainCameraConstants.java (multi-scope variant)
        com/zwo/seestar/socket/command/*.java             encodeCommand(): method + params
        com/zwoasi/kit/service/CmdCode.java               numeric result/error codes
        com/zwoasi/kit/data/EventType.java                event-type enum
    v3.2.0  has NO decompiled sources and no jadx/apktool, so method/event
    strings are recovered from the raw  D:\Seestar_v3.2.0\classes*.dex  string
    pool.  Parameters for shared methods are carried over from v3.0.2 (the wire
    contract is keyed by method name); methods new in v3.2.0 are flagged.
"""

from __future__ import annotations

import io
import json
import os
import re
import sys
import tarfile
import tempfile

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #

APK = {
    "3.0.2": {
        "iscope": r"D:\Seestar_v3.0.2\assets\iscope",
        "sources": r"D:\Seestar_v3.0.2_decompiled\sources",
        "dex_glob": None,  # decompiled sources available, no dex parse needed
    },
    "3.2.0": {
        "iscope": r"D:\Seestar_v3.2.0\assets\iscope",
        "sources": None,  # no decompiled sources
        "dex_glob": r"D:\Seestar_v3.2.0\classes*.dex",
    },
}

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# An identifier token, used to harvest method-like names from binaries/dex.
WORD = re.compile(rb"[A-Za-z0-9_]{2,64}")
# A snake_case token that looks like an RPC method name.
SNAKE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)+$")
# Prefixes/verbs that mark a snake_case token as a plausible RPC method.
METHOD_HINT = re.compile(
    r"^(get|set|start|stop|begin|move|reset|clear|open|close|check|is|can|"
    r"scope|iscope|pi|play|add|del|delete|remove|test|cali|format|file|"
    r"shutdown|reboot|restart|save|load|update|enable|disable|goto|"
    r"select|grab|wifi|remote)_"
)


# --------------------------------------------------------------------------- #
# Firmware: bz2 -> tar -> ar(deb) -> xz(tar) -> ELF identifier tokens
# --------------------------------------------------------------------------- #

def _ar_member(deb: bytes, want: str) -> bytes | None:
    """Return a named member from a Debian ar archive."""
    assert deb[:8] == b"!<arch>\n", "not an ar archive"
    off = 8
    while off < len(deb):
        hdr = deb[off:off + 60]
        off += 60
        name = hdr[0:16].decode("ascii", "replace").strip()
        size = int(hdr[48:58].decode().strip())
        if name == want:
            return deb[off:off + size]
        off += size + (size & 1)
    return None


def firmware_tokens(version: str) -> set[str]:
    """
    All identifier tokens found in the firmware control binaries.  Cached to the
    OS temp dir because the deb+xz decompress is slow (~30-60 s, ~400 MB RAM).
    """
    cache = os.path.join(tempfile.gettempdir(), f"seestar_fw_tokens_{version}.txt")
    if os.path.exists(cache):
        with open(cache, encoding="utf-8") as fh:
            return set(fh.read().split("\n"))

    path = APK[version]["iscope"]
    sys.stderr.write(f"[fw {version}] decompressing {path} ...\n")
    with tarfile.open(path, mode="r:bz2") as outer:
        deb = None
        for m in outer:
            if m.name == "deb/asiair_armhf.deb":
                deb = outer.extractfile(m).read()
                break
    if deb is None:
        raise RuntimeError("deb/asiair_armhf.deb not found in iscope tar")

    data = _ar_member(deb, "data.tar.xz")
    if data is None:
        raise RuntimeError("data.tar.xz not found in asiair_armhf.deb")

    tokens: set[str] = set()
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:xz") as dt:
        for m in dt:
            if not m.isfile():
                continue
            # The JSON-RPC handlers live in the ASIAIR bin/ and usr/bin/ ELFs.
            if not ("/ASIAIR/bin/" in m.name or "/usr/bin/" in m.name):
                continue
            blob = dt.extractfile(m).read()
            for tok in WORD.findall(blob):
                tokens.add(tok.decode("ascii"))
    sys.stderr.write(f"[fw {version}] {len(tokens):,} identifier tokens\n")
    with open(cache, "w", encoding="utf-8") as fh:
        fh.write("\n".join(sorted(tokens)))
    return tokens


# --------------------------------------------------------------------------- #
# App v3.0.2: decompiled Java sources
# --------------------------------------------------------------------------- #

def _read(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _humanize(class_or_const: str) -> str:
    """SetSettingGainCmd -> 'set setting gain';  CMD_START_STACK -> 'start stack'."""
    s = class_or_const
    s = re.sub(r"^CMD_|^EVENT_", "", s)
    s = re.sub(r"Cmd$", "", s)
    if "_" in s and s.isupper() or "_" in s:
        s = s.replace("_", " ").lower()
    else:
        s = re.sub(r"(?<!^)(?=[A-Z])", " ", s).lower()
    return s.strip()


def parse_app_302(sources: str) -> dict:
    """Return {methods, cmd_const, events, codes} from the decompiled Java."""
    socket = os.path.join(sources, "com", "zwo", "seestar", "socket")
    main_const = os.path.join(socket, "MainCameraConstants.java")
    commi_const = os.path.join(
        sources, "com", "zwo", "commiscope", "share", "MainCameraConstants.java"
    )
    cmd_enum = os.path.join(sources, "com", "zwoasi", "kit", "cmd", "CmdMethod.java")
    code_enum = os.path.join(sources, "com", "zwoasi", "kit", "service", "CmdCode.java")
    event_enum = os.path.join(sources, "com", "zwoasi", "kit", "data", "EventType.java")
    cmd_dir = os.path.join(socket, "command")

    # 1) CMD_* and EVENT_* string constants (used by name elsewhere).
    cmd_const: dict[str, str] = {}     # CMD_FOO -> "method_string"
    events: dict[str, str] = {}        # "EventName" -> EVENT_const
    for f in (main_const, commi_const):
        if not os.path.exists(f):
            continue
        txt = _read(f)
        for const, val in re.findall(r'(CMD_\w+)\s*=\s*"([^"]+)"', txt):
            cmd_const.setdefault(const, val)
        for const, val in re.findall(r'(EVENT_\w+)\s*=\s*"([^"]+)"', txt):
            events.setdefault(val, const)

    # 2) Master method table.  name -> {params, purpose, sources}
    methods: dict[str, dict] = {}

    def add(name: str, params=None, purpose="", source=""):
        rec = methods.setdefault(
            name, {"params": [], "purpose": "", "sources": []}
        )
        for p in params or []:
            if p not in rec["params"]:
                rec["params"].append(p)
        if purpose and not rec["purpose"]:
            rec["purpose"] = purpose
        if source and source not in rec["sources"]:
            rec["sources"].append(source)

    # 2a) Every CMD_* constant value is an API method name.
    for const, val in cmd_const.items():
        add(val, purpose=_humanize(const), source="MainCameraConstants")

    # 2b) CmdMethod enum (resolve literal or CMD_ reference).
    if os.path.exists(cmd_enum):
        txt = _read(cmd_enum)
        for m in re.finditer(
            r'new CmdMethod\("(\w+)",\s*\d+,\s*'
            r'(?:"([^"]+)"|MainCameraConstants\.(\w+))\)',
            txt,
        ):
            enum_name, literal, const_ref = m.groups()
            val = literal or cmd_const.get(const_ref)
            if val:
                add(val, purpose=_humanize(enum_name), source="CmdMethod")

    # 2c) Command builder classes: encodeCommand() -> method + params.
    SKIP_KEYS = {"id", "method", "params"}
    if os.path.isdir(cmd_dir):
        for fn in sorted(os.listdir(cmd_dir)):
            if not fn.endswith("Cmd.java"):
                continue
            txt = _read(os.path.join(cmd_dir, fn))
            mm = re.search(
                r'Param\.METHOD,\s*(?:"([^"]+)"|MainCameraConstants\.(\w+))', txt
            )
            if not mm:
                continue
            literal, const_ref = mm.groups()
            name = literal or cmd_const.get(const_ref)
            if not name:
                continue
            params = [
                k for k in re.findall(r'\.put\("([^"]+)"', txt)
                if k not in SKIP_KEYS
            ]
            add(
                name,
                params=params,
                purpose=_humanize(fn[:-5]),
                source=f"command/{fn[:-5]}",
            )

    # 3) Error / result codes.
    codes: dict[str, str] = {}
    if os.path.exists(code_enum):
        txt = _read(code_enum)
        for enum_name, num in re.findall(r'new CmdCode\("(\w+)",\s*\d+,\s*(-?\d+)\)', txt):
            codes[num] = enum_name

    # 4) Event-type enum -> event string names (augment EVENT_* constants).
    if os.path.exists(event_enum):
        txt = _read(event_enum)
        for enum_name, val in re.findall(r'new EventType\("(\w+)",\s*\d+,\s*"([^"]+)"', txt):
            events.setdefault(val, enum_name)

    return {"methods": methods, "cmd_const": cmd_const, "events": events, "codes": codes}


# --------------------------------------------------------------------------- #
# App v3.2.0: raw dex string pool
# --------------------------------------------------------------------------- #

def dex_tokens(dex_glob: str) -> set[str]:
    import glob
    toks: set[str] = set()
    for f in glob.glob(dex_glob):
        with open(f, "rb") as fh:
            blob = fh.read()
        for tok in WORD.findall(blob):
            toks.add(tok.decode("ascii"))
    return toks


# --------------------------------------------------------------------------- #
# Curated vocabulary: methods the device supports but the official app may not
# expose, gathered from the repo's hand-verified reference docs + the SDK.
# The firmware ELF string pool is polluted with internal C-library symbols
# (mbedTLS, CFITSIO, BlueZ, wpa_supplicant), so it cannot be enumerated by
# pattern alone. These curated lists name *real* RPC methods; we keep only the
# ones a firmware actually contains, so firmware presence stays the truth check.
# --------------------------------------------------------------------------- #

CURATED_SOURCES = [
    ("seestar_alp_methods.md", "seestar_alp"),
    ("claude_found_the_plan_methods.md", "plan_ref"),
]


def curated_methods() -> dict[str, str]:
    """name -> provenance label, harvested from in-repo references + the SDK."""
    import glob
    found: dict[str, str] = {}
    for fn, label in CURATED_SOURCES:
        p = os.path.join(REPO, fn)
        if not os.path.exists(p):
            continue
        for tok in re.findall(r"[a-z][a-z0-9_]{3,}", _read(p)):
            if SNAKE.match(tok) and METHOD_HINT.match(tok):
                found.setdefault(tok, label)
    # SDK: prefer explicit method strings, fall back to verb-prefixed tokens.
    for f in glob.glob(os.path.join(REPO, "src", "seestarpy", "**", "*.py"),
                       recursive=True):
        txt = _read(f)
        for tok in re.findall(r'"method"\s*:\s*"([a-z0-9_]+)"', txt):
            found.setdefault(tok, "sdk")
        for tok in re.findall(r"[a-z][a-z0-9_]{3,}", txt):
            if SNAKE.match(tok) and METHOD_HINT.match(tok):
                found.setdefault(tok, "sdk")
    return found


# --------------------------------------------------------------------------- #
# Categorisation
# --------------------------------------------------------------------------- #

def categorize(name: str) -> str:
    if name.startswith("scope_"):
        return "Mount / scope motion"
    if name.startswith("pi_"):
        return "Device / Raspberry-Pi system"
    if name.startswith("iscope_"):
        return "iScope session (view/stack/scan)"
    if "stack" in name:
        return "Stacking"
    if "plan" in name or "view_plan" in name:
        return "Observation plans"
    if "stream" in name or "img" in name or "image" in name:
        return "Imaging / streaming"
    if "focus" in name or "focuse" in name:
        return "Focus"
    if "wifi" in name or "ap" == name.split("_")[-1] or "station" in name:
        return "Network / WiFi"
    if "polar" in name or "compass" in name or "align" in name or "calib" in name:
        return "Alignment / calibration"
    if name.startswith("get_") or name.startswith("set_"):
        return "Settings / getters"
    return "Other"


# --------------------------------------------------------------------------- #
# Build the full catalogue
# --------------------------------------------------------------------------- #

def build() -> dict:
    fw302 = firmware_tokens("3.0.2")
    fw320 = firmware_tokens("3.2.0")
    app302 = parse_app_302(APK["3.0.2"]["sources"])
    dex320 = dex_tokens(APK["3.2.0"]["dex_glob"])

    # Canonical vocabulary: official-app methods (with params/purpose) ...
    vocab = app302["methods"]
    official = set(vocab)  # names the official v3.0.2 app references
    # ... augmented with curated reference/SDK methods that a firmware confirms.
    fw_any = fw302 | fw320
    for name, label in curated_methods().items():
        if name in vocab or name not in fw_any:
            continue
        vocab[name] = {"params": [], "purpose": _humanize(name), "sources": [label]}

    # v3.0.2 records: in this version's firmware, or referenced by the v3.0.2 app.
    rec302 = {}
    for name, info in vocab.items():
        in_fw = name in fw302
        if not (in_fw or name in official):
            continue
        rec302[name] = {
            **info,
            "category": categorize(name),
            "in_firmware": in_fw,
            "in_app": name in official,
        }

    # v3.2.0 records: in this version's firmware, or referenced by the app dex.
    rec320 = {}
    for name, info in vocab.items():
        in_fw = name in fw320
        in_app = name in dex320
        if in_fw or in_app:
            rec320[name] = {
                **info,
                "category": categorize(name),
                "in_firmware": in_fw,
                "in_app": in_app,
                "new": in_fw and name not in fw302,
            }
    # Discover methods entirely new to v3.2.0: present in the v3.2.0 firmware AND
    # referenced by the app dex (the dex never contains C-library symbols, so
    # this intersection is high-precision), absent from the v3.0.2 firmware and
    # the existing vocabulary.
    for tok in sorted(fw320 & dex320):
        if (tok in vocab or tok in fw302
                or not SNAKE.match(tok) or not METHOD_HINT.match(tok)):
            continue
        rec320[tok] = {
            "params": [],
            "purpose": _humanize(tok),
            "sources": ["firmware:zwoair_imager", "dex"],
            "category": categorize(tok),
            "in_firmware": True,
            "in_app": True,
            "new": True,
        }

    # SDK-emitted method names (explicit `"method":"x"` call sites in seestarpy)
    # that no firmware string table contains -- likely unsupported or routed via
    # stop_func; surfaced as a caveat rather than listed as device methods.
    import glob
    sdk_explicit: set[str] = set()
    for f in glob.glob(os.path.join(REPO, "src", "seestarpy", "**", "*.py"),
                       recursive=True):
        for tok in re.findall(r'"method"\s*:\s*"([a-z0-9_]+)"', _read(f)):
            sdk_explicit.add(tok)
    client_only = sorted(sdk_explicit - fw_any)

    return {
        "client_only": client_only,
        "v3.0.2": {
            "methods": rec302,
            "events": app302["events"],
            "codes": app302["codes"],
        },
        "v3.2.0": {
            "methods": rec320,
            "events": {e: c for e, c in app302["events"].items()
                       if e in dex320},  # event names still present in dex
            "codes": app302["codes"],
        },
    }


# --------------------------------------------------------------------------- #
# Markdown rendering
# --------------------------------------------------------------------------- #

def _method_table(methods: dict, show_new=False) -> str:
    by_cat: dict[str, list] = {}
    for name, r in methods.items():
        by_cat.setdefault(r["category"], []).append((name, r))
    out = []
    for cat in sorted(by_cat):
        out.append(f"\n### {cat}\n")
        if show_new:
            out.append("| method | params | purpose | firmware | app | new |")
            out.append("|---|---|---|:--:|:--:|:--:|")
        else:
            out.append("| method | params | purpose | firmware | app |")
            out.append("|---|---|---|:--:|:--:|")
        for name, r in sorted(by_cat[cat]):
            params = ", ".join(f"`{p}`" for p in r["params"]) or "—"
            fw = "✓" if r["in_firmware"] else "·"
            ap = "✓" if r["in_app"] else "·"
            row = f"| `{name}` | {params} | {r['purpose']} | {fw} | {ap} |"
            if show_new:
                row += " 🆕 |" if r.get("new") else "  |"
            out.append(row)
    return "\n".join(out)


def render_version(version: str, data: dict, cat: dict) -> str:
    methods = cat["methods"]
    n_fw = sum(1 for r in methods.values() if r["in_firmware"])
    if version == "3.0.2":
        src = (
            "**App source** — decompiled Java at "
            "`D:\\Seestar_v3.0.2_decompiled\\sources\\`:\n"
            "- `com/zwoasi/kit/cmd/CmdMethod.java`\n"
            "- `com/zwo/seestar/socket/MainCameraConstants.java` "
            "(+ `com/zwo/commiscope/share/MainCameraConstants.java`)\n"
            "- `com/zwo/seestar/socket/command/*.java` (params + purpose)\n"
            "- `com/zwoasi/kit/service/CmdCode.java`, "
            "`com/zwoasi/kit/data/EventType.java`\n"
        )
    else:
        src = (
            "**App source** — no decompiled sources exist for v3.2.0, so method/"
            "event names were recovered from the raw `D:\\Seestar_v3.2.0\\"
            "classes*.dex` string pool. Parameters & purpose are inherited from "
            "v3.0.2 for shared methods; methods marked 🆕 are new in v3.2.0 and "
            "their params need a manual dex decompile (see `seestar_api_changes.md`).\n"
        )
    head = f"""# Seestar JSON-RPC API — method catalogue (APK v{version})

> Generated by `tools/extract_seestar_api.py`. Re-run after a firmware bump:
> `python tools/extract_seestar_api.py`

The Seestar exposes a JSON-RPC API on TCP port 4700. Every request is
`{{"id":<n>,"method":"<name>","params":{{...}}}}` terminated by `\\r\\n`.

## Sources

**Firmware (authoritative)** — `D:\\Seestar_v{version}\\assets\\iscope`
(bzip2 → tar → `deb/asiair_armhf.deb` → `data.tar.xz` → ELF binaries under
`home/pi/ASIAIR/bin/`; the JSON-RPC dispatch lives in **`zwoair_imager`**, with
streaming in `zwoair_guider`). Method names are ASCII string literals in those
binaries; the **firmware** column marks names found there ({n_fw} of
{len(methods)}).

{src}
**Supplementary vocabulary** — the firmware ELF string table is polluted with
internal C-library symbols (mbedTLS, CFITSIO, BlueZ, wpa_supplicant), so it
cannot be enumerated by pattern alone. Method names the official app does not
expose were taken from the repo's hand-verified references
(`seestar_alp_methods.md`, `claude_found_the_plan_methods.md`) and the
`seestarpy` SDK, and kept only when the firmware actually contains them.

A `✓` in **firmware** means the name is present in the device binaries; a `✓` in
**app** means the app references it. Rows with **firmware** ✓ / **app** · are
methods the device implements but the official app does not call.

## Methods ({len(methods)})
"""
    body = _method_table(methods, show_new=(version == "3.2.0"))

    events = cat["events"]
    ev = ["\n## Push events\n", "Asynchronous `Event` messages pushed by the device.\n",
          "| event | constant |", "|---|---|"]
    for name, const in sorted(events.items()):
        ev.append(f"| `{name}` | `{const}` |")

    codes = cat["codes"]
    cd = ["\n## Result / error codes\n", "| code | name |", "|---|---|"]
    for num, name in sorted(codes.items(), key=lambda kv: int(kv[0])):
        cd.append(f"| `{num}` | `{name}` |")

    return head + body + "\n" + "\n".join(ev) + "\n" + "\n".join(cd) + "\n"


def render_changes(catalogue: dict) -> str:
    m302 = catalogue["v3.0.2"]["methods"]
    m320 = catalogue["v3.2.0"]["methods"]
    # Use firmware presence as the truth for added/removed.
    fw302 = {n for n, r in m302.items() if r["in_firmware"]}
    fw320 = {n for n, r in m320.items() if r["in_firmware"]}
    added = sorted(n for n in m320 if m320[n].get("new"))
    removed = sorted(fw302 - fw320)
    unchanged = sorted(fw302 & fw320)

    e302 = set(catalogue["v3.0.2"]["events"])
    e320 = set(catalogue["v3.2.0"]["events"])

    def lst(items):
        return "\n".join(f"- `{i}`" for i in items) if items else "_(none)_"

    client_only = lst(catalogue.get("client_only", []))

    return f"""# Seestar API changes: v3.0.2 → v3.2.0

> Generated by `tools/extract_seestar_api.py`. The diff is computed on
> **firmware** presence (the device's `zwoair_imager` binary), which is the
> ground truth for what each version accepts — not on app references.

## Summary

| | count |
|---|---|
| methods in v3.0.2 firmware | {len(fw302)} |
| methods in v3.2.0 firmware | {len(fw320)} |
| added in v3.2.0 | {len(added)} |
| removed since v3.0.2 | {len(removed)} |
| unchanged | {len(unchanged)} |

## Methods added in v3.2.0

These appear in the v3.2.0 firmware (and dex) but not the v3.0.2 vocabulary.
Their parameters are not yet known — decompile `classes*.dex` (no jadx was
available at generation time) to recover the `params` for each.

{lst(added)}

## Methods removed since v3.0.2

Present in v3.0.2 firmware, absent from v3.2.0 firmware.

{lst(removed)}

## Push events

Event names are enumerated from the v3.0.2 app (`EVENT_*` constants +
`EventType`) and checked for presence in the v3.2.0 dex string pool. "Removed"
is reliable; **new** v3.2.0-only events cannot be auto-discovered without
decompiled v3.2.0 sources, so "added" reflects only the known v3.0.2 set.

- removed in v3.2.0: {lst(sorted(e302 - e320)) if (e302 - e320) else "_(none)_"}

## Unchanged methods ({len(unchanged)})

<details><summary>expand</summary>

{lst(unchanged)}

</details>

## Client-emitted methods absent from both firmwares

These method names are sent by the `seestarpy` SDK but appear in neither the
v3.0.2 nor the v3.2.0 firmware string table — they may be unsupported, renamed,
or routed through `stop_func`. Worth auditing in the SDK.

{client_only}

## How to regenerate (for the next firmware drop, e.g. v3.3.x)

1. Unpack the new APK so you have `D:\\Seestar_v<ver>\\` (with `assets/iscope`
   and `classes*.dex`). If jadx is available, also decompile to
   `D:\\Seestar_v<ver>_decompiled\\sources\\` for params.
2. Add the version to the `APK` dict at the top of
   `tools/extract_seestar_api.py` (firmware `iscope` path, dex glob, and
   decompiled `sources` path if you have them).
3. Run `python tools/extract_seestar_api.py`.

The firmware method names live in the ELF binaries under
`home/pi/ASIAIR/bin/` inside `assets/iscope`
(bzip2 → tar → `deb/asiair_armhf.deb` → `data.tar.xz`); `zwoair_imager` holds
the JSON-RPC dispatch. App-side params/events/codes come from the decompiled
Java (`com/zwo/seestar/socket/...`, `com/zwoasi/kit/...`) or, lacking that, the
`classes*.dex` string pool.
"""


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #

def main(argv):
    catalogue = build()
    if "--json" in argv:
        json.dump(catalogue, sys.stdout, indent=2, default=list)
        return
    files = {
        "seestar_api_methods_summary_v3.0.2.md":
            render_version("3.0.2", catalogue["v3.0.2"], catalogue["v3.0.2"]),
        "seestar_api_methods_summary_v3.2.0.md":
            render_version("3.2.0", catalogue["v3.2.0"], catalogue["v3.2.0"]),
        "seestar_api_changes.md": render_changes(catalogue),
    }
    for fn, text in files.items():
        with open(os.path.join(REPO, fn), "w", encoding="utf-8") as fh:
            fh.write(text)
        sys.stderr.write(f"wrote {fn}\n")


if __name__ == "__main__":
    main(sys.argv[1:])
