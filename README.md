# Source File Copier

A command-line tool that takes files from a **source** folder (or zip) and copies them into a **target** folder (or zip) by matching filenames recursively.

---

## Usage

```bash
python3 source_file_copier.py <input1> <input2> ["ignored1,ignored2"]
```

| Argument | Required | Description |
|----------|----------|-------------|
| `input1` | ✅ | Source — folder path or `.zip` file |
| `input2` | ✅ | Target — folder path or `.zip` file |
| `ignored` | ❌ | Comma-separated folder names to exclude from target search |

---

## Examples

```bash
# Both folders
python3 source_file_copier.py ./src ./project

# Source is a zip
python3 source_file_copier.py ~/Downloads/files.zip ./project

# Both zips, with ignored folders
python3 source_file_copier.py source.zip target.zip "build,dist,.git"

# Exclude virtual environment
python3 source_file_copier.py ~/Downloads/files.zip ../my-project/ ".venv"
```

---

## How It Works

For each file found in the source, the tool searches the target tree by filename:

| Matches found | Action |
|---------------|--------|
| **0** | Prompts for a manual destination path. Provide a path to copy there, or press Enter to skip. |
| **1** | File is copied over the matched target file. |
| **2+** | Conflict warning — no action taken. |

---

## Zip Support

If a `.zip` is provided as either argument, the tool automatically:
1. Extracts it into a temporary folder next to the zip file (`_sfc_tmp_<name>_XXXX/`)
2. Runs the copy operation
3. Deletes the temporary folder on exit

---

## Output

- Colored terminal output with per-file status
- A `copy_report.log` file saved in the current working directory

### Status indicators

| Icon | Meaning |
|------|---------|
| ✔ | Copied successfully |
| ⚠ | Conflict — multiple matches, skipped |
| ⊘ | Not found in target |
| ✖ | Error |

---

## Requirements

Python 3.10+ — no third-party dependencies.
