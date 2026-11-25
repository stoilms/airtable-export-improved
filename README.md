# airtable-export-improved

[![Changelog](https://img.shields.io/github/v/release/stoilms/airtable-export-improved?include_prereleases&label=changelog)](https://github.com/stoilms/airtable-export-improved/releases)
[![Tests](https://github.com/stoilms/airtable-export-improved/workflows/Test/badge.svg)](https://github.com/stoilms/airtable-export-improved/actions?query=workflow%3ATest)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://github.com/stoilms/airtable-export-improved/blob/main/LICENSE)

Export Airtable data to files on disk.

## Installation

Clone the repository and install it into a virtual environment:

    git clone https://github.com/stoilms/airtable-export-improved.git
    cd airtable-export-improved
    python -m venv .venv

On Windows:

    .venv\Scripts\activate
    pip install -e .

On macOS and Linux:

    source .venv/bin/activate
    pip install -e .

Copy `.env.example` to `.env` and paste your Airtable personal access token.

## Usage

    airtable-export --bases appXXXXXXXXXXXXXX --formats yaml

This writes one YAML file per table into a folder named with the base ID, for example `appXXXXXXXXXXXXXX/People.yml`. The token is read from `.env`.

### `--bases`

Required. One or more Airtable base IDs, separated by commas. Each ID starts with `app`. Each base is written to its own folder in the current directory.

    airtable-export --bases appAAA,appBBB --formats yaml

`--tables` cannot be used when more than one base is listed. Every table in each base is exported. A line names each base before its tables:

    [1/2] base appAAA
    [2/2] base appBBB

### `--formats`

Required. A comma-separated list of `yaml`, `json`, `ndjson`, `xlsx`, and `sqlite`.

    airtable-export --bases appXXX --formats yaml,json,xlsx,sqlite

- `yaml` writes `{base}/{table}.yml`
- `json` writes `{base}/{table}.json`
- `ndjson` writes `{base}/{table}.ndjson`, one JSON object per line
- `xlsx` writes one workbook, `{base}/{base}.xlsx`, with one sheet per table. Sheet names are shortened to Excel's 31-character limit. `airtable_id` is the first column and `airtable_createdTime` is the last. Lists of plain values are joined with commas. Nested values, including attachments, are stored as JSON text.
- `sqlite` writes `{base}/{base}.db`. Each Airtable table becomes a SQLite table with primary key `airtable_id`. A later export overwrites rows that have the same primary key. The database file name cannot be changed.

### `--tables`

Optional. Comma-separated table names to export from a single base. Omit it to export every table. It cannot be combined with more than one base.

    airtable-export --bases appXXX --formats yaml --tables People,Tasks

### `--key`

Optional. Airtable personal access token (`pat...`). If you omit it, the tool uses the `AIRTABLE_KEY` environment variable, then `AIRTABLE_PAT` from a `.env` file in the current directory. A `--key` on the command line wins over both.

    airtable-export --bases appXXX --formats yaml --key pat...

### `--attachments`

Download original image and attachment files into a folder beside each table. Airtable download URLs expire after about two hours.

    airtable-export --bases appXXX --formats yaml --attachments

For a table called `People` this writes `appXXX/People.yml` and `appXXX/People/`. Each file is named `{attachment id}-original-{filename}`. Characters that are not allowed in Windows filenames are replaced with `_`.

The export keeps the Airtable `url` and adds `_saved` with the path relative to the base folder, using forward slashes:

    _saved: People/attwPzAABrX7mUpdl-original-photo.jpg

Files already on disk with the same byte size are not downloaded again. Thumbnail URLs are left unchanged. Downloads do not send your API key. When `--http-read-timeout` is omitted, downloads use a 120 second read timeout. If a download fails, the table is still written, `_saved` is omitted for that file, and the command exits with an error after the rest of the export.

The record line is printed before downloads start. Each file is then listed on its own line.

### `--schema`

Write the Airtable schema to `{base}/_schema.json`. This file is also written whenever every table is exported, which is what happens when `--tables` is omitted.

### `--useragent`

User-Agent header sent with Airtable API requests.

    airtable-export --bases appXXX --formats yaml --useragent "Airtable Export Robot"

### `--http-read-timeout`

Timeout, in seconds, for reading from the Airtable API. The default is 5 seconds. Attachment downloads use 120 seconds when this option is omitted.

    airtable-export --bases appXXX --formats yaml --http-read-timeout 60

### `-q`, `--quiet`

Print nothing while the export runs. Files are still written. Download errors are still printed. Without this flag, progress goes to stderr with paths relative to the current directory. The record count is printed when the table files are written, before attachment downloads and before the SQLite file is updated.

    airtable-export --bases appXXX --formats yaml --quiet

## Known issues / Todos

- With `--http-read-timeout`, record pagination opens an HTTP client and does not close it.
- Listing tables does not check the HTTP status. A rejected schema request fails later, when the response has no `tables` key.
- A SQLite export whose record count is a multiple of 100 sends one extra empty insert after the last full batch.
- Airtable allows about 5 requests per second per base. The tool waits 0.2 seconds only between pages of the same table. It does not wait between tables, and it does not retry a `429` response.

## Running this using GitHub Actions

[GitHub Actions](https://github.com/features/actions) can run `airtable-export` on a schedule and commit the files to a repository. That gives you a history of changes to your Airtable data, like [this one](https://github.com/natbat/rockybeaches/commits/main/airtable).

Add these secrets to the repository that will store the backup:

<dl>
  <dt>AIRTABLE_BASE_ID</dt>
  <dd>One or more base IDs, comma-separated, each beginning <samp>app...</samp></dd>
  <dt>AIRTABLE_KEY</dt>
  <dd>Your Airtable personal access token</dd>
  <dt>AIRTABLE_TABLES</dt>
  <dd>Optional. A comma-separated list of tables from a single base, for example <samp>My table,OtherTable</samp>. Leave it empty to export every table. Leave it empty when <samp>AIRTABLE_BASE_ID</samp> lists more than one base.</dd>
</dl>

Add this file as `.github/workflows/backup-airtable.yml`:

```yaml
name: Backup Airtable

on:
  workflow_dispatch:
  schedule:
  - cron: '32 0 * * *'

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
    - name: Check out repo
      uses: actions/checkout@v7
    - name: Set up Python
      uses: actions/setup-python@v7
      with:
        python-version: "3.13"
    - name: Install airtable-export
      run: |
        pip install git+https://github.com/stoilms/airtable-export-improved.git
    - name: Backup Airtable
      env:
        AIRTABLE_BASE_ID: ${{ secrets.AIRTABLE_BASE_ID }}
        AIRTABLE_KEY: ${{ secrets.AIRTABLE_KEY }}
        AIRTABLE_TABLES: ${{ secrets.AIRTABLE_TABLES }}
      run: |-
        if [ -n "$AIRTABLE_TABLES" ]; then
          airtable-export --bases "$AIRTABLE_BASE_ID" --formats yaml --tables "$AIRTABLE_TABLES"
        else
          airtable-export --bases "$AIRTABLE_BASE_ID" --formats yaml
        fi
    - name: Commit and push if it changed
      run: |-
        git config user.name "Automated"
        git config user.email "actions@users.noreply.github.com"
        git add -A
        timestamp=$(date -u)
        git commit -m "Latest data: ${timestamp}" || exit 0
        git push
```

This runs once a day, at 32 minutes past midnight UTC, and also when you click "Run workflow". See [GitHub Actions: Manual triggers with workflow_dispatch](https://github.blog/changelog/2020-07-06-github-actions-manual-triggers-with-workflow_dispatch/).

The repository that stores the backup must be able to install from `stoilms/airtable-export-improved`. If that repository is private, the workflow needs a token that can read it.

## Development

Clone the repository and install the package with its test dependencies:

    git clone https://github.com/stoilms/airtable-export-improved.git
    cd airtable-export-improved
    python -m venv .venv

On Windows:

    .venv\Scripts\activate

On macOS and Linux:

    source .venv/bin/activate

Then:

    pip install -e ".[test]"
    pytest
