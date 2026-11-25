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

# Attachment files can be several megabytes, so use a longer read timeout
# than httpx's 5 second default when --http-read-timeout is not set.
DEFAULT_ATTACHMENT_READ_TIMEOUT = 120
INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


@click.command()
@click.version_option()
@click.argument(
    "output_path",
    type=click.Path(file_okay=False, dir_okay=True, allow_dash=False),
    required=True,
)
@click.argument(
    "base_id",
    type=str,
    required=True,
)
@click.argument("tables", type=str, nargs=-1)
@click.option("--key", envvar="AIRTABLE_KEY", help="Airtable API key", required=True)
@click.option(
    "--http-read-timeout",
    help="Timeout (in seconds) for network read operations",
    type=int,
)
@click.option("--user-agent", help="User agent to use for requests")
@click.option("-v", "--verbose", is_flag=True, help="Verbose output")
@click.option("--json", is_flag=True, help="JSON format")
@click.option("--ndjson", is_flag=True, help="Newline delimited JSON format")
@click.option("--yaml", is_flag=True, help="YAML format (default)")
@click.option(
    "--sqlite",
    type=click.Path(file_okay=True, dir_okay=False, allow_dash=False),
    help="Export to this SQLite database",
)
@click.option(
    "--schema",
    is_flag=True,
    help="Save Airtable schema to output_path/_schema.json",
)
@click.option(
    "--attachments",
    is_flag=True,
    help="Download attachment and image files into a subfolder per table",
)
def cli(
    output_path,
    base_id,
    tables,
    key,
    http_read_timeout,
    user_agent,
    verbose,
    json,
    ndjson,
    yaml,
    sqlite,
    schema,
    attachments,
):
    "Export Airtable data to YAML file on disk"
    output = pathlib.Path(output_path)
    output.mkdir(parents=True, exist_ok=True)
    if not json and not ndjson and not yaml and not sqlite:
        yaml = True
    write_batch = lambda table, batch: None
    if sqlite:
        db = sqlite_utils.Database(sqlite)
        write_batch = lambda table, batch: db[table].insert_all(
            batch, pk="airtable_id", replace=True, alter=True
        )
    if not tables or schema:
        # Fetch all tables
        schema_data = list_tables(base_id, key, user_agent=user_agent)
        dumped_schema = json_.dumps(schema_data, sort_keys=True, indent=4)
        (output / "_schema.json").write_text(dumped_schema, "utf-8")
        if not tables:
            tables = [table["name"] for table in schema_data["tables"]]

    failed_downloads = 0
    for table in tables:
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
        if verbose:
            click.echo(
                "Wrote {} record{} to {}".format(
                    len(records),
                    "" if len(records) == 1 else "s",
                    ", ".join(map(str, filenames)),
                ),
                err=True,
            )
        if attachments:
            saved, failed = save_table_attachments(
                output,
                table,
                records,
                http_read_timeout,
                user_agent=user_agent,
            )
            failed_downloads += failed
            if saved:
                write_table_files(output, table, records, json, ndjson, yaml)
                write_batch(table, records)
                if verbose:
                    click.echo(
                        "Saved {} attachment{} to {}".format(
                            saved,
                            "" if saved == 1 else "s",
                            output / table,
                        ),
                        err=True,
                    )
    if failed_downloads:
        raise click.ClickException(
            "Failed to download {} attachment{}".format(
                failed_downloads, "" if failed_downloads == 1 else "s"
            )
        )


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


def write_table_files(output, table, records, json, ndjson, yaml):
    filenames = []
    if json:
        filename = "{}.json".format(table)
        dumped = json_.dumps(records, sort_keys=True, indent=4)
        (output / filename).write_text(dumped, "utf-8")
        filenames.append(output / filename)
    if ndjson:
        filename = "{}.ndjson".format(table)
        dumped = "\n".join(json_.dumps(r, sort_keys=True) for r in records)
        (output / filename).write_text(dumped, "utf-8")
        filenames.append(output / filename)
    if yaml:
        filename = "{}.yml".format(table)
        dumped = yaml_.dump(records, sort_keys=True)
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


def save_table_attachments(output, table, records, http_read_timeout, user_agent=None):
    "Download original files for one table. Returns (saved_count, failed_count)."
    pending = list(iter_attachments(records))
    if not pending:
        return 0, 0
    folder = output / table
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
        for attachment in pending:
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
