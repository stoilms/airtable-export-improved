from click.testing import CliRunner
from airtable_export import cli
import json
import pathlib
import pytest
import sqlite_utils
from openpyxl import load_workbook
from urllib.parse import quote

FORMATS = [
    (
        "yaml",
        """
- address: |-
    Address line 1
    Address line 2
  airtable_createdTime: '2020-04-18T18:50:27.000Z'
  airtable_id: rec1
  name: This is the name
  size: 441
  true_or_false: true
  'weird name: what is this?': hello
- address: |-
    Address line 1
    Address line 2
  airtable_createdTime: '2020-04-18T18:58:27.000Z'
  airtable_id: rec2
  name: This is the name 2
  size: 442
  true_or_false: false
  'weird name: what is this?': there
       """,
    ),
    (
        "json",
        r"""
[
    {
        "address": "Address line 1\nAddress line 2",
        "airtable_createdTime": "2020-04-18T18:50:27.000Z",
        "airtable_id": "rec1",
        "name": "This is the name",
        "size": 441,
        "true_or_false": true,
        "weird name: what is this?": "hello"
    },
    {
        "address": "Address line 1\nAddress line 2",
        "airtable_createdTime": "2020-04-18T18:58:27.000Z",
        "airtable_id": "rec2",
        "name": "This is the name 2",
        "size": 442,
        "true_or_false": false,
        "weird name: what is this?": "there"
    }
]
       """,
    ),
    (
        "ndjson",
        r"""
{"address": "Address line 1\nAddress line 2", "airtable_createdTime": "2020-04-18T18:50:27.000Z", "airtable_id": "rec1", "name": "This is the name", "size": 441, "true_or_false": true, "weird name: what is this?": "hello"}
{"address": "Address line 1\nAddress line 2", "airtable_createdTime": "2020-04-18T18:58:27.000Z", "airtable_id": "rec2", "name": "This is the name 2", "size": 442, "true_or_false": false, "weird name: what is this?": "there"}
       """,
    ),
]


BASE_ID = "appZOGvNJPXCQ205F"


def exported(tmp_path, *parts):
    return tmp_path.joinpath(BASE_ID, *parts)


def shown(*parts):
    return str(pathlib.Path(BASE_ID, *parts))


def invoke(tmp_path, monkeypatch, args, **kwargs):
    monkeypatch.chdir(tmp_path)
    return CliRunner().invoke(cli.cli, args, **kwargs)


def command(formats, table=None, key="x", bases=None):
    args = ["--bases", bases or BASE_ID, "--formats", formats]
    if table is not None:
        args.extend(["--tables", table])
    if key is not None:
        args.extend(["--key", key])
    return args


def test_version():
    runner = CliRunner()
    result = runner.invoke(cli.cli, ["--version"])
    assert 0 == result.exit_code
    assert result.output.startswith("cli, version ")


@pytest.fixture
def mock_table(httpx_mock):
    httpx_mock.add_response(
        url="https://api.airtable.com/v0/appZOGvNJPXCQ205F/tablename",
        json=AIRTABLE_RESPONSE,
    )


@pytest.fixture
def mock_table_list(httpx_mock):
    httpx_mock.add_response(
        url="https://api.airtable.com/v0/meta/bases/appZOGvNJPXCQ205F/tables",
        json={"tables": [{"id": "tbl123", "name": "tablename"}]},
    )


@pytest.mark.parametrize("format,expected", FORMATS)
@pytest.mark.parametrize(
    "extra_arguments",
    [["--tables", "tablename"], [], ["--tables", "tablename", "--schema"]],
)
def test_airtable_export(
    mock_table, httpx_mock, format, expected, extra_arguments, tmp_path, monkeypatch
):
    if not extra_arguments or "--schema" in extra_arguments:
        httpx_mock.add_response(
            url="https://api.airtable.com/v0/meta/bases/appZOGvNJPXCQ205F/tables",
            json={"tables": [{"id": "tbl123", "name": "tablename"}]},
        )
    table_file = exported(
        tmp_path, "tablename.{}".format("yml" if format == "yaml" else format)
    )
    result = invoke(
        tmp_path,
        monkeypatch,
        command(format, key="x") + extra_arguments,
    )
    assert 0 == result.exit_code, result.output
    assert result.output.strip() == "\n".join(
        [
            "Exporting 1 table",
            "[1/1] tablename ...",
            "[1/1] tablename - 2 records -> {}".format(
                shown("tablename.{}".format("yml" if format == "yaml" else format))
            ),
        ]
    )
    actual = table_file.read_text(encoding="utf-8")
    assert expected.strip() == actual.strip()
    schema = exported(tmp_path, "_schema.json")
    if not extra_arguments or "--schema" in extra_arguments:
        assert schema.exists()
        assert schema.read_text(encoding="utf-8")[0] == "{"
    else:
        assert not schema.exists()


def test_all_three_formats_at_once(mock_table, tmp_path, monkeypatch):
    result = invoke(
        tmp_path,
        monkeypatch,
        command("json,ndjson,yaml", table="tablename"),
    )
    assert 0 == result.exit_code, result.output
    written = ", ".join(
        shown(name)
        for name in ("tablename.json", "tablename.ndjson", "tablename.yml")
    )
    assert result.output.strip() == "\n".join(
        [
            "Exporting 1 table",
            "[1/1] tablename ...",
            "[1/1] tablename - 2 records -> {}".format(written),
        ]
    )
    for format, expected in FORMATS:
        actual = exported(
            tmp_path, "tablename.{}".format("yml" if format == "yaml" else format)
        ).read_text(encoding="utf-8")
        assert expected.strip() == actual.strip()


def workbook_sheets(path):
    workbook = load_workbook(path)
    return {
        worksheet.title: list(worksheet.iter_rows(values_only=True))
        for worksheet in workbook.worksheets
    }


def test_xlsx_export(mock_table, tmp_path, monkeypatch):
    result = invoke(
        tmp_path,
        monkeypatch,
        command("xlsx", table="tablename"),
    )
    assert result.exit_code == 0, result.output
    workbook_path = exported(tmp_path, "appZOGvNJPXCQ205F.xlsx")
    assert result.output.strip() == "\n".join(
        [
            "Exporting 1 table",
            "[1/1] tablename ...",
            "[1/1] tablename - 2 records",
            "{} - 1 table, 2 records".format(shown("appZOGvNJPXCQ205F.xlsx")),
        ]
    )
    assert not exported(tmp_path, "tablename.yml").exists()
    sheets = workbook_sheets(workbook_path)
    assert list(sheets) == ["tablename"]
    rows = sheets["tablename"]
    headers = rows[0]
    assert headers[0] == "airtable_id"
    assert headers[-1] == "airtable_createdTime"
    assert "name" in headers
    assert "weird name: what is this?" in headers
    by_id = {row[0]: dict(zip(headers, row)) for row in rows[1:]}
    assert by_id["rec1"]["name"] == "This is the name"
    assert by_id["rec1"]["address"] == "Address line 1\nAddress line 2"
    assert by_id["rec1"]["true_or_false"] is True
    assert by_id["rec1"]["size"] == 441
    assert by_id["rec2"]["true_or_false"] is False


def test_xlsx_plain_lists_and_cyrillic(httpx_mock, tmp_path, monkeypatch):
    table = "Backlog: Теми"
    httpx_mock.add_response(
        url="https://api.airtable.com/v0/appZOGvNJPXCQ205F/{}".format(
            quote(table, safe="")
        ),
        json={
            "records": [
                {
                    "id": "rec1",
                    "fields": {
                        "Тема": "Анализ",
                        "Tags": ["едно", "две"],
                        "Photos": [
                            {
                                "id": "attwPzAABrX7mUpdl",
                                "url": "https://example.test/photo.jpg",
                                "filename": "снимка.jpg",
                            }
                        ],
                    },
                    "createdTime": "2020-04-18T18:50:27.000Z",
                }
            ]
        },
    )
    result = invoke(tmp_path, monkeypatch, command("xlsx", table=table))
    assert result.exit_code == 0, result.output
    sheets = workbook_sheets(exported(tmp_path, "appZOGvNJPXCQ205F.xlsx"))
    assert list(sheets) == ["Backlog_ Теми"]
    rows = sheets["Backlog_ Теми"]
    record = dict(zip(rows[0], rows[1]))
    assert record["Тема"] == "Анализ"
    assert record["Tags"] == "едно, две"
    photos = json.loads(record["Photos"])
    assert photos[0]["filename"] == "снимка.jpg"


def test_xlsx_one_workbook_for_the_base(httpx_mock, tmp_path, monkeypatch):
    long_name = "A" * 31
    httpx_mock.add_response(
        url="https://api.airtable.com/v0/appZOGvNJPXCQ205F/People",
        json={
            "records": [
                {
                    "id": "rec1",
                    "fields": {"Name": "Ada"},
                    "createdTime": "2020-04-18T18:50:27.000Z",
                }
            ]
        },
    )
    httpx_mock.add_response(
        url="https://api.airtable.com/v0/appZOGvNJPXCQ205F/{}".format(
            quote(long_name + "1", safe="")
        ),
        json={"records": []},
    )
    httpx_mock.add_response(
        url="https://api.airtable.com/v0/appZOGvNJPXCQ205F/{}".format(
            quote(long_name + "2", safe="")
        ),
        json={"records": []},
    )
    result = invoke(
        tmp_path,
        monkeypatch,
        command("xlsx", table="{},{},{}".format("People", long_name + "1", long_name + "2")),
    )
    assert result.exit_code == 0, result.output
    workbook_path = exported(tmp_path, "appZOGvNJPXCQ205F.xlsx")
    assert workbook_path.exists()
    assert not exported(tmp_path, "People.xlsx").exists()
    sheets = workbook_sheets(workbook_path)
    assert list(sheets) == ["People", "A" * 31, ("A" * 29) + "_2"]
    assert sheets["People"][1][sheets["People"][0].index("Name")] == "Ada"
    assert "[1/3] People - 1 record" in result.output
    assert "{} - 3 tables, 1 record".format(shown("appZOGvNJPXCQ205F.xlsx")) in result.output


def test_xlsx_includes_saved_attachment_path(httpx_mock, tmp_path, monkeypatch):
    add_table(httpx_mock, records_with_attachments())
    add_files(httpx_mock)
    result = invoke(
        tmp_path,
        monkeypatch,
        command("xlsx", table="tablename") + ["--attachments"],
    )
    assert result.exit_code == 0, result.output
    sheets = workbook_sheets(exported(tmp_path, "appZOGvNJPXCQ205F.xlsx"))
    rows = sheets["tablename"]
    record = dict(zip(rows[0], rows[1]))
    photos = json.loads(record["Photos"])
    assert photos[0]["_saved"] == "tablename/{}".format(
        saved_name(PHOTO_ID, "photo.jpg")
    )


def test_airtable_sqlite(mock_table, tmp_path, monkeypatch):
    db_path = exported(tmp_path, "{}.db".format(BASE_ID))
    result = invoke(
        tmp_path,
        monkeypatch,
        command("sqlite", table="tablename"),
        catch_exceptions=False,
    )
    assert 0 == result.exit_code, result.output
    assert result.output.strip() == "\n".join(
        [
            "Exporting 1 table",
            "[1/1] tablename ...",
            "[1/1] tablename - writing to {}".format(shown("{}.db".format(BASE_ID))),
            "[1/1] tablename - 2 records -> {}".format(shown("{}.db".format(BASE_ID))),
        ]
    )
    db = sqlite_utils.Database(db_path)
    assert db.table_names() == ["tablename"]
    assert list(db["tablename"].rows) == [
        {
            "airtable_id": "rec1",
            "name": "This is the name",
            "address": "Address line 1\nAddress line 2",
            "weird name: what is this?": "hello",
            "size": 441,
            "true_or_false": 1,
            "airtable_createdTime": "2020-04-18T18:50:27.000Z",
        },
        {
            "airtable_id": "rec2",
            "name": "This is the name 2",
            "address": "Address line 1\nAddress line 2",
            "weird name: what is this?": "there",
            "size": 442,
            "true_or_false": 0,
            "airtable_createdTime": "2020-04-18T18:58:27.000Z",
        },
    ]


def test_key_from_dotenv(httpx_mock, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("AIRTABLE_PAT=from-dotenv\n", encoding="utf-8")
    httpx_mock.add_response(
        url="https://api.airtable.com/v0/appZOGvNJPXCQ205F/tablename",
        json={"records": []},
    )
    result = invoke(
        tmp_path,
        monkeypatch,
        command("yaml", table="tablename", key=None),
    )
    assert result.exit_code == 0, result.output
    assert httpx_mock.get_requests()[0].headers["authorization"] == "Bearer from-dotenv"


def test_key_argument_overrides_dotenv(httpx_mock, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("AIRTABLE_PAT=from-dotenv\n", encoding="utf-8")
    httpx_mock.add_response(
        url="https://api.airtable.com/v0/appZOGvNJPXCQ205F/tablename",
        json={"records": []},
    )
    result = invoke(
        tmp_path,
        monkeypatch,
        command("yaml", table="tablename", key="from-arg"),
    )
    assert result.exit_code == 0, result.output
    assert httpx_mock.get_requests()[0].headers["authorization"] == "Bearer from-arg"


def test_missing_key(tmp_path, monkeypatch):
    result = invoke(
        tmp_path,
        monkeypatch,
        command("yaml", table="tablename", key=None),
    )
    assert result.exit_code != 0
    assert "AIRTABLE_PAT" in result.output


def test_formats_are_required(tmp_path, monkeypatch):
    result = invoke(
        tmp_path,
        monkeypatch,
        ["--bases", BASE_ID, "--key", "x", "--tables", "tablename"],
    )
    assert result.exit_code != 0
    assert "--formats" in result.output


def test_unknown_format_is_rejected(tmp_path, monkeypatch):
    result = invoke(
        tmp_path,
        monkeypatch,
        command("csv", table="tablename"),
    )
    assert result.exit_code != 0
    assert "yaml, json, ndjson, xlsx, sqlite" in result.output


def test_exports_each_listed_base(httpx_mock, tmp_path, monkeypatch):
    second = "appSecondBaseId0001"
    for base in (BASE_ID, second):
        httpx_mock.add_response(
            url="https://api.airtable.com/v0/meta/bases/{}/tables".format(base),
            json={"tables": [{"id": "tbl1", "name": "tablename"}]},
        )
        httpx_mock.add_response(
            url="https://api.airtable.com/v0/{}/tablename".format(base),
            json={"records": []},
        )
    result = invoke(
        tmp_path,
        monkeypatch,
        command("yaml", bases="{}, {}".format(BASE_ID, second)),
    )
    assert result.exit_code == 0, result.output
    assert exported(tmp_path, "tablename.yml").is_file()
    assert (tmp_path / second / "tablename.yml").is_file()
    first_line = result.output.index("[1/2] base {}".format(BASE_ID))
    second_line = result.output.index("[2/2] base {}".format(second))
    assert first_line < second_line
    assert result.output.count("[1/1] tablename - 0 records ->") == 2


def test_tables_rejected_when_several_bases(tmp_path, monkeypatch):
    second = "appSecondBaseId0001"
    result = invoke(
        tmp_path,
        monkeypatch,
        command(
            "yaml",
            table="tablename",
            bases="{},{}".format(BASE_ID, second),
        ),
    )
    assert result.exit_code != 0
    assert "--tables cannot be used with more than one base" in result.output
    assert not exported(tmp_path, "tablename.yml").exists()
    assert not (tmp_path / second).exists()


def test_quiet_hides_progress(mock_table, tmp_path, monkeypatch):
    result = invoke(
        tmp_path,
        monkeypatch,
        command("yaml", table="tablename") + ["--quiet"],
    )
    assert result.exit_code == 0, result.output
    assert result.output.strip() == ""
    assert exported(tmp_path, "tablename.yml").is_file()


def test_quiet_still_reports_download_failure(httpx_mock, tmp_path, monkeypatch):
    add_table(httpx_mock, records_with_attachments())
    httpx_mock.add_response(url=PHOTO_URL, status_code=404)
    httpx_mock.add_response(url=PDF_URL, content=PDF_BYTES)
    result = invoke(
        tmp_path,
        monkeypatch,
        command("yaml", table="tablename") + ["--attachments", "--quiet"],
    )
    assert result.exit_code == 1
    assert "Failed to download photo.jpg" in result.output
    assert "Exporting" not in result.output
    assert "downloading" not in result.output
    assert exported(tmp_path, "tablename.yml").is_file()


def test_useragent_is_sent(mock_table, tmp_path, monkeypatch, httpx_mock):
    result = invoke(
        tmp_path,
        monkeypatch,
        command("yaml", table="tablename") + ["--useragent", "Airtable Export Robot"],
    )
    assert result.exit_code == 0, result.output
    assert (
        httpx_mock.get_requests()[0].headers["user-agent"] == "Airtable Export Robot"
    )


def test_table_name_with_colon(httpx_mock, tmp_path, monkeypatch):
    table = "Backlog: Теми за обществени съвети"
    httpx_mock.add_response(
        url="https://api.airtable.com/v0/appZOGvNJPXCQ205F/{}".format(
            quote(table, safe="")
        ),
        json={
            "records": [
                {
                    "id": "rec1",
                    "fields": {"name": "Тема"},
                    "createdTime": "2020-04-18T18:50:27.000Z",
                }
            ]
        },
    )
    result = invoke(tmp_path, monkeypatch, command("yaml", table=table))
    assert result.exit_code == 0, result.output
    table_file = exported(tmp_path, "Backlog_ Теми за обществени съвети.yml")
    text = table_file.read_text(encoding="utf-8")
    assert "Тема" in text
    assert "\\u" not in text
    assert table_file.stat().st_size > 0
    assert not exported(tmp_path, "Backlog").exists()


def test_airtable_export_error(httpx_mock, tmp_path, monkeypatch):
    httpx_mock.add_response(status_code=401)
    result = invoke(
        tmp_path,
        monkeypatch,
        command("yaml", table="tablename"),
    )
    assert result.exit_code == 1
    assert "401 Unauthorized" in result.output


PHOTO_URL = "https://example.test/photo.jpg"
THUMB_URL = "https://example.test/small.jpg"
PDF_URL = "https://example.test/ardata.pdf"
PHOTO_BYTES = b"hello"
PDF_BYTES = b"%PDF"
PHOTO_ID = "attwPzAABrX7mUpdl"
PDF_ID = "attHd9sanAvr8PwGk"
BASE_URL = "https://api.airtable.com/v0/appZOGvNJPXCQ205F/tablename"


def records_with_attachments(filename="photo.jpg"):
    return {
        "records": [
            {
                "id": "rec1",
                "fields": {
                    "name": "This is the name",
                    "Photos": [
                        {
                            "id": PHOTO_ID,
                            "url": PHOTO_URL,
                            "filename": filename,
                            "size": len(PHOTO_BYTES),
                            "type": "image/jpeg",
                            "thumbnails": {
                                "small": {
                                    "url": THUMB_URL,
                                    "width": 48,
                                    "height": 36,
                                }
                            },
                        },
                        {
                            "id": PDF_ID,
                            "url": PDF_URL,
                            "filename": "ardata.pdf",
                            "size": len(PDF_BYTES),
                            "type": "application/pdf",
                        },
                    ],
                },
                "createdTime": "2020-04-18T18:50:27.000Z",
            }
        ]
    }


def add_table(httpx_mock, payload):
    httpx_mock.add_response(url=BASE_URL, json=payload)


def add_files(httpx_mock):
    httpx_mock.add_response(url=PHOTO_URL, content=PHOTO_BYTES)
    httpx_mock.add_response(url=PDF_URL, content=PDF_BYTES)


def saved_name(attachment_id, filename):
    return "{}-original-{}".format(attachment_id, filename)


@pytest.mark.parametrize("format", ["yaml", "json", "ndjson"])
def test_attachments_saved_next_to_table(httpx_mock, format, tmp_path, monkeypatch):
    add_table(httpx_mock, records_with_attachments())
    add_files(httpx_mock)
    result = invoke(
        tmp_path,
        monkeypatch,
        command(format, table="tablename") + ["--attachments"],
    )
    assert result.exit_code == 0, result.output
    photo = exported(tmp_path, "tablename", saved_name(PHOTO_ID, "photo.jpg"))
    pdf = exported(tmp_path, "tablename", saved_name(PDF_ID, "ardata.pdf"))
    assert photo.read_bytes() == PHOTO_BYTES
    assert pdf.read_bytes() == PDF_BYTES
    text = exported(
        tmp_path, "tablename.{}".format("yml" if format == "yaml" else format)
    ).read_text(encoding="utf-8")
    assert "tablename/{}".format(saved_name(PHOTO_ID, "photo.jpg")) in text
    assert "tablename/{}".format(saved_name(PDF_ID, "ardata.pdf")) in text
    assert PHOTO_URL in text
    assert THUMB_URL in text
    record_line = result.output.index("[1/1] tablename - 1 record ->")
    download_line = result.output.index("[1/1] tablename - downloading 2 attachments")
    assert record_line < download_line
    assert "  [1/2] photo.jpg" in result.output
    assert "  [2/2] ardata.pdf" in result.output
    assert "[1/1] tablename - 2 attachments" in result.output
    for request in httpx_mock.get_requests():
        if request.url.host == "example.test":
            assert "authorization" not in request.headers


def test_attachments_sqlite(httpx_mock, tmp_path, monkeypatch):
    add_table(httpx_mock, records_with_attachments())
    add_files(httpx_mock)
    db_path = exported(tmp_path, "{}.db".format(BASE_ID))
    result = invoke(
        tmp_path,
        monkeypatch,
        command("sqlite", table="tablename") + ["--attachments"],
    )
    assert result.exit_code == 0, result.output
    db_shown = shown("{}.db".format(BASE_ID))
    record_line = result.output.index(
        "[1/1] tablename - 1 record -> {}".format(db_shown)
    )
    download_line = result.output.index("[1/1] tablename - downloading 2 attachments")
    rewrite_line = result.output.index(
        "[1/1] tablename - writing 1 record to {}".format(db_shown)
    )
    assert result.output.index("[1/1] tablename - writing to {}".format(db_shown)) < record_line
    assert record_line < download_line < rewrite_line
    photo = exported(tmp_path, "tablename", saved_name(PHOTO_ID, "photo.jpg"))
    assert photo.read_bytes() == PHOTO_BYTES
    db = sqlite_utils.Database(db_path)
    photos = list(db["tablename"].rows)[0]["Photos"]
    if isinstance(photos, str):
        photos = json.loads(photos)
    by_id = {item["id"]: item for item in photos}
    assert by_id[PHOTO_ID]["_saved"] == "tablename/{}".format(
        saved_name(PHOTO_ID, "photo.jpg")
    )
    assert by_id[PHOTO_ID]["url"] == PHOTO_URL
    assert by_id[PHOTO_ID]["thumbnails"]["small"]["url"] == THUMB_URL
    assert "_saved" not in by_id[PHOTO_ID]["thumbnails"]["small"]
    assert by_id[PDF_ID]["_saved"] == "tablename/{}".format(
        saved_name(PDF_ID, "ardata.pdf")
    )


def test_attachments_skip_existing_file(httpx_mock, tmp_path, monkeypatch):
    add_table(httpx_mock, records_with_attachments())
    add_files(httpx_mock)
    args = command("yaml", table="tablename") + ["--attachments"]
    first = invoke(tmp_path, monkeypatch, args)
    assert first.exit_code == 0, first.output
    add_table(httpx_mock, records_with_attachments())
    second = invoke(tmp_path, monkeypatch, args)
    assert second.exit_code == 0, second.output
    photo_hits = [
        request
        for request in httpx_mock.get_requests()
        if str(request.url) == PHOTO_URL
    ]
    pdf_hits = [
        request for request in httpx_mock.get_requests() if str(request.url) == PDF_URL
    ]
    assert len(photo_hits) == 1
    assert len(pdf_hits) == 1
    text = exported(tmp_path, "tablename.yml").read_text(encoding="utf-8")
    assert "tablename/{}".format(saved_name(PHOTO_ID, "photo.jpg")) in text


def test_attachments_sanitize_filename(httpx_mock, tmp_path, monkeypatch):
    payload = {
        "records": [
            {
                "id": "rec1",
                "fields": {
                    "Docs": [
                        {
                            "id": PDF_ID,
                            "url": PDF_URL,
                            "filename": "q1:report/final.pdf",
                            "size": len(PDF_BYTES),
                            "type": "application/pdf",
                        }
                    ]
                },
                "createdTime": "2020-04-18T18:50:27.000Z",
            }
        ]
    }
    add_table(httpx_mock, payload)
    httpx_mock.add_response(url=PDF_URL, content=PDF_BYTES)
    result = invoke(
        tmp_path,
        monkeypatch,
        command("yaml", table="tablename") + ["--attachments"],
    )
    assert result.exit_code == 0, result.output
    expected = saved_name(PDF_ID, "q1_report_final.pdf")
    assert exported(tmp_path, "tablename", expected).read_bytes() == PDF_BYTES
    text = exported(tmp_path, "tablename.yml").read_text(encoding="utf-8")
    assert "tablename/{}".format(expected) in text


def test_attachments_download_failure_still_writes_table(httpx_mock, tmp_path, monkeypatch):
    add_table(httpx_mock, records_with_attachments())
    httpx_mock.add_response(url=PHOTO_URL, status_code=404)
    httpx_mock.add_response(url=PDF_URL, content=PDF_BYTES)
    result = invoke(
        tmp_path,
        monkeypatch,
        command("yaml", table="tablename") + ["--attachments"],
    )
    assert result.exit_code == 1
    table_file = exported(tmp_path, "tablename.yml")
    record_line = result.output.index(
        "[1/1] tablename - 1 record -> {}".format(shown("tablename.yml"))
    )
    download_line = result.output.index("[1/1] tablename - downloading 2 attachments")
    photo_line = result.output.index("  [1/2] photo.jpg")
    failure_line = result.output.index("Failed to download photo.jpg")
    summary_line = result.output.index("[1/1] tablename - 1 attachment, 1 failure")
    assert record_line < download_line < photo_line < failure_line < summary_line
    assert "  [2/2] ardata.pdf" in result.output
    text = table_file.read_text(encoding="utf-8")
    assert PHOTO_URL in text
    assert "tablename/{}".format(saved_name(PHOTO_ID, "photo.jpg")) not in text
    assert "tablename/{}".format(saved_name(PDF_ID, "ardata.pdf")) in text
    saved_pdf = exported(tmp_path, "tablename", saved_name(PDF_ID, "ardata.pdf"))
    assert saved_pdf.read_bytes() == PDF_BYTES
    assert not exported(tmp_path, "tablename", saved_name(PHOTO_ID, "photo.jpg")).exists()
    assert list(exported(tmp_path, "tablename").glob("*.part")) == []


def test_attachments_not_downloaded_without_flag(httpx_mock, tmp_path, monkeypatch):
    add_table(httpx_mock, records_with_attachments())
    result = invoke(tmp_path, monkeypatch, command("yaml", table="tablename"))
    assert result.exit_code == 0, result.output
    text = exported(tmp_path, "tablename.yml").read_text(encoding="utf-8")
    assert "_saved" not in text
    assert not exported(tmp_path, "tablename").exists()


AIRTABLE_RESPONSE = {
    "records": [
        {
            "id": "rec1",
            "fields": {
                "name": "This is the name",
                "address": "Address line 1\nAddress line 2",
                "weird name: what is this?": "hello",
                "size": 441,
                "true_or_false": True,
            },
            "createdTime": "2020-04-18T18:50:27.000Z",
        },
        {
            "id": "rec2",
            "fields": {
                "name": "This is the name 2",
                "address": "Address line 1\nAddress line 2",
                "weird name: what is this?": "there",
                "size": 442,
                "true_or_false": False,
            },
            "createdTime": "2020-04-18T18:58:27.000Z",
        },
    ]
}
