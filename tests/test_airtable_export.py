from click.testing import CliRunner
from airtable_export import cli
import json
import pathlib
import pytest
import sqlite_utils

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
