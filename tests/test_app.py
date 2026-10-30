import io
import os
import zipfile

import pytest

from app import app

SAMPLE = os.path.join(os.path.dirname(__file__), "..", "samples", "sample_report.pdf")


@pytest.fixture()
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.fixture()
def sample_bytes():
    with open(SAMPLE, "rb") as f:
        return f.read()


def upload(client, data, filename="report.pdf", **form):
    payload = {"pdf": (io.BytesIO(data), filename)}
    payload.update(form)
    return client.post("/extract", data=payload, content_type="multipart/form-data")


def extract_file_id(client, sample_bytes):
    resp = upload(client, sample_bytes)
    assert resp.status_code == 200
    # file_id is embedded in the results page links (/page-img/<id>/1, /csv/<id>/0)
    html = resp.get_data(as_text=True)
    marker = "/page-img/"
    start = html.index(marker) + len(marker)
    return html[start:start + 32]


def test_sample_path_is_absolute():
    import app as app_module
    assert os.path.isabs(app_module.SAMPLE_PATH)
    assert os.path.exists(app_module.SAMPLE_PATH)


def test_index_loads(client):
    assert client.get("/").status_code == 200


def test_extract_sample_report(client, sample_bytes):
    resp = upload(client, sample_bytes, use_sample=None)  # real upload path
    html = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "Table 1" in html and "Table 2" in html
    assert "Northeast" in html
    assert "Cloud infrastructure" in html
    assert "2 pages" in html


def test_extract_via_sample_button(client):
    resp = client.post("/extract", data={"use_sample": "1"})
    assert resp.status_code == 200
    assert "Table 1" in resp.get_data(as_text=True)


def test_rejects_non_pdf(client):
    resp = upload(client, b"just some text", filename="notes.txt")
    assert resp.status_code == 400


def test_rejects_empty_upload(client):
    resp = client.post("/extract", data={})
    assert resp.status_code == 400


def test_rejects_garbage_pdf(client):
    resp = upload(client, b"%PDF-1.4 not really a pdf")
    assert resp.status_code == 400


def test_serve_pdf_roundtrip(client, sample_bytes):
    file_id = extract_file_id(client, sample_bytes)
    resp = client.get(f"/pdf/{file_id}")
    assert resp.status_code == 200
    assert resp.content_type == "application/pdf"
    assert resp.data == sample_bytes


def test_page_image_is_png(client, sample_bytes):
    file_id = extract_file_id(client, sample_bytes)
    resp = client.get(f"/page-img/{file_id}/1")
    assert resp.status_code == 200
    assert resp.content_type == "image/png"
    assert resp.data[:8] == b"\x89PNG\r\n\x1a\n"
    assert client.get(f"/page-img/{file_id}/99").status_code == 404


def test_download_csv(client, sample_bytes):
    file_id = extract_file_id(client, sample_bytes)
    resp = client.get(f"/csv/{file_id}/0")
    assert resp.status_code == 200
    assert "text/csv" in resp.content_type
    first_line = resp.get_data(as_text=True).splitlines()[0]
    assert first_line == "Region,Q1,Q2,Q3,Q4"


def test_download_all_zip(client, sample_bytes):
    file_id = extract_file_id(client, sample_bytes)
    resp = client.get(f"/csv-all/{file_id}")
    assert resp.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(resp.data)).namelist()
    assert len(names) == 2
    assert all(n.endswith(".csv") for n in names)


def test_bad_csv_index_404(client, sample_bytes):
    file_id = extract_file_id(client, sample_bytes)
    assert client.get(f"/csv/{file_id}/99").status_code == 404
    assert client.get("/pdf/doesnotexist").status_code == 404


def test_api_extract(client, sample_bytes):
    resp = client.post(
        "/api/extract",
        data={"pdf": (io.BytesIO(sample_bytes), "report.pdf")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["pages"] == 2
    assert body["table_count"] == 2
    assert body["tables"][0]["rows"][0] == ["Region", "Q1", "Q2", "Q3", "Q4"]


def test_api_rejects_missing_file(client):
    resp = client.post("/api/extract", data={})
    assert resp.status_code == 400
