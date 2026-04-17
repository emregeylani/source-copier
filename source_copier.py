#!/usr/bin/env python3
"""
source_file_copier.py
─────────────────────
Searches for source files from Input1 (folder or zip) recursively in
Input2 (target folder or zip) and copies / warns based on match count.

Usage:
    python3 source_file_copier.py <input1> <input2> ["ignored1,ignored2"]

    input1 / input2 → folder path OR .zip file path

    Third parameter is optional. Comma-separated folder names in quotes.
    Folders with these names are excluded from target search.
    Example: "build,dist,.git,__pycache__"

Logic:
    • If a zip is given, it is automatically extracted to a temporary
      subfolder next to the zip. The temp folder is deleted on exit.
    • For each source file, files with the same name are searched in the target tree.
    • 0 matches  → not found in target, skipped (info given).
    • 1 match    → source file is copied over the target.
    • 2+ matches → conflict warning, no action taken.
"""

import sys
import shutil
import zipfile
import tempfile
import atexit
from pathlib import Path
from datetime import datetime


# ── Colored terminal output ────────────────────────────────────────────────

class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    RED    = "\033[91m"
    YELLOW = "\033[93m"
    GREEN  = "\033[92m"
    CYAN   = "\033[96m"
    BLUE   = "\033[94m"
    GREY   = "\033[90m"
    WHITE  = "\033[97m"

def banner():
    print(f"""
{C.CYAN}{C.BOLD}╔══════════════════════════════════════════════╗
║        SOURCE FILE COPIER  v1.1              ║
╚══════════════════════════════════════════════╝{C.RESET}
""")

def fmt_path(p: Path) -> str:
    return f"{C.BLUE}{p}{C.RESET}"

def fmt_size(p: Path) -> str:
    try:
        s = p.stat().st_size
        for unit in ("B", "KB", "MB", "GB"):
            if s < 1024:
                return f"{s:.1f} {unit}"
            s /= 1024
        return f"{s:.1f} TB"
    except Exception:
        return "?"


# ── Zip helpers ────────────────────────────────────────────────────────────

# Track temp folders open during the run (cleaned up via atexit)
_temp_dirs: list[Path] = []

def _cleanup_temps():
    for tmp in _temp_dirs:
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)
            print(f"\n{C.GREY}🗑  Temporary folder deleted: {tmp}{C.RESET}")

atexit.register(_cleanup_temps)


def resolve_input(arg: str, label: str) -> tuple[Path, Path | None]:
    """
    Resolves the given argument as a folder or zip file.

    Returns: (folder_to_use, zip_path_or_None)
      - If not a zip, zip_path is None.
      - If zip, extracted to a temp folder next to the zip; that path is returned.
    """
    p = Path(arg).resolve()

    # ── Zip file?
    if p.suffix.lower() == ".zip":
        if not p.exists():
            print(f"{C.RED}✖  {label} zip file not found: {p}{C.RESET}")
            sys.exit(1)
        if not zipfile.is_zipfile(p):
            print(f"{C.RED}✖  {label} is not a valid zip file: {p}{C.RESET}")
            sys.exit(1)

        # Open temp folder next to the zip
        tmp_parent = p.parent
        tmp_dir = Path(tempfile.mkdtemp(
            prefix=f"_sfc_tmp_{p.stem}_",
            dir=tmp_parent,
        ))
        _temp_dirs.append(tmp_dir)

        print(f"  {C.CYAN}📦 {label} zip file is being extracted...{C.RESET}")
        print(f"     {fmt_path(p)}  →  {fmt_path(tmp_dir)}")

        with zipfile.ZipFile(p, "r") as zf:
            zf.extractall(tmp_dir)

        file_count = sum(1 for f in tmp_dir.rglob("*") if f.is_file())
        print(f"     {C.GREEN}✔  {file_count} files extracted.{C.RESET}\n")

        return tmp_dir, p

    # ── Regular folder
    if not p.exists():
        print(f"{C.RED}✖  {label} not found: {p}{C.RESET}")
        sys.exit(1)
    if not p.is_dir():
        print(f"{C.RED}✖  {label} is neither a folder nor a zip file: {p}{C.RESET}")
        sys.exit(1)

    return p, None


# ── Core logic ─────────────────────────────────────────────────────────────

def collect_sources(folder: Path) -> list[Path]:
    """Return all files (recursive) inside Input1."""
    return [p for p in folder.rglob("*") if p.is_file()]


def find_matches(filename: str, root: Path, ignored: set) -> list[Path]:
    """Search recursively for files with the given name under root; skip ignored folders."""
    results = []
    for p in root.rglob(filename):
        if not p.is_file():
            continue
        if ignored and ignored.intersection(set(p.parts)):
            continue
        results.append(p)
    return results


def run(src_arg: str, dst_arg: str, ignored: set):
    banner()

    # ── Resolve inputs (extract if zip)
    src_root, src_zip = resolve_input(src_arg, "INPUT1 (source)")
    dst_root, dst_zip = resolve_input(dst_arg, "INPUT2 (target)")

    # ── Header info
    src_label = f"{src_zip}  {C.GREY}(zip → {src_root}){C.RESET}" if src_zip else str(src_root)
    dst_label = f"{dst_zip}  {C.GREY}(zip → {dst_root}){C.RESET}" if dst_zip else str(dst_root)

    print(f"  {C.BOLD}Source         :{C.RESET} {C.BLUE}{src_label}{C.RESET}")
    print(f"  {C.BOLD}Target         :{C.RESET} {C.BLUE}{dst_label}{C.RESET}")
    if ignored:
        print(f"  {C.BOLD}Ignored folders:{C.RESET} {C.YELLOW}{', '.join(sorted(ignored))}{C.RESET}")
    print(f"  {C.BOLD}Started        :{C.RESET} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    print(f"{C.GREY}{'─'*60}{C.RESET}\n")

    sources = collect_sources(src_root)

    if not sources:
        print(f"{C.YELLOW}⚠  No files found in source folder.{C.RESET}")
        sys.exit(0)

    print(f"{C.BOLD}Source file count: {len(sources)}{C.RESET}\n")

    # ── Counters
    stats = {
        "copied":    0,
        "conflict":  0,
        "not_found": 0,
    }
    log: list[dict] = []

    # ── Process each source file
    for src in sources:
        rel  = src.relative_to(src_root)
        name = src.name
        matches = find_matches(name, dst_root, ignored)

        print(f"{C.BOLD}► {rel}{C.RESET}  {C.GREY}({fmt_size(src)}){C.RESET}")

        if len(matches) == 0:
            print(f"  {C.YELLOW}⊘  No match found in target.{C.RESET}")
            print(f"     {C.BOLD}Enter destination path (or press Enter to skip):{C.RESET} ", end="", flush=True)
            try:
                user_input = input().strip()
            except (EOFError, KeyboardInterrupt):
                user_input = ""

            if not user_input:
                msg = "No match found — skipped by user."
                print(f"  {C.GREY}   Skipped.{C.RESET}")
                stats["not_found"] += 1
                log.append({"file": str(rel), "status": "NOT_FOUND", "detail": msg})
            else:
                manual_dst = Path(user_input).expanduser().resolve()
                if manual_dst.is_dir():
                    # User gave a folder → place file inside it
                    manual_dst = manual_dst / src.name
                if not manual_dst.parent.exists():
                    print(f"  {C.RED}✖  Directory does not exist: {manual_dst.parent} — skipped.{C.RESET}")
                    stats["not_found"] += 1
                    log.append({"file": str(rel), "status": "NOT_FOUND", "detail": f"Manual path invalid: {manual_dst}"})
                else:
                    old_size = fmt_size(manual_dst) if manual_dst.exists() else "—"
                    try:
                        shutil.copy2(src, manual_dst)
                        print(f"  {C.GREEN}✔  Copied  →  {fmt_path(manual_dst)}")
                        print(f"     Old size: {old_size}  |  New size: {fmt_size(manual_dst)}{C.RESET}")
                        stats["copied"] += 1
                        log.append({
                            "file":   str(rel),
                            "status": "COPIED",
                            "detail": f"→ {manual_dst} (manual)  [old: {old_size}, new: {fmt_size(manual_dst)}]",
                        })
                    except Exception as e:
                        print(f"  {C.RED}✖  Copy error: {e}{C.RESET}")
                        log.append({"file": str(rel), "status": "ERROR", "detail": str(e)})

        elif len(matches) == 1:
            dst = matches[0]
            old_size = fmt_size(dst)
            try:
                shutil.copy2(src, dst)
                print(f"  {C.GREEN}✔  Copied  →  {fmt_path(dst.relative_to(dst_root))}")
                print(f"     Old size: {old_size}  |  New size: {fmt_size(dst)}{C.RESET}")
                stats["copied"] += 1
                log.append({
                    "file":   str(rel),
                    "status": "COPIED",
                    "detail": f"→ {dst}  [old: {old_size}, new: {fmt_size(dst)}]",
                })
            except Exception as e:
                print(f"  {C.RED}✖  Copy error: {e}{C.RESET}")
                log.append({"file": str(rel), "status": "ERROR", "detail": str(e)})

        else:
            print(f"  {C.YELLOW}⚠  CONFLICT — {len(matches)} matches found, no action taken:{C.RESET}")
            for m in matches:
                print(f"     {C.YELLOW}• {m}{C.RESET}")
            stats["conflict"] += 1
            log.append({
                "file":   str(rel),
                "status": "CONFLICT",
                "detail": f"{len(matches)} matches: " + " | ".join(str(m) for m in matches),
            })

        print()

    # ── Summary report
    status_meta = {
        "COPIED":    (C.GREEN,  "✔", "COPIED     "),
        "CONFLICT":  (C.YELLOW, "⚠", "CONFLICT   "),
        "NOT_FOUND": (C.GREY,   "⊘", "NOT FOUND  "),
        "ERROR":     (C.RED,    "✖", "ERROR      "),
    }

    print(f"{C.GREY}{'─'*60}{C.RESET}")
    print(f"\n{C.BOLD}{C.WHITE}  SUMMARY REPORT  ({len(log)} files){C.RESET}\n")

    for entry in log:
        color, icon, label = status_meta.get(entry["status"], (C.WHITE, "?", entry["status"]))
        print(f"  {color}{icon} {label}  {C.BOLD}{entry['file']}{C.RESET}")
        print(f"           {C.GREY}{entry['detail']}{C.RESET}")

    print(f"\n{C.GREY}{'─'*60}{C.RESET}")
    print(f"  {C.GREEN}✔  Copied          : {stats['copied']}{C.RESET}")
    print(f"  {C.YELLOW}⚠  Conflicts (skip): {stats['conflict']}{C.RESET}")
    print(f"  {C.GREY}⊘  Not found       : {stats['not_found']}{C.RESET}")
    print(f"\n  {C.BOLD}Total processed   : {len(sources)}{C.RESET}")
    print(f"  {C.BOLD}Finished          : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{C.RESET}\n")

    # ── Detailed log file
    log_path = Path("copy_report.log")
    with log_path.open("w", encoding="utf-8") as f:
        f.write("SOURCE FILE COPIER — Report\n")
        f.write(f"Date    : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Source  : {src_zip or src_root}\n")
        f.write(f"Target  : {dst_zip or dst_root}\n")
        if ignored:
            f.write(f"Ignored : {', '.join(sorted(ignored))}\n")
        f.write("─" * 60 + "\n\n")
        for entry in log:
            f.write(f"[{entry['status']:10s}]  {entry['file']}\n")
            f.write(f"             {entry['detail']}\n\n")
        f.write("─" * 60 + "\n")
        f.write(f"Copied: {stats['copied']}  |  "
                f"Conflicts: {stats['conflict']}  |  "
                f"Not found: {stats['not_found']}\n")

    print(f"  {C.CYAN}📄 Detailed log saved: {log_path.resolve()}{C.RESET}\n")

    # ── Option to delete zip files
    for zip_path, label in [(src_zip, "Source (INPUT1)"), (dst_zip, "Target (INPUT2)")]:
        if zip_path and zip_path.exists():
            print(f"  {C.YELLOW}🗜  Delete {label} zip file?{C.RESET}")
            print(f"     {fmt_path(zip_path)}")
            print(f"  {C.BOLD}[Enter/Y = Yes, any other key = No]: {C.RESET}", end="", flush=True)
            try:
                answer = input().strip().lower()
            except (EOFError, KeyboardInterrupt):
                answer = ""

            if answer in ("", "y", "yes"):
                try:
                    zip_path.unlink()
                    print(f"  {C.GREEN}✔  Deleted: {zip_path}{C.RESET}\n")
                except Exception as ex:
                    print(f"  {C.RED}✖  Could not delete: {ex}{C.RESET}\n")
            else:
                print(f"  {C.GREY}   Skipped, zip kept.{C.RESET}\n")

    # atexit → temp folders are deleted automatically


# ── Entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) not in (3, 4):
        print(f"\n{C.YELLOW}Usage: python3 source_file_copier.py <input1> <input2> [\"ignored1,ignored2\"]")
        print(f"  input1 / input2 → folder path or .zip file{C.RESET}\n")
        sys.exit(1)

    ignored: set = set()
    if len(sys.argv) == 4:
        ignored = {name.strip() for name in sys.argv[3].split(",") if name.strip()}

    run(sys.argv[1], sys.argv[2], ignored)
