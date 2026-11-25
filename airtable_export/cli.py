import click
import httpx
from httpx import HTTPError
import json as json_
import os
import pathlib
import re
from urllib.parse import quote, urlencode
import sqlite_utils
import time
import yaml as yaml_
from openpyxl import Workbook

# Attachment files can be several megabytes, so use a longer read timeout
# than httpx's 5 second default when --http-read-timeout is not set.
DEFAULT_ATTACHMENT_READ_TIMEOUT = 120
VALID_FORMATS = ("yaml", "json", "ndjson", "xlsx", "sqlite")
INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
ILLEGAL_XLSX_CHARS = re.compile(r"[\000-\010\013\014\016-\037]")
INVALID_SHEET_CHARS = re.compile(r"[\[\]:\\/?*]")


def split_csv(value):
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


@click.command()
@click.version_option()
@click.option(
    "--bases",
    required=True,
    help="Comma-separated Airtable base IDs (app...)",
)
@click.option(
    "--formats",
    required=True,
    help="Comma-separated formats: yaml, json, ndjson, xlsx, sqlite",
)
@click.option(
    "--tables",
    "table_names",
    help="Comma-separated table names for a single base. Omit to export every table.",
)
@click.option(
    "--key",
    envvar="AIRTABLE_KEY",
    help="Airtable personal access token. Defaults to AIRTABLE_PAT in .env.",
)
@click.option(
    "--http-read-timeout",
    help="Timeout (in seconds) for network read operations",
    type=int,
)
@click.option("--useragent", help="User agent to use for requests")
@click.option("-v", "--verbose", is_flag=True, help="Verbose output")
@click.option(
    "--schema",
    is_flag=True,
    help="Save Airtable schema to {base id}/_schema.json",
)
@click.option(
    "--attachments",
    is_flag=True,
    help="Download attachment and image files into a subfolder per table",
)
@click.pass_context
def cli(
    ctx,
    bases,
    formats,
    table_names,
    key,
    http_read_timeout,
    useragent,
    verbose,
    schema,
    attachments,
):
    "Export Airtable bases into folders named with each base ID"
    if ctx.get_parameter_source("key") != click.core.ParameterSource.COMMANDLINE:
        dotenv_pat = read_dotenv_value(pathlib.Path.cwd() / ".env", "AIRTABLE_PAT")
        if dotenv_pat:
            key = dotenv_pat
    if not key:
        raise click.UsageError(
            "Missing Airtable token. Pass --key or set AIRTABLE_PAT in .env."
        )
    chosen = split_csv(formats)
    unknown = [name for name in chosen if name not in VALID_FORMATS]
    if unknown or not chosen:
        raise click.UsageError(
            "--formats must be a comma-separated list of: {}.".format(
                ", ".join(VALID_FORMATS)
            )
        )
    json = "json" in chosen
    ndjson = "ndjson" in chosen
    yaml = "yaml" in chosen
    xlsx = "xlsx" in chosen
    base_ids = split_csv(bases)
    if not base_ids:
        raise click.UsageError("--bases requires one or more Airtable base IDs.")
    requested_tables = split_csv(table_names)
    if len(base_ids) > 1 and requested_tables:
        raise click.UsageError(
            "--tables cannot be used with more than one base. "
            "Omit --tables to export every table in each base."
        )
    user_agent = useragent
    failed_downloads = 0
    several = len(base_ids) > 1
    for number, base_id in enumerate(base_ids, start=1):
        if several:
            click.echo(
                "[{}/{}] base {}".format(number, len(base_ids), base_id),
                err=True,
            )
        failed_downloads += export_base(
            base_id,
            requested_tables,
            key,
            http_read_timeout,
            user_agent,
            schema,
            attachments,
            json,
            ndjson,
            yaml,
            xlsx,
            "sqlite" in chosen,
        )
    if failed_downloads:
        raise click.ClickException(
            "Failed to download {} attachment{}".format(
                failed_downloads, "" if failed_downloads == 1 else "s"
            )
        )


def export_base(
    base_id,
    requested_tables,
    key,
    http_read_timeout,
    user_agent,
    schema,
    attachments,
    json,
    ndjson,
    yaml,
    xlsx,
    use_sqlite,
):
    "Export one base into a folder named with its base ID. Returns failed downloads."
    tables = list(requested_tables)
    output_name = filesystem_name(base_id)
    output = pathlib.Path.cwd() / output_name
    output.mkdir(parents=True, exist_ok=True)
    sqlite = output / "{}.db".format(output_name) if use_sqlite else None
    sqlite_state = {"announced": False}

    def write_batch(table, batch):
        if not sqlite:
            return
        if batch and not sqlite_state["announced"]:
            click.echo(
                "[{}/{}] {} - writing to {}".format(
                    index, total, table, relative_path(sqlite)
                ),
                err=True,
            )
            sqlite_state["announced"] = True
        db[table].insert_all(batch, pk="airtable_id", replace=True, alter=True)

    if sqlite:
        db = sqlite_utils.Database(sqlite)
    if not tables or schema:
        # Fetch all tables
        schema_data = list_tables(base_id, key, user_agent=user_agent)
        dumped_schema = json_.dumps(
            schema_data, sort_keys=True, indent=4, ensure_ascii=False
        )
        (output / "_schema.json").write_text(dumped_schema, "utf-8")
        if not tables:
            tables = [table["name"] for table in schema_data["tables"]]

    failed_downloads = 0
    xlsx_tables = []
    total = len(tables)
    if total:
        click.echo("Exporting {}".format(count_label(total, "table")), err=True)
    for index, table in enumerate(tables, start=1):
        sqlite_state["announced"] = False
        click.echo("[{}/{}] {} ...".format(index, total, table), err=True)
        records = []
        try:
            db_batch = []
            for record in all_records(
                base_id, table, key, http_read_timeout, user_agent=user_agent
            ):
                r = {
                    **{"airtable_id": record["id"]},
                    **record["fields"],
                    **{"airtable_createdTime": record["createdTime"]},
                }
                records.append(r)
                db_batch.append(r)
                if len(db_batch) == 100:
                    write_batch(table, db_batch)
                    db_batch = []
        except HTTPError as exc:
            raise click.ClickException(exc)
        write_batch(table, db_batch)
        filenames = write_table_files(output, table, records, json, ndjson, yaml)
        destinations = [relative_path(filename) for filename in filenames]
        if sqlite:
            destinations.append(relative_path(sqlite))
        line = "[{}/{}] {} - {}".format(
            index, total, table, count_label(len(records), "record")
        )
        if destinations:
            line += " -> {}".format(", ".join(destinations))
        click.echo(line, err=True)
        if attachments:
            pending = list(iter_attachments(records))
            if pending:
                click.echo(
                    "[{}/{}] {} - downloading {}".format(
                        index,
                        total,
                        table,
                        count_label(len(pending), "attachment"),
                    ),
                    err=True,
                )

                def report_attachment(number, attachment, pending_count=len(pending)):
                    click.echo(
                        "  [{}/{}] {}".format(
                            number,
                            pending_count,
                            attachment.get("filename") or attachment["id"],
                        ),
                        err=True,
                    )

                saved, failed = save_table_attachments(
                    output,
                    table,
                    records,
                    http_read_timeout,
                    user_agent=user_agent,
                    on_file=report_attachment,
                )
                failed_downloads += failed
                if saved:
                    write_table_files(output, table, records, json, ndjson, yaml)
                    if sqlite:
                        click.echo(
                            "[{}/{}] {} - writing {} to {}".format(
                                index,
                                total,
                                table,
                                count_label(len(records), "record"),
                                relative_path(sqlite),
                            ),
                            err=True,
                        )
                    write_batch(table, records)
                summary = "[{}/{}] {} - {}".format(
                    index, total, table, count_label(saved, "attachment")
                )
                if failed:
                    summary += ", {}".format(count_label(failed, "failure"))
                click.echo(summary, err=True)
        if xlsx:
            xlsx_tables.append((table, records))
    if xlsx and xlsx_tables:
        workbook_path = output / "{}.xlsx".format(output_name)
        write_base_xlsx(workbook_path, xlsx_tables)
        record_count = sum(len(rows) for _, rows in xlsx_tables)
        click.echo(
            "{} - {}, {}".format(
                relative_path(workbook_path),
                count_label(len(xlsx_tables), "table"),
                count_label(record_count, "record"),
            ),
            err=True,
        )
    return failed_downloads


def count_label(count, singular):
    return "{} {}{}".format(count, singular, "" if count == 1 else "s")


def relative_path(path):
    return str(pathlib.Path(path).relative_to(pathlib.Path.cwd()))


def read_dotenv_value(path, name):
    "Return one value from a .env file, or None when the file or name is absent."
    if not path.is_file():
        return None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() != name:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        return value or None
    return None


def list_tables(base_id, api_key, user_agent=None):
    url = f"https://api.airtable.com/v0/meta/bases/{base_id}/tables"
    headers = {"Authorization": "Bearer {}".format(api_key)}
    if user_agent is not None:
        headers["user-agent"] = user_agent
    return httpx.get(url, headers=headers).json()


def all_records(base_id, table, api_key, http_read_timeout, sleep=0.2, user_agent=None):
    headers = {"Authorization": "Bearer {}".format(api_key)}
    if user_agent is not None:
        headers["user-agent"] = user_agent

    if http_read_timeout:
        timeout = httpx.Timeout(5, read=http_read_timeout)
        client = httpx.Client(timeout=timeout)
    else:
        client = httpx

    first = True
    offset = None
    while first or offset:
        first = False
        url = "https://api.airtable.com/v0/{}/{}".format(base_id, quote(table, safe=""))
        if offset:
            url += "?" + urlencode({"offset": offset})
        response = client.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        offset = data.get("offset")
        yield from data["records"]
        if offset and sleep:
            time.sleep(sleep)


def filesystem_name(name):
    "Make a table or file name safe on Windows, where ':' opens an alternate stream."
    cleaned = INVALID_FILENAME_CHARS.sub("_", name).strip(" .")
    return cleaned or "_"


def excel_cell(value):
    if isinstance(value, str):
        return ILLEGAL_XLSX_CHARS.sub("", value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, list) and all(
        item is None or isinstance(item, (bool, int, float, str)) for item in value
    ):
        return ", ".join("" if item is None else str(item) for item in value)
    return ILLEGAL_XLSX_CHARS.sub(
        "", json_.dumps(value, ensure_ascii=False, sort_keys=True)
    )


def excel_columns(records):
    keys = set()
    for record in records:
        keys.update(record)
    columns = ["airtable_id"] if "airtable_id" in keys else []
    columns.extend(
        sorted(key for key in keys if key not in ("airtable_id", "airtable_createdTime"))
    )
    if "airtable_createdTime" in keys:
        columns.append("airtable_createdTime")
    return columns


def sheet_title(name):
    title = INVALID_SHEET_CHARS.sub("_", filesystem_name(name))[:31].strip(" .")
    return title or "Sheet"


def unique_sheet_title(name, used):
    base = sheet_title(name)
    title = base
    number = 2
    while title in used:
        suffix = "_{}".format(number)
        title = (base[: 31 - len(suffix)] + suffix).strip(" .") or "Sheet"
        number += 1
    used.add(title)
    return title


def write_sheet(worksheet, table, records, used_titles):
    worksheet.title = unique_sheet_title(table, used_titles)
    columns = excel_columns(records)
    if columns:
        worksheet.append(columns)
        for record in records:
            worksheet.append([excel_cell(record.get(column)) for column in columns])


def write_base_xlsx(path, tables):
    workbook = Workbook()
    used_titles = set()
    first = True
    for table, records in tables:
        if first:
            worksheet = workbook.active
            first = False
        else:
            worksheet = workbook.create_sheet()
        write_sheet(worksheet, table, records, used_titles)
    workbook.save(path)


def write_table_files(output, table, records, json, ndjson, yaml):
    filenames = []
    stem = filesystem_name(table)
    if json:
        filename = "{}.json".format(stem)
        dumped = json_.dumps(records, sort_keys=True, indent=4, ensure_ascii=False)
        (output / filename).write_text(dumped, "utf-8")
        filenames.append(output / filename)
    if ndjson:
        filename = "{}.ndjson".format(stem)
        dumped = "\n".join(
            json_.dumps(r, sort_keys=True, ensure_ascii=False) for r in records
        )
        (output / filename).write_text(dumped, "utf-8")
        filenames.append(output / filename)
    if yaml:
        filename = "{}.yml".format(stem)
        dumped = yaml_.dump(records, sort_keys=True, allow_unicode=True)
        (output / filename).write_text(dumped, "utf-8")
        filenames.append(output / filename)
    return filenames


def is_attachment(value):
    if not isinstance(value, dict):
        return False
    attachment_id = value.get("id")
    url = value.get("url")
    return (
        isinstance(attachment_id, str)
        and attachment_id.startswith("att")
        and isinstance(url, str)
        and bool(url)
        and isinstance(value.get("filename"), str)
    )


def iter_attachments(records):
    for record in records:
        for value in record.values():
            if not isinstance(value, list) or not value:
                continue
            if all(is_attachment(item) for item in value):
                yield from value


def attachment_filename(attachment):
    filename = INVALID_FILENAME_CHARS.sub("_", attachment.get("filename") or "")
    filename = filename.strip(" .")
    if not filename:
        filename = attachment["id"]
    return "{}-original-{}".format(attachment["id"], filename)


def attachment_already_saved(dest, attachment):
    size = attachment.get("size")
    return type(size) is int and dest.is_file() and dest.stat().st_size == size


def save_table_attachments(
    output, table, records, http_read_timeout, user_agent=None, on_file=None
):
    "Download original files for one table. Returns (saved_count, failed_count)."
    pending = list(iter_attachments(records))
    if not pending:
        return 0, 0
    folder = output / filesystem_name(table)
    folder.mkdir(parents=True, exist_ok=True)
    read_timeout = http_read_timeout or DEFAULT_ATTACHMENT_READ_TIMEOUT
    timeout = httpx.Timeout(5, read=read_timeout)
    headers = {}
    if user_agent is not None:
        headers["user-agent"] = user_agent
    saved = 0
    failed = 0
    with httpx.Client(
        timeout=timeout, headers=headers, follow_redirects=True
    ) as client:
        for number, attachment in enumerate(pending, start=1):
            if on_file is not None:
                on_file(number, attachment)
            dest_name = attachment_filename(attachment)
            dest = folder / dest_name
            if attachment_already_saved(dest, attachment):
                attachment["_saved"] = dest.relative_to(output).as_posix()
                saved += 1
                continue
            tmp = folder / "{}.part".format(dest_name)
            try:
                with client.stream("GET", attachment["url"]) as response:
                    response.raise_for_status()
                    with tmp.open("wb") as handle:
                        for chunk in response.iter_bytes():
                            handle.write(chunk)
                os.replace(tmp, dest)
            except (HTTPError, OSError) as exc:
                if tmp.exists():
                    tmp.unlink()
                failed += 1
                click.echo(
                    "Failed to download {}: {}".format(
                        attachment.get("filename") or attachment["id"], exc
                    ),
                    err=True,
                )
                continue
            attachment["_saved"] = dest.relative_to(output).as_posix()
            saved += 1
    if saved == 0:
        try:
            folder.rmdir()
        except OSError:
            pass
    return saved, failed


def str_representer(dumper, data):
    try:
        if "\n" in data:
            return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    except TypeError:
        pass
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


yaml_.add_representer(str, str_representer)
