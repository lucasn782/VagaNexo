from __future__ import annotations

import io
import uuid
from pathlib import Path

import docx
import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.api.routes.resume_documents import get_resume_storage
from app.main import app
from app.resume_import.storage import ResumeStorage


def _pdf_bytes(text: str) -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    if text:
        page.insert_text((72, 72), text)
    data = document.tobytes()
    document.close()
    return data


def _docx_bytes(text: str) -> bytes:
    buffer = io.BytesIO()
    document = docx.Document()
    document.add_paragraph(text)
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Skill"
    table.cell(0, 1).text = "PostgreSQL"
    document.save(buffer)
    return buffer.getvalue()


@pytest.fixture()
def isolated_storage(tmp_path: Path) -> ResumeStorage:
    storage = ResumeStorage(tmp_path)
    app.dependency_overrides[get_resume_storage] = lambda: storage
    try:
        yield storage
    finally:
        app.dependency_overrides.pop(get_resume_storage, None)


def _create_profile(client: TestClient, payload: dict[str, object]) -> str:
    response = client.post("/api/v1/profiles", json=payload)
    assert response.status_code == 201
    return str(response.json()["id"])


def test_upload_list_read_extract_and_delete_pdf_and_docx(
    client: TestClient,
    profile_payload: dict[str, object],
    isolated_storage: ResumeStorage,
) -> None:
    profile_id = _create_profile(client, profile_payload)

    pdf_response = client.post(
        f"/api/v1/profiles/{profile_id}/resume-documents/upload",
        files={"file": ("curriculo.pdf", _pdf_bytes("Ana Souza\nPython"), "application/pdf")},
    )
    assert pdf_response.status_code == 201
    pdf_body = pdf_response.json()
    assert pdf_body["original_filename"] == "curriculo.pdf"
    assert pdf_body["parsing_status"] == "completed"
    assert pdf_body["page_count"] == 1
    assert pdf_body["word_count"] >= 2
    assert pdf_body["warnings"] == []
    pdf_id = pdf_body["id"]

    docx_response = client.post(
        f"/api/v1/profiles/{profile_id}/resume-documents/upload",
        files={
            "file": (
                "curriculo.docx",
                _docx_bytes("Experiência com FastAPI e São Paulo"),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert docx_response.status_code == 201
    docx_id = docx_response.json()["id"]

    list_response = client.get(f"/api/v1/profiles/{profile_id}/resume-documents")
    assert list_response.status_code == 200
    listed = list_response.json()
    assert len(listed) == 2
    for item in listed:
        assert "extracted_text" not in item

    detail_response = client.get(f"/api/v1/profiles/{profile_id}/resume-documents/{pdf_id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["extraction"]["page_count"] == 1
    assert "extracted_text" not in detail["extraction"]

    extraction_response = client.get(
        f"/api/v1/profiles/{profile_id}/resume-documents/{docx_id}/extraction"
    )
    assert extraction_response.status_code == 200
    extraction_body = extraction_response.json()
    assert "Experiência com FastAPI e São Paulo" in extraction_body["extracted_text"]
    assert "Skill | PostgreSQL" in extraction_body["extracted_text"]

    storage_key = next(item["storage_key"] for item in listed if item["id"] == pdf_id)
    assert isolated_storage.exists(storage_key)

    delete_response = client.delete(f"/api/v1/profiles/{profile_id}/resume-documents/{pdf_id}")
    assert delete_response.status_code == 204
    assert not isolated_storage.exists(storage_key)

    after_delete = client.get(f"/api/v1/profiles/{profile_id}/resume-documents/{pdf_id}")
    assert after_delete.status_code == 404


def test_upload_rejects_duplicate_invalid_and_oversized_files(
    client: TestClient,
    profile_payload: dict[str, object],
    isolated_storage: ResumeStorage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile_id = _create_profile(client, profile_payload)
    other_id = _create_profile(client, {**profile_payload, "full_name": "Bruno Lima"})
    pdf_data = _pdf_bytes("Unique Resume Content")

    first = client.post(
        f"/api/v1/profiles/{profile_id}/resume-documents/upload",
        files={"file": ("cv.pdf", pdf_data, "application/pdf")},
    )
    assert first.status_code == 201
    doc_id = first.json()["id"]

    duplicate = client.post(
        f"/api/v1/profiles/{profile_id}/resume-documents/upload",
        files={"file": ("cv_copy.pdf", pdf_data, "application/pdf")},
    )
    assert duplicate.status_code == 409

    other_profile = client.post(
        f"/api/v1/profiles/{other_id}/resume-documents/upload",
        files={"file": ("cv.pdf", pdf_data, "application/pdf")},
    )
    assert other_profile.status_code == 201

    # Cross-profile isolation
    assert client.get(f"/api/v1/profiles/{other_id}/resume-documents/{doc_id}").status_code == 404
    assert (
        client.get(f"/api/v1/profiles/{other_id}/resume-documents/{doc_id}/extraction").status_code
        == 404
    )
    assert (
        client.delete(f"/api/v1/profiles/{other_id}/resume-documents/{doc_id}").status_code == 404
    )

    # Non-existent profile / document
    missing_profile = uuid.uuid4()
    assert (
        client.post(
            f"/api/v1/profiles/{missing_profile}/resume-documents/upload",
            files={"file": ("cv.pdf", pdf_data, "application/pdf")},
        ).status_code
        == 404
    )

    # Invalid file (empty / bad extension / bad content)
    assert (
        client.post(
            f"/api/v1/profiles/{profile_id}/resume-documents/upload",
            files={"file": ("empty.pdf", b"", "application/pdf")},
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/v1/profiles/{profile_id}/resume-documents/upload",
            files={"file": ("notes.txt", b"hello", "text/plain")},
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/v1/profiles/{profile_id}/resume-documents/upload",
            files={"file": ("fake.pdf", b"not-a-pdf", "application/pdf")},
        ).status_code
        == 422
    )

    # Oversized file -> 413
    from app.core import config

    settings = config.get_settings()
    monkeypatch.setattr(settings, "max_resume_upload_bytes", 100)
    oversized = client.post(
        f"/api/v1/profiles/{profile_id}/resume-documents/upload",
        files={"file": ("big.pdf", _pdf_bytes("A" * 200), "application/pdf")},
    )
    assert oversized.status_code == 413


def test_deleting_resume_preserves_provenance_on_profile_facts(
    client: TestClient,
    profile_payload: dict[str, object],
    isolated_storage: ResumeStorage,
) -> None:
    profile_id = _create_profile(client, profile_payload)
    upload = client.post(
        f"/api/v1/profiles/{profile_id}/resume-documents/upload",
        files={"file": ("cv.pdf", _pdf_bytes("Python Developer"), "application/pdf")},
    )
    assert upload.status_code == 201
    document_id = upload.json()["id"]

    skill = client.post(
        f"/api/v1/profiles/{profile_id}/skills",
        json={
            "name": "Python",
            "source_type": "document",
            "source_document_id": document_id,
        },
    )
    assert skill.status_code == 201
    assert skill.json()["validation_status"] == "pending"
    skill_id = skill.json()["id"]

    delete_res = client.delete(f"/api/v1/profiles/{profile_id}/resume-documents/{document_id}")
    assert delete_res.status_code == 204

    skills = client.get(f"/api/v1/profiles/{profile_id}/skills").json()
    preserved = next(item for item in skills if item["id"] == skill_id)
    assert preserved["source_document_id"] is None
    assert preserved["source_type"] == "document"
