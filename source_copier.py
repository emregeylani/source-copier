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
    Supports wildcard patterns (e.g. "*env*", "build", ".git").
    Example: "build,dist,.git,__pycache__,*env*"

Logic:
    • If a zip is given, it is automatically extracted to a temporary
      subfolder next to the zip. The temp folder is deleted on exit.
    • For each source file, files with the same name are searched in the target tree.
    • 0 matches  → not found in target; user prompted (default = target root,
                   relative paths are joined to target root).
    • 1 match    → source file is copied over the target.
    • 2+ matches → try to resolve by matching folder structure (e.g. db/__init__.py).
                   If exactly one candidate shares the same parent folder name(s),
                   it is used automatically. Otherwise a conflict warning is shown.
"""

import sys
import shutil
import zipfile
import tempfile
import atexit
import fnmatch
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
║        SOURCE FILE COPIER  v1.2              ║
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


# ── Ignored-pattern helpers ────────────────────────────────────────────────

def part_is_ignored(part: str, patterns: set[str]) -> bool:
    """
    Return True if *part* (a single path component) matches any pattern in
    *patterns*.  Supports plain names ("build") and wildcards ("*env*").
    """
    return any(fnmatch.fnmatch(part, pat) for pat in patterns)


def path_is_ignored(p: Path, patterns: set[str]) -> bool:
    """Return True if any component of *p* matches an ignored pattern."""
    if not patterns:
        return False
    return any(part_is_ignored(part, patterns) for part in p.parts)


# ── Core logic ─────────────────────────────────────────────────────────────

def collect_sources(folder: Path) -> list[Path]:
    """Return all files (recursive) inside Input1."""
    return [p for p in folder.rglob("*") if p.is_file()]


def find_matches(filename: str, root: Path, ignored: set[str]) -> list[Path]:
    """Search recursively for files with the given name under root; skip ignored paths."""
    results = []
    for p in root.rglob(filename):
        if not p.is_file():
            continue
        # Check each path component against wildcard-aware patterns
        if path_is_ignored(p.relative_to(root), ignored):
            continue
        results.append(p)
    return results


def resolve_by_folder_structure(src_rel: Path, matches: list[Path]) -> Path | None:
    """
    Improvement #1 – multiple matches: try to narrow down by comparing
    the source's relative path parts (parent folders) with each candidate.

    Strategy: count how many trailing path components the source and each
    candidate share (excluding the filename itself).  The candidate with
    the highest overlap — if it is strictly greater than all others — wins.

    Example:
        src_rel  = db/__init__.py   →  parents = ["db"]
        candidate A: app/db/__init__.py   → parents ending with ["db"]  ✔
        candidate B: utils/__init__.py    → parents ending with ["utils"] ✗

    Returns the winning Path, or None if no clear winner exists.
    """
    src_parts = list(src_rel.parts[:-1])  # parent folder parts (no filename)

    if not src_parts:
        # Source is in the root – cannot disambiguate by folder
        return None

    def score(candidate: Path) -> int:
        cand_parts = list(candidate.parts[:-1])  # absolute parts without filename
        # Walk src_parts in reverse and count matching suffix
        matched = 0
        for s, c in zip(reversed(src_parts), reversed(cand_parts)):
            if s == c:
                matched += 1
            else:
                break
        return matched

    scores = [(score(m), m) for m in matches]
    scores.sort(key=lambda x: x[0], reverse=True)

    best_score, best_match = scores[0]
    # Must have at least one folder match and be unique at that score
    if best_score == 0:
        return None
    if len(scores) > 1 and scores[1][0] == best_score:
        return None  # tie – cannot decide

    return best_match


def copy_file(src: Path, dst: Path, rel: Path, log: list, stats: dict, note: str = ""):
    """Perform the actual copy and update stats/log."""
    old_size = fmt_size(dst) if dst.exists() else "—"
    try:
        shutil.copy2(src, dst)
        suffix = f"  {C.GREY}({note}){C.RESET}" if note else ""
        print(f"  {C.GREEN}✔  Copied  →  {fmt_path(dst)}{suffix}")
        print(f"     Old size: {old_size}  |  New size: {fmt_size(dst)}{C.RESET}")
        stats["copied"] += 1
        log.append({
            "file":   str(rel),
            "status": "COPIED",
            "detail": f"→ {dst}  [old: {old_size}, new: {fmt_size(dst)}]{(' (' + note + ')') if note else ''}",
        })
    except Exception as e:
        print(f"  {C.RED}✖  Copy error: {e}{C.RESET}")
        log.append({"file": str(rel), "status": "ERROR", "detail": str(e)})


def run(src_arg: str, dst_arg: str, ignored: set[str]):
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
        print(f"  {C.BOLD}Ignored patterns:{C.RESET} {C.YELLOW}{', '.join(sorted(ignored))}{C.RESET}")
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
        rel     = src.relative_to(src_root)
        name    = src.name
        matches = find_matches(name, dst_root, ignored)

        print(f"{C.BOLD}► {rel}{C.RESET}  {C.GREY}({fmt_size(src)}){C.RESET}")

        # ── 0 matches: not found ──────────────────────────────────────────
        if len(matches) == 0:
            print(f"  {C.YELLOW}⊘  No match found in target.{C.RESET}")
            print(
                f"     {C.BOLD}Enter destination path "
                f"{C.GREY}(Enter = {dst_root}  |  relative path joined to target root):{C.RESET} ",
                end="", flush=True,
            )
            try:
                user_input = input().strip()
            except (EOFError, KeyboardInterrupt):
                user_input = ""

            # ── Improvement #2: default = target root; relative → joined to target root
            if not user_input:
                # No input → place file directly inside target root
                manual_dst = dst_root / src.name
            else:
                given = Path(user_input).expanduser()
                if given.is_absolute():
                    manual_dst = given.resolve()
                else:
                    # Relative path → join to target root
                    manual_dst = (dst_root / given).resolve()

            # If the resolved destination is a directory, place file inside it
            if manual_dst.is_dir():
                manual_dst = manual_dst / src.name

            if not manual_dst.parent.exists():
                print(
                    f"  {C.RED}✖  Directory does not exist: "
                    f"{manual_dst.parent} — skipped.{C.RESET}"
                )
                stats["not_found"] += 1
                log.append({
                    "file":   str(rel),
                    "status": "NOT_FOUND",
                    "detail": f"Manual path invalid: {manual_dst}",
                })
            else:
                copy_file(src, manual_dst, rel, log, stats, note="manual")

        # ── 1 match: straightforward copy ────────────────────────────────
        elif len(matches) == 1:
            copy_file(src, matches[0], rel, log, stats)

        # ── 2+ matches: try folder-structure disambiguation ───────────────
        else:
            winner = resolve_by_folder_structure(rel, matches)

            if winner is not None:
                print(
                    f"  {C.CYAN}🔍 {len(matches)} matches found — resolved by folder structure:{C.RESET}"
                )
                for m in matches:
                    marker = f"  {C.GREEN}✔ (selected){C.RESET}" if m == winner else f"  {C.GREY}(skipped){C.RESET}"
                    print(f"     {C.CYAN}• {m}{marker}")
                copy_file(src, winner, rel, log, stats, note="resolved by folder match")
            else:
                print(
                    f"  {C.YELLOW}⚠  CONFLICT — {len(matches)} matches found, "
                    f"no folder-structure winner, no action taken:{C.RESET}"
                )
                for m in matches:
                    print(f"     {C.YELLOW}• {m}{C.RESET}")
                stats["conflict"] += 1
                log.append({
                    "file":   str(rel),
                    "status": "CONFLICT",
                    "detail": f"{len(matches)} matches: " + " | ".join(str(m) for m in matches),
                })

        print()

    # ── Summary report ─────────────────────────────────────────────────────
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
        print(f"\n{C.YELLOW}Usage: python3 source_file_copier.py <source> <target> [\"ignored1,ignored2\"]")
        print(f"  source  / target  → folder path or .zip file")
        print(f"  ignored           → comma-separated names/patterns (wildcards OK, e.g. *env*){C.RESET}\n")
        sys.exit(1)

    ignored: set[str] = set()
    if len(sys.argv) == 4:
        ignored = {name.strip() for name in sys.argv[3].split(",") if name.strip()}

    # ── Pre-flight confirmation ────────────────────────────────────────────
    ignored_display = ", ".join(sorted(ignored)) if ignored else "(none)"
    print(f"\n  {C.BOLD}Source  :{C.RESET} {C.BLUE}{sys.argv[1]}{C.RESET}")
    print(f"  {C.BOLD}Target  :{C.RESET} {C.BLUE}{sys.argv[2]}{C.RESET}")
    print(f"  {C.BOLD}Ignored :{C.RESET} {C.YELLOW}{ignored_display}{C.RESET}")
    print(f"\n  {C.BOLD}Ready to start? {C.GREY}[Y/Enter = Start, n/N = Stop]:{C.RESET} ", end="", flush=True)

    try:
        answer = input().strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = "n"

    if answer in ("n", "no"):
        print(f"\n  {C.GREY}Aborted.{C.RESET}\n")
        sys.exit(0)

    run(sys.argv[1], sys.argv[2], ignored)
