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
    "extra_arguments", [["tablename"], [], ["tablename", "--schema"]]
)
def test_airtable_export(
    mock_table, httpx_mock, format, expected, extra_arguments, tmp_path
):
    if not extra_arguments or "--schema" in extra_arguments:
        httpx_mock.add_response(
            url="https://api.airtable.com/v0/meta/bases/appZOGvNJPXCQ205F/tables",
            json={"tables": [{"id": "tbl123", "name": "tablename"}]},
        )
    runner = CliRunner()
    table_file = tmp_path / "tablename.{}".format("yml" if format == "yaml" else format)
    args = (
        [
            str(tmp_path),
            "appZOGvNJPXCQ205F",
        ]
        + extra_arguments
        + [
            "-v",
            "--key",
            "x",
            "--{}".format(format),
        ]
    )
    result = runner.invoke(
        cli.cli,
        args,
    )
    assert 0 == result.exit_code, result.output
    assert "Wrote 2 records to {}".format(table_file) == result.output.strip()
    actual = table_file.read_text(encoding="utf-8")
    assert expected.strip() == actual.strip()
    schema = tmp_path / "_schema.json"
    if not extra_arguments or "--schema" in extra_arguments:
        assert schema.exists()
        assert schema.read_text(encoding="utf-8")[0] == "{"
    else:
        assert not schema.exists()


def test_all_three_formats_at_once(mock_table, tmp_path):
    runner = CliRunner()
    args = [
        str(tmp_path),
        "appZOGvNJPXCQ205F",
        "tablename",
        "-v",
        "--key",
        "x",
        "--yaml",
        "--json",
        "--ndjson",
    ]
    result = runner.invoke(
        cli.cli,
        args,
    )
    assert 0 == result.exit_code, result.output
    written = ", ".join(
        str(tmp_path / name)
        for name in ("tablename.json", "tablename.ndjson", "tablename.yml")
    )
    assert "Wrote 2 records to {}".format(written) == result.output.strip()
    for format, expected in FORMATS:
        actual = (
            tmp_path / "tablename.{}".format("yml" if format == "yaml" else format)
        ).read_text(encoding="utf-8")
        assert expected.strip() == actual.strip()


def workbook_sheets(path):
    workbook = load_workbook(path)
    return {
        worksheet.title: list(worksheet.iter_rows(values_only=True))
        for worksheet in workbook.worksheets
    }


def test_xlsx_export(mock_table, tmp_path):
    runner = CliRunner()
    result = runner.invoke(
        cli.cli,
        [
            str(tmp_path),
            "appZOGvNJPXCQ205F",
            "tablename",
            "--key",
            "x",
            "--xlsx",
            "-v",
        ],
    )
    assert result.exit_code == 0, result.output
    workbook_path = tmp_path / "appZOGvNJPXCQ205F.xlsx"
    assert (
        "Wrote 2 records from 1 table to {}".format(workbook_path)
        == result.output.strip()
    )
    assert not (tmp_path / "tablename.yml").exists()
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


def test_xlsx_plain_lists_and_cyrillic(httpx_mock, tmp_path):
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
    runner = CliRunner()
    result = runner.invoke(
        cli.cli,
        [str(tmp_path), "appZOGvNJPXCQ205F", table, "--key", "x", "--xlsx"],
    )
    assert result.exit_code == 0, result.output
    sheets = workbook_sheets(tmp_path / "appZOGvNJPXCQ205F.xlsx")
    assert list(sheets) == ["Backlog_ Теми"]
    rows = sheets["Backlog_ Теми"]
    record = dict(zip(rows[0], rows[1]))
    assert record["Тема"] == "Анализ"
    assert record["Tags"] == "едно, две"
    photos = json.loads(record["Photos"])
    assert photos[0]["filename"] == "снимка.jpg"


def test_xlsx_one_workbook_for_the_base(httpx_mock, tmp_path):
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
    runner = CliRunner()
    result = runner.invoke(
        cli.cli,
        [
            str(tmp_path),
            "appZOGvNJPXCQ205F",
            "People",
            long_name + "1",
            long_name + "2",
            "--key",
            "x",
            "--xlsx",
            "-v",
        ],
    )
    assert result.exit_code == 0, result.output
    workbook_path = tmp_path / "appZOGvNJPXCQ205F.xlsx"
    assert workbook_path.exists()
    assert not (tmp_path / "People.xlsx").exists()
    sheets = workbook_sheets(workbook_path)
    assert list(sheets) == ["People", "A" * 31, ("A" * 29) + "_2"]
    assert sheets["People"][1][sheets["People"][0].index("Name")] == "Ada"
    assert "Wrote 1 record from 3 tables to {}".format(workbook_path) in result.output


def test_xlsx_includes_saved_attachment_path(httpx_mock, tmp_path):
    add_table(httpx_mock, records_with_attachments())
    add_files(httpx_mock)
    runner = CliRunner()
    result = runner.invoke(
        cli.cli,
        [
            str(tmp_path),
            "appZOGvNJPXCQ205F",
            "tablename",
            "--key",
            "x",
            "--xlsx",
            "--attachments",
        ],
    )
    assert result.exit_code == 0, result.output
    sheets = workbook_sheets(tmp_path / "appZOGvNJPXCQ205F.xlsx")
    rows = sheets["tablename"]
    record = dict(zip(rows[0], rows[1]))
    photos = json.loads(record["Photos"])
    assert photos[0]["_saved"] == "tablename/{}".format(
        saved_name(PHOTO_ID, "photo.jpg")
    )


def test_airtable_sqlite(mock_table, tmp_path):
    runner = CliRunner()
    db_path = tmp_path / "test.db"
    args = [
        str(tmp_path),
        "appZOGvNJPXCQ205F",
        "tablename",
        "--key",
        "x",
        "--sqlite",
        str(db_path),
    ]
    result = runner.invoke(cli.cli, args, catch_exceptions=False)
    assert 0 == result.exit_code, result.output
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
    runner = CliRunner()
    result = runner.invoke(
        cli.cli,
        [str(tmp_path / "out"), "appZOGvNJPXCQ205F", "tablename"],
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
    runner = CliRunner()
    result = runner.invoke(
        cli.cli,
        [
            str(tmp_path / "out"),
            "appZOGvNJPXCQ205F",
            "tablename",
            "--key",
            "from-arg",
        ],
    )
    assert result.exit_code == 0, result.output
    assert httpx_mock.get_requests()[0].headers["authorization"] == "Bearer from-arg"


def test_missing_key(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli.cli,
        [str(tmp_path), "appZOGvNJPXCQ205F", "tablename"],
    )
    assert result.exit_code != 0
    assert "AIRTABLE_PAT" in result.output


def test_table_name_with_colon(httpx_mock, tmp_path):
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
    runner = CliRunner()
    result = runner.invoke(
        cli.cli,
        [str(tmp_path), "appZOGvNJPXCQ205F", table, "--key", "x"],
    )
    assert result.exit_code == 0, result.output
    exported = tmp_path / "Backlog_ Теми за обществени съвети.yml"
    text = exported.read_text(encoding="utf-8")
    assert "Тема" in text
    assert "\\u" not in text
    assert exported.stat().st_size > 0
    assert not (tmp_path / "Backlog").exists()


def test_airtable_export_error(httpx_mock, tmp_path):
    httpx_mock.add_response(status_code=401)
    runner = CliRunner()
    result = runner.invoke(
        cli.cli,
        [str(tmp_path), "appZOGvNJPXCQ205F", "tablename", "-v", "--key", "x"],
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
def test_attachments_saved_next_to_table(httpx_mock, format, tmp_path):
    add_table(httpx_mock, records_with_attachments())
    add_files(httpx_mock)
    runner = CliRunner()
    result = runner.invoke(
        cli.cli,
        [
            str(tmp_path),
            "appZOGvNJPXCQ205F",
            "tablename",
            "--key",
            "x",
            "--{}".format(format),
            "--attachments",
            "-v",
        ],
    )
    assert result.exit_code == 0, result.output
    photo = tmp_path / "tablename" / saved_name(PHOTO_ID, "photo.jpg")
    pdf = tmp_path / "tablename" / saved_name(PDF_ID, "ardata.pdf")
    assert photo.read_bytes() == PHOTO_BYTES
    assert pdf.read_bytes() == PDF_BYTES
    text = (
        tmp_path / "tablename.{}".format("yml" if format == "yaml" else format)
    ).read_text(encoding="utf-8")
    assert "tablename/{}".format(saved_name(PHOTO_ID, "photo.jpg")) in text
    assert "tablename/{}".format(saved_name(PDF_ID, "ardata.pdf")) in text
    assert PHOTO_URL in text
    assert THUMB_URL in text
    assert "Saved 2 attachments to {}".format(tmp_path / "tablename") in result.output
    for request in httpx_mock.get_requests():
        if request.url.host == "example.test":
            assert "authorization" not in request.headers


def test_attachments_sqlite(httpx_mock, tmp_path):
    add_table(httpx_mock, records_with_attachments())
    add_files(httpx_mock)
    runner = CliRunner()
    db_path = tmp_path / "test.db"
    result = runner.invoke(
        cli.cli,
        [
            str(tmp_path),
            "appZOGvNJPXCQ205F",
            "tablename",
            "--key",
            "x",
            "--sqlite",
            str(db_path),
            "--attachments",
        ],
    )
    assert result.exit_code == 0, result.output
    photo = tmp_path / "tablename" / saved_name(PHOTO_ID, "photo.jpg")
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


def test_attachments_skip_existing_file(httpx_mock, tmp_path):
    add_table(httpx_mock, records_with_attachments())
    add_files(httpx_mock)
    runner = CliRunner()
    args = [
        str(tmp_path),
        "appZOGvNJPXCQ205F",
        "tablename",
        "--key",
        "x",
        "--attachments",
    ]
    first = runner.invoke(cli.cli, args)
    assert first.exit_code == 0, first.output
    add_table(httpx_mock, records_with_attachments())
    second = runner.invoke(cli.cli, args)
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
    text = (tmp_path / "tablename.yml").read_text(encoding="utf-8")
    assert "tablename/{}".format(saved_name(PHOTO_ID, "photo.jpg")) in text


def test_attachments_sanitize_filename(httpx_mock, tmp_path):
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
    runner = CliRunner()
    result = runner.invoke(
        cli.cli,
        [
            str(tmp_path),
            "appZOGvNJPXCQ205F",
            "tablename",
            "--key",
            "x",
            "--attachments",
        ],
    )
    assert result.exit_code == 0, result.output
    expected = saved_name(PDF_ID, "q1_report_final.pdf")
    assert (tmp_path / "tablename" / expected).read_bytes() == PDF_BYTES
    text = (tmp_path / "tablename.yml").read_text(encoding="utf-8")
    assert "tablename/{}".format(expected) in text


def test_attachments_download_failure_still_writes_table(httpx_mock, tmp_path):
    add_table(httpx_mock, records_with_attachments())
    httpx_mock.add_response(url=PHOTO_URL, status_code=404)
    httpx_mock.add_response(url=PDF_URL, content=PDF_BYTES)
    runner = CliRunner()
    result = runner.invoke(
        cli.cli,
        [
            str(tmp_path),
            "appZOGvNJPXCQ205F",
            "tablename",
            "--key",
            "x",
            "--attachments",
        ],
    )
    assert result.exit_code == 1
    assert "Failed to download photo.jpg" in result.output
    text = (tmp_path / "tablename.yml").read_text(encoding="utf-8")
    assert PHOTO_URL in text
    assert "tablename/{}".format(saved_name(PHOTO_ID, "photo.jpg")) not in text
    assert "tablename/{}".format(saved_name(PDF_ID, "ardata.pdf")) in text
    saved_pdf = tmp_path / "tablename" / saved_name(PDF_ID, "ardata.pdf")
    assert saved_pdf.read_bytes() == PDF_BYTES
    assert not (tmp_path / "tablename" / saved_name(PHOTO_ID, "photo.jpg")).exists()
    assert list((tmp_path / "tablename").glob("*.part")) == []


def test_attachments_not_downloaded_without_flag(httpx_mock, tmp_path):
    add_table(httpx_mock, records_with_attachments())
    runner = CliRunner()
    result = runner.invoke(
        cli.cli,
        [str(tmp_path), "appZOGvNJPXCQ205F", "tablename", "--key", "x"],
    )
    assert result.exit_code == 0, result.output
    text = (tmp_path / "tablename.yml").read_text(encoding="utf-8")
    assert "_saved" not in text
    assert not (tmp_path / "tablename").exists()


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
