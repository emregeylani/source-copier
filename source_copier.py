#!/usr/bin/env python3
"""
source_copier.py
─────────────────────
Searches for source files from Input1 (folder or zip) recursively in
Input2 (target folder or zip) and copies / warns based on match count.

Usage:
    python3 source_copier.py <input1> <input2> ["ignored1,ignored2"]
    python3 source_copier.py <input1> p:<profile>
    python3 source_copier.py --profiles

    input1 / input2 → folder path OR .zip file path

    Third parameter is optional. Comma-separated folder names in quotes.
    Folders with these names are excluded from target search.
    Supports wildcard patterns (e.g. "*env*", "build", ".git").
    Example: "build,dist,.git,__pycache__,*env*"

    Profile mode: place a profiles.ini next to this script.
    Pass p:<name> instead of target path (and optionally ignored).
    Example: sc ~/Downloads/asset-manager.zip p:am

Logic:
    • If a zip is given, it is automatically extracted to a temporary
      subfolder next to the zip. The temp folder is deleted on exit.
    • For each source file, files with the same name are searched in the target tree.
    • 0 matches  → not found in target; user prompted (default = target root,
                   relative paths are joined to target root).
                   If the source's parent folder name exists uniquely in the
                   target tree, that folder is offered as a suggestion (S/Enter).
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
import configparser
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
║        SOURCE FILE COPIER  v1.5              ║
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
    p = Path(arg).expanduser().resolve()

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


# ── Profile helpers ────────────────────────────────────────────────────────

PROFILES_FILE = Path(__file__).resolve().parent / "profiles.ini"


def load_profiles() -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    if PROFILES_FILE.exists():
        cfg.read(PROFILES_FILE)
    return cfg


def list_profiles():
    """Print all available profiles and exit."""
    cfg = load_profiles()
    if not PROFILES_FILE.exists():
        print(f"\n{C.YELLOW}⚠  profiles.ini not found at:{C.RESET}")
        print(f"   {fmt_path(PROFILES_FILE)}")
        print(f"\n{C.GREY}Create it with sections like:\n")
        print(f"  [am]")
        print(f"  target  = ~/git/asset-manager")
        print(f"  ignored = __pycache__,*env*,.git\n{C.RESET}")
        sys.exit(0)

    sections = cfg.sections()
    if not sections:
        print(f"\n{C.YELLOW}⚠  profiles.ini exists but has no profiles.{C.RESET}\n")
        sys.exit(0)

    print(f"\n{C.BOLD}{C.WHITE}  Available profiles  ({PROFILES_FILE}){C.RESET}\n")
    for name in sections:
        target  = cfg[name].get("target",  "(not set)")
        ignored = cfg[name].get("ignored", "(none)")
        print(f"  {C.CYAN}{C.BOLD}[{name}]{C.RESET}")
        print(f"    target  : {C.BLUE}{target}{C.RESET}")
        print(f"    ignored : {C.YELLOW}{ignored}{C.RESET}")
        print()
    sys.exit(0)


def resolve_profile(token: str) -> tuple[str, set[str]]:
    """
    Parse a 'p:<name>' token, load the profile from profiles.ini,
    and return (target_str, ignored_set).
    """
    name = token[2:].strip()  # strip the "p:" prefix

    cfg = load_profiles()

    if not PROFILES_FILE.exists():
        print(f"\n{C.RED}✖  profiles.ini not found at:{C.RESET}")
        print(f"   {fmt_path(PROFILES_FILE)}")
        print(f"{C.YELLOW}   Create it or run with --profiles for help.{C.RESET}\n")
        sys.exit(1)

    if name not in cfg:
        available = ", ".join(cfg.sections()) or "(none)"
        print(f"\n{C.RED}✖  Profile '{name}' not found in profiles.ini.{C.RESET}")
        print(f"   {C.YELLOW}Available: {available}{C.RESET}\n")
        sys.exit(1)

    section = cfg[name]

    target = section.get("target", "").strip()
    if not target:
        print(f"\n{C.RED}✖  Profile '{name}' has no 'target' defined.{C.RESET}\n")
        sys.exit(1)

    ignored_raw = section.get("ignored", "")
    ignored = {p.strip() for p in ignored_raw.split(",") if p.strip()}

    return target, ignored


def is_profile_token(s: str) -> bool:
    return s.startswith("p:") or s.startswith("p=")


def normalize_profile_token(s: str) -> str:
    """Accept both p:am and p=am."""
    if s.startswith("p="):
        return "p:" + s[2:]
    return s


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

def collect_sources(folder: Path, ignored: set[str]) -> list[Path]:
    """Return all files (recursive) inside Input1, skipping ignored paths."""
    return [
        p for p in folder.rglob("*")
        if p.is_file() and not path_is_ignored(p.relative_to(folder), ignored)
    ]


def find_matches(filename: str, root: Path, ignored: set[str]) -> list[Path]:
    """Search recursively for files with the given name under root; skip ignored paths."""
    results = []
    for p in root.rglob(filename):
        if not p.is_file():
            continue
        if path_is_ignored(p.relative_to(root), ignored):
            continue
        results.append(p)
    return results


def find_suggested_folder(src_rel: Path, dst_root: Path, ignored: set[str]) -> Path | None:
    """
    Walk the source file's parent folder names (innermost first) and search the
    target tree for a directory with that exact name.  The first level that yields
    exactly ONE match (ignoring ignored patterns) is returned as the suggested
    destination folder.  If no level yields a unique match, return None.
    """
    src_parts = list(src_rel.parts[:-1])
    if not src_parts:
        return None

    for folder_name in reversed(src_parts):
        candidates = [
            d for d in dst_root.rglob(folder_name)
            if d.is_dir()
            and not path_is_ignored(d.relative_to(dst_root), ignored)
        ]
        if len(candidates) == 1:
            return candidates[0]

    return None


def resolve_by_folder_structure(src_rel: Path, matches: list[Path]) -> Path | None:
    """
    Try to narrow down multiple matches by comparing the source's relative
    path parts (parent folders) with each candidate.
    """
    src_parts = list(src_rel.parts[:-1])

    if not src_parts:
        return None

    def score(candidate: Path) -> int:
        cand_parts = list(candidate.parts[:-1])
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
    if best_score == 0:
        return None
    if len(scores) > 1 and scores[1][0] == best_score:
        return None

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


def run(src_arg: str, dst_arg: str, ignored: set[str], profile_name: str | None = None):
    banner()

    src_root, src_zip = resolve_input(src_arg, "INPUT1 (source)")
    dst_root, dst_zip = resolve_input(dst_arg, "INPUT2 (target)")

    src_label = f"{src_zip}  {C.GREY}(zip → {src_root}){C.RESET}" if src_zip else str(src_root)
    dst_label = f"{dst_zip}  {C.GREY}(zip → {dst_root}){C.RESET}" if dst_zip else str(dst_root)

    print(f"  {C.BOLD}Source         :{C.RESET} {C.BLUE}{src_label}{C.RESET}")
    print(f"  {C.BOLD}Target         :{C.RESET} {C.BLUE}{dst_label}{C.RESET}")
    if profile_name:
        print(f"  {C.BOLD}Profile        :{C.RESET} {C.CYAN}[{profile_name}]{C.RESET}")
    if ignored:
        print(f"  {C.BOLD}Ignored patterns:{C.RESET} {C.YELLOW}{', '.join(sorted(ignored))}{C.RESET}")
    print(f"  {C.BOLD}Started        :{C.RESET} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    print(f"{C.GREY}{'─'*60}{C.RESET}\n")

    sources = collect_sources(src_root, ignored)

    if not sources:
        print(f"{C.YELLOW}⚠  No files found in source folder.{C.RESET}")
        sys.exit(0)

    print(f"{C.BOLD}Source file count: {len(sources)}{C.RESET}\n")

    stats = {
        "copied":    0,
        "skipped":   0,
        "conflict":  0,
        "not_found": 0,
    }
    log: list[dict] = []

    for src in sources:
        rel     = src.relative_to(src_root)
        name    = src.name
        matches = find_matches(name, dst_root, ignored)

        print(f"{C.BOLD}► {rel}{C.RESET}  {C.GREY}({fmt_size(src)}){C.RESET}")

        # ── 0 matches ────────────────────────────────────────────────────
        if len(matches) == 0:
            print(f"  {C.YELLOW}⊘  New file — not found in target.{C.RESET}")

            suggested_folder = find_suggested_folder(rel, dst_root, ignored)
            suggested_dst    = suggested_folder / src.name if suggested_folder else None

            if suggested_dst:
                suggested_rel = suggested_dst.relative_to(dst_root)
                print(f"     {C.CYAN}💡 Suggested: {fmt_path(suggested_dst)}{C.RESET}")
                print(
                    f"     {C.BOLD}Destination: "
                    f"{C.GREY}[S = suggested  |  Enter = target root  |  X = skip  |  path = custom]:{C.RESET} ",
                    end="", flush=True,
                )
            else:
                print(
                    f"     {C.BOLD}Destination: "
                    f"{C.GREY}[Enter = target root  |  X = skip  |  relative/absolute path]:{C.RESET} ",
                    end="", flush=True,
                )

            try:
                user_input = input().strip()
            except (EOFError, KeyboardInterrupt):
                user_input = "x"

            if user_input.lower() in ("x", "\x1b"):
                print(f"  {C.GREY}↷  Skipped.{C.RESET}")
                stats["skipped"] += 1
                log.append({
                    "file":   str(rel),
                    "status": "SKIPPED",
                    "detail": "User skipped (new file)",
                })
            elif suggested_dst and user_input.lower() == "s":
                note = f"suggested: {suggested_rel}"
                _do_copy_manual(src, suggested_dst, rel, log, stats, note)
            elif not user_input:
                manual_dst = dst_root / src.name
                _do_copy_manual(src, manual_dst, rel, log, stats, note="target root")
            else:
                given = Path(user_input).expanduser()
                if given.is_absolute():
                    manual_dst = given.resolve()
                else:
                    manual_dst = (dst_root / given).resolve()
                _do_copy_manual(src, manual_dst, rel, log, stats, note="manual")

        # ── 1 match ──────────────────────────────────────────────────────
        elif len(matches) == 1:
            copy_file(src, matches[0], rel, log, stats)

        # ── 2+ matches ───────────────────────────────────────────────────
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
                    "file":    str(rel),
                    "status":  "CONFLICT",
                    "detail":  f"{len(matches)} matches: " + " | ".join(str(m) for m in matches),
                    "targets": [str(m) for m in matches],
                })

        print()

    # ── Summary ────────────────────────────────────────────────────────────
    status_meta = {
        "COPIED":    (C.GREEN,  "✔", "COPIED     "),
        "SKIPPED":   (C.GREY,   "↷", "SKIPPED    "),
        "CONFLICT":  (C.YELLOW, "⚠", "CONFLICT   "),
        "NOT_FOUND": (C.GREY,   "⊘", "NOT FOUND  "),
        "ERROR":     (C.RED,    "✖", "ERROR      "),
    }

    print(f"{C.GREY}{'─'*60}{C.RESET}")
    print(f"\n{C.BOLD}{C.WHITE}  SUMMARY REPORT  ({len(log)} files){C.RESET}\n")

    for entry in log:
        color, icon, label = status_meta.get(entry["status"], (C.WHITE, "?", entry["status"]))
        if entry["status"] == "CONFLICT":
            print(f"  {color}{icon} {label}  {C.BOLD}{entry['file']}{C.RESET}  {C.YELLOW}← NOT COPIED{C.RESET}")
            print(f"           {C.GREY}Source : {src_root / entry['file']}{C.RESET}")
            print(f"           {C.GREY}{entry['detail']}{C.RESET}")
        else:
            print(f"  {color}{icon} {label}  {C.BOLD}{entry['file']}{C.RESET}")
            print(f"           {C.GREY}{entry['detail']}{C.RESET}")

    print(f"\n{C.GREY}{'─'*60}{C.RESET}")
    print(f"  {C.GREEN}✔  Copied          : {stats['copied']}{C.RESET}")
    print(f"  {C.GREY}↷  Skipped         : {stats['skipped']}{C.RESET}")
    print(f"  {C.YELLOW}⚠  Conflicts (skip): {stats['conflict']}{C.RESET}")
    print(f"  {C.GREY}⊘  Not found       : {stats['not_found']}{C.RESET}")
    print(f"\n  {C.BOLD}Total processed   : {len(sources)}{C.RESET}")
    print(f"  {C.BOLD}Finished          : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{C.RESET}\n")

    conflicts = [e for e in log if e["status"] == "CONFLICT"]
    if conflicts:
        print(f"{C.YELLOW}{C.BOLD}{'─'*60}")
        print(f"  ⚠  UNRESOLVED CONFLICTS — FILES NOT COPIED ({len(conflicts)})")
        print(f"{'─'*60}{C.RESET}")
        for e in conflicts:
            print(f"  {C.YELLOW}{C.BOLD}• {e['file']}{C.RESET}")
            print(f"    {C.CYAN}Source : {src_root / e['file']}{C.RESET}")
            for t in e.get("targets", []):
                print(f"    {C.GREY}Target : {t}{C.RESET}")
            print()
        print(f"{C.YELLOW}{'─'*60}{C.RESET}\n")

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


def _do_copy_manual(src: Path, manual_dst: Path, rel: Path, log: list, stats: dict, note: str):
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
        copy_file(src, manual_dst, rel, log, stats, note=note)


# ── Entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":

    # ── --profiles flag ───────────────────────────────────────────────────
    if len(sys.argv) == 2 and sys.argv[1] == "--profiles":
        list_profiles()

    # ── Validate arg count ────────────────────────────────────────────────
    if len(sys.argv) not in (3, 4):
        print(f"\n{C.YELLOW}Usage:")
        print(f"  python3 source_copier.py <source> <target> [\"ignored1,ignored2\"]")
        print(f"  python3 source_copier.py <source> p:<profile>")
        print(f"  python3 source_copier.py --profiles")
        print(f"\n  source / target → folder path or .zip file")
        print(f"  p:<profile>     → load target + ignored from profiles.ini")
        print(f"  ignored         → comma-separated names/patterns (wildcards OK){C.RESET}\n")
        sys.exit(1)

    # ── Detect profile token in argv[2] or argv[3] ────────────────────────
    src_arg      = sys.argv[1]
    profile_name = None
    dst_arg      = None
    ignored: set[str] = set()

    raw2 = sys.argv[2]
    raw3 = sys.argv[3] if len(sys.argv) == 4 else None

    if is_profile_token(raw2):
        # sc <source> p:am
        token        = normalize_profile_token(raw2)
        profile_name = token[2:]
        dst_arg, ignored = resolve_profile(token)
        # 4th arg is silently ignored when profile already provides ignored
        if raw3:
            print(
                f"{C.YELLOW}⚠  Profile '{profile_name}' already sets ignored patterns — "
                f"4th argument ignored.{C.RESET}"
            )
    elif raw3 and is_profile_token(raw3):
        # sc <source> <target> p:am  (unusual but supported)
        token        = normalize_profile_token(raw3)
        profile_name = token[2:]
        _, ignored   = resolve_profile(token)   # use explicit target, profile's ignored
        dst_arg      = raw2
    else:
        # Classic mode: no profile token
        dst_arg = raw2
        if raw3:
            ignored = {name.strip() for name in raw3.split(",") if name.strip()}

    # ── Pre-flight confirmation ───────────────────────────────────────────
    ignored_display = ", ".join(sorted(ignored)) if ignored else "(none)"
    profile_display = f"  {C.BOLD}Profile :{C.RESET} {C.CYAN}[{profile_name}]{C.RESET}\n" if profile_name else ""

    print(f"\n  {C.BOLD}Source  :{C.RESET} {C.BLUE}{src_arg}{C.RESET}")
    print(f"  {C.BOLD}Target  :{C.RESET} {C.BLUE}{dst_arg}{C.RESET}")
    print(profile_display, end="")
    print(f"  {C.BOLD}Ignored :{C.RESET} {C.YELLOW}{ignored_display}{C.RESET}")
    print(f"\n  {C.BOLD}Ready to start? {C.GREY}[Y/Enter = Start, n/N = Stop]:{C.RESET} ", end="", flush=True)

    try:
        answer = input().strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = "n"

    if answer in ("n", "no"):
        print(f"\n  {C.GREY}Aborted.{C.RESET}\n")
        sys.exit(0)

    run(src_arg, dst_arg, ignored, profile_name=profile_name)
