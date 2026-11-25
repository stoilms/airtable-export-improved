# AGENTS.md

The project name is airtable-export-improved. The console script is `airtable-export`. Leave the package name, author, and version in `setup.py` unchanged until a change is requested. Leave the PyPI publish workflow unchanged until a publish is requested.

Flag behavior for humans is in `README.md`. A code change that alters a flag updates that file in the same change.

## After a merge

When a pull request is merged and its branch is deleted:

1. Check out `main` and fast-forward it from `origin`.
2. Delete the local branch that was merged.
3. Start the next change on a new branch from that `main`.

Done when `git status` shows the new branch and a clean tree before the edit.

## Make a change

1. Edit `airtable_export/cli.py` for behavior. Keep the existing helpers: `filesystem_name` for on-disk names, `relative_path` for progress lines, `split_csv` for `--bases`, `--formats`, and `--tables`.
2. Update `tests/test_airtable_export.py`. Invoke the CLI through `command()` and `invoke()`, which chdir into `tmp_path`. Assert file contents with `exported()` and progress text with `shown()`.
3. Update the matching flag section in `README.md`.
4. Run the suite with the repo virtual environment: `.venv\Scripts\python.exe -m pytest` on Windows.

Done when `pytest` passes and every command shown in the README is one the code accepts.

The shell is PowerShell. Chain commands with `;`, not `&&`. Pass a commit message with a here-string, and a pull request body with `gh pr create --body-file`.

## Open a pull request

Do this only when asked.

1. Commit the intended files. `.env`, `export/`, `app*/`, and a local `database.db` stay untracked.
2. Push the branch with `git push -u origin HEAD`.
3. Open the pull request with `gh pr create --repo stoilms/airtable-export-improved --base main`. Without `--repo`, `gh` targets `upstream`, which is simonw/airtable-export.

The body has three parts: a short control-flow sketch of the change, evidence with the `pytest` result, and whether reverting the commit is enough to undo it.

## Invariants

- Each base is a folder in the current directory, named with `filesystem_name(base_id)`. Progress lines are relative to that directory.
- A new file or folder name goes through `filesystem_name`. On Windows a `:` in a name is an NTFS alternate data stream and leaves a 0-byte file beside the real data.
- YAML is dumped with `allow_unicode=True`. JSON, NDJSON, and `_schema.json` use `ensure_ascii=False`, so Cyrillic is written as characters.
- A `--key` on the command line wins. Otherwise read `AIRTABLE_PAT` from `.env` in the working directory, then the `AIRTABLE_KEY` environment variable. Keep that value out of chat, commits, and logs.
- `--tables` with more than one base raises `UsageError` before any file is created.
- The record-count line is printed when the table files are first written, before attachment downloads. After a download, rewrite those files and the SQLite rows so `_saved` is included. `_saved` uses forward slashes and is relative to the base folder.
- `sqlite` writes `{base}/{base}.db`. `xlsx` writes `{base}/{base}.xlsx`. Neither path is a command-line argument. A line is printed before each SQLite write.
- GitHub Actions tests Python 3.11 through 3.15. Keep the matrix on versions that Ubuntu image can install.
