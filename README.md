# airtable-export

[![PyPI](https://img.shields.io/pypi/v/airtable-export.svg)](https://pypi.org/project/airtable-export/)
[![Changelog](https://img.shields.io/github/v/release/simonw/airtable-export?include_prereleases&label=changelog)](https://github.com/simonw/airtable-export/releases)
[![Tests](https://github.com/simonw/airtable-export/workflows/Test/badge.svg)](https://github.com/simonw/airtable-export/actions?query=workflow%3ATest)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://github.com/simonw/airtable-export/blob/master/LICENSE)

Export Airtable data to files on disk

## Installation

Install this tool using `pip`:

    $ pip install airtable-export

## Usage

You will need the following information:

- One or more Airtable base IDs, each a string starting with `app...`
- Your Airtable personal access token, a string starting with `pat...`
- To export only some tables from a single base, the names of those tables

Export a base with:

    airtable-export --bases base_id --formats yaml --key=key

`--bases` and `--formats` are required. `--bases` takes one or more base IDs, separated by commas. `--formats` takes a comma-separated list of `yaml`, `json`, `ndjson`, `xlsx`, and `sqlite`. Each base is written to its own folder in the current directory, named with that base ID. For example, base `appAAA` produces `appAAA/table1.yml` and `appAAA/table2.yml`.

Several bases are exported one after another. `--tables` cannot be combined with more than one base, so every table in each base is exported:

    airtable-export --bases appAAA,appBBB --formats yaml --key=key

    [1/2] base appAAA
    Exporting 2 tables
    [1/2] table1 ...
    [2/2] base appBBB
    Exporting 1 table

To export only specified tables from one base, pass a comma-separated list to `--tables`:

    airtable-export --bases base_id --formats yaml --tables table1,table2 --key=key

Rather than passing the API key using the `--key` option you can set it as an environment variable called `AIRTABLE_KEY`. If you omit `--key`, the tool reads `AIRTABLE_PAT` from a `.env` file in the current directory. Copy `.env.example` to `.env` and paste your token there.

While it runs, progress is printed to stderr. Paths are relative to the current directory. The record line appears as soon as that table's files are written:

    Exporting 2 tables
    [1/2] table1 ...
    [1/2] table1 - 18 records -> base_id/table1.yml
    [2/2] table2 ...
    [2/2] table2 - 5 records -> base_id/table2.yml

With `--attachments`, downloads are listed after that record line:

    [1/2] table1 - 18 records -> base_id/table1.yml
    [1/2] table1 - downloading 3 attachments
      [1/3] photo.jpg
      [2/3] notes.pdf
      [3/3] scan.png
    [1/2] table1 - 3 attachments

A failed download is printed under its filename. The last line then includes the failure count, for example `1 attachment, 1 failure`.

With `sqlite` included in `--formats`, the database is `base_id/base_id.db`. A line is printed before it is written, and that path is included on the record line. After attachments are saved, those records are written again:

    [1/2] table1 - writing to base_id/base_id.db
    [1/2] table1 - 18 records -> base_id/table1.yml, base_id/base_id.db
    [1/2] table1 - writing 18 records to base_id/base_id.db

With `xlsx` included in `--formats`, the workbook is written after every table and reported on its own line:

    base_id/base_id.xlsx - 2 tables, 23 records

## Export options

`--formats` chooses what gets written. This command writes JSON, newline delimited JSON, and YAML for each table:

    airtable-export --bases base_id --formats json,ndjson,yaml --key=key

You can export the whole base as one Excel workbook by including `xlsx`:

    airtable-export --bases base_id --formats xlsx --key=key

This writes `base_id/base_id.xlsx`. Each table is a sheet, named from the table and shortened to Excel's 31-character limit. `airtable_id` is the first column and `airtable_createdTime` is the last. Lists of plain values, such as linked records or multiple select options, are joined with commas. Nested values, including attachments, are stored as JSON text. Cyrillic and other non-ASCII text is written as characters.

If you import all tables, or if you add the `--schema` option, a JSON schema for the base will be written to `base_id/_schema.json`.

### Attachments

Airtable stores images in attachment fields. The download URLs for those files expire after about two hours, so pass `--attachments` to save the original files next to each table export:

    airtable-export --bases base_id --formats yaml --key=key --attachments

For a table called `People` this writes `base_id/People.yml` and a folder `base_id/People/`. Each file is named `{attachment id}-original-{filename}`, for example `base_id/People/attwPzAABrX7mUpdl-original-photo.jpg`. Characters that are not allowed in Windows filenames are replaced with `_`.

The exported YAML, JSON, NDJSON, Excel, and SQLite keep the Airtable `url` and add `_saved` with that path relative to the output directory, using forward slashes:

    _saved: People/attwPzAABrX7mUpdl-original-photo.jpg

Files that are already on disk and match the attachment's byte size are not downloaded again. Thumbnail URLs are left unchanged.

Attachment downloads do not send your API key. When `--http-read-timeout` is omitted, those downloads use a 120 second read timeout. If a download fails, the table is still written, `_saved` is omitted for that file, and the command exits with an error.

`sqlite` in `--formats` writes `base_id/base_id.db`. Attachment files and `_saved` paths still use that base ID folder.

### SQLite database export

Include `sqlite` in `--formats` to write `base_id/base_id.db`. The file name is the base ID, and it cannot be set on the command line:

    airtable-export --bases base_id --formats sqlite --key=key

`sqlite` can be combined with the other formats, for example `--formats yaml,sqlite`.

The SQLite database will have a table created for each table you export. Those tables will have a primary key column called `airtable_id`.

If you run this command against an existing SQLite database records with matching primary keys will be over-written by new records from the export.

## Request options

By default the tool uses [python-httpx](https://www.python-httpx.org)'s default configurations.

You can override the `user-agent` using the `--useragent` option:

    airtable-export --bases base_id --formats yaml --tables table1,table2 --key=key --useragent "Airtable Export Robot"

You can override the [timeout during a network read operation](https://www.python-httpx.org/advanced/#fine-tuning-the-configuration) using the `--http-read-timeout` option. If not set, this defaults to 5s.

    airtable-export --bases base_id --formats yaml --tables table1,table2 --key=key --http-read-timeout 60

## Running this using GitHub Actions

[GitHub Actions](https://github.com/features/actions) is GitHub's workflow automation product. You can use it to run `airtable-export` in order to back up your Airtable data to a GitHub repository. Doing this gives you a visible commit history of changes you make to your Airtable data - like [this one](https://github.com/natbat/rockybeaches/commits/main/airtable).

To run this for your own Airtable database you'll first need to add the following secrets to your GitHub repository:

<dl>
  <dt>AIRTABLE_BASE_ID</dt>
  <dd>One or more base IDs, comma-separated, each beginning <samp>app...</samp></dd>
  <dt>AIRTABLE_KEY</dt>
  <dd>Your Airtable API key</dd>
  <dt>AIRTABLE_TABLES</dt>
  <dd>A comma-separated list of tables to backup from a single base, for example <samp>My table,OtherTable</samp>. Leave it empty to export every table. Leave it empty when <samp>AIRTABLE_BASE_ID</samp> lists more than one base.</dd>
</dl>

Once you have set those secrets, add the following as a file called `.github/workflows/backup-airtable.yml`:
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
        pip install airtable-export
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
This will run once a day (at 32 minutes past midnight UTC) and will also run if you manually click the "Run workflow" button, see [GitHub Actions: Manual triggers with workflow_dispatch](https://github.blog/changelog/2020-07-06-github-actions-manual-triggers-with-workflow_dispatch/).

## Development

To contribute to this tool, first checkout the code. Then create a new virtual environment:

    cd airtable-export
    python -mvenv venv
    source venv/bin/activate

Or if you are using `pipenv`:

    pipenv shell

Now install the dependencies and tests:

    pip install -e '.[test]'

To run the tests:

    pytest
