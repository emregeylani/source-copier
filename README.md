# Source File Copier

A Python CLI utility that searches for source files (from a folder or `.zip`) recursively inside a target directory (or `.zip`) and copies them over — with smart conflict resolution, wildcard ignore patterns, and interactive prompts.

---

## Requirements

- Python 3.10+
- No external dependencies (stdlib only)

---

## Usage

```bash
python3 source_copier.py <source> <target> ["pattern1,pattern2,..."]
```

| Argument | Required | Description |
|---|---|---|
| `source` | ✔ | Source folder or `.zip` file |
| `target` | ✔ | Target folder or `.zip` file |
| `ignored` | ✗ | Comma-separated names/patterns to exclude from target search |

### Examples

```bash
# Basic
python3 source_copier.py ~/dev/myapp /var/www/myapp

# With ignored patterns
python3 source_copier.py ~/dev/myapp /var/www/myapp "build,dist,*env*,__pycache__,.git"

# Using zip files
python3 source_copier.py myapp_patch.zip /var/www/myapp

# Both as zips
python3 source_copier.py source.zip target.zip "*env*,build"
```

---

## Zsh Alias (recommended)

Add to your `~/.zshrc`:

```zsh
sfc() {
    python3 ~/git/source-copier/source_copier.py "$1" "$2" "${3:-}"
}
```

Reload:

```bash
source ~/.zshrc
```

Then simply call:

```bash
sfc ~/dev/myapp /var/www/myapp "*env*,build,dist"
```

---

## Behavior

### Pre-flight confirmation

Before doing anything, the script displays a summary and asks for confirmation:

```
  Source  : /path/to/source
  Target  : /path/to/target
  Ignored : *env*, build, dist

  Ready to start? [Y/Enter = Start, n/N = Stop]:
```

### Per-file logic

| Matches found | Action |
|---|---|
| **0** | Not found in target — user is prompted for a manual destination path |
| **1** | File is copied directly over the target match |
| **2+** | Folder-structure resolution attempted (see below) |

### Multiple matches — folder structure resolution

When the same filename exists in multiple locations in the target, the script tries to resolve the conflict automatically by comparing parent folder names.

**Example:**

```
Source file : db/__init__.py

Target matches:
  /project/app/db/__init__.py     ← folder "db" matches ✔  (selected)
  /project/utils/__init__.py      ← folder "utils" doesn't match  (skipped)
```

If exactly one candidate has the best folder overlap → it is copied automatically.  
If there is a tie or no folder overlap → a conflict warning is shown and no action is taken.

### Not found — manual path prompt

When no match is found, the user is prompted for a destination path:

```
  Enter destination path (Enter = /target/root  |  relative path joined to target root):
```

| Input | Result |
|---|---|
| *(empty, just Enter)* | File is placed directly in the target root |
| `some/sub/dir` | Joined to target root → `target/some/sub/dir/filename` |
| `/absolute/path` | Used as-is |

If the given destination is an existing directory, the filename is appended automatically.

### Ignored patterns

The third argument accepts comma-separated names **and wildcard patterns**:

```bash
"build,dist,.git,__pycache__,*env*,*.egg-info"
```

Any path component in the target tree that matches one of these patterns is excluded from the search.

| Pattern | Matches |
|---|---|
| `build` | exactly `build` |
| `*env*` | `venv`, `.env`, `myenv`, `test_env`, … |
| `.git` | exactly `.git` |
| `*.egg-info` | `myapp.egg-info`, `pkg.egg-info`, … |

### Zip support

If a `.zip` file is provided as source or target, it is automatically extracted to a temporary folder next to the zip. The temp folder is deleted on exit.

At the end of the run, the script offers to delete the original zip file(s).

---

## Output

### During processing

```
► db/__init__.py  (2.1 KB)
  🔍 2 matches found — resolved by folder structure:
     • /project/app/db/__init__.py  ✔ (selected)
     • /project/utils/__init__.py   (skipped)
  ✔  Copied  →  /project/app/db/__init__.py  (resolved by folder match)
     Old size: 1.8 KB  |  New size: 2.1 KB
```

### Summary report

```
────────────────────────────────────────────────────────────
  SUMMARY REPORT  (4 files)

  ✔ COPIED      db/__init__.py
                → /project/app/db/__init__.py  [old: 1.8 KB, new: 2.1 KB]
  ⚠ CONFLICT    utils.py
                2 matches: /project/a/utils.py | /project/b/utils.py
  ⊘ NOT FOUND   config.py
                Manual path invalid: /bad/path/config.py

────────────────────────────────────────────────────────────
  ✔  Copied          : 2
  ⚠  Conflicts (skip): 1
  ⊘  Not found       : 1

  Total processed    : 4
  Finished           : 2025-01-15 14:32:07
```

---

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Success (or aborted by user) |
| `1` | Invalid arguments or unresolvable input path |
