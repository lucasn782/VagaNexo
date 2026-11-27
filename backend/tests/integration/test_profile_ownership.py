from __future__ import annotations

import uuid
from pathlib import Path

import pymupdf
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.routes.resume_documents import get_resume_storage
from app.auth.dependencies import get_rate_limiter
from app.auth.rate_limit import InMemoryRateLimiter
from app.auth.service import AuthService
from app.database.dependencies import get_db
from app.main import app
from app.models.candidate_profile import CandidateProfile
from app.resume_import.storage import ResumeStorage


def _pdf_bytes(text: str) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def _login_new_client(
    db_session: Session,
    email: str,
    password: str,
    limiter: InMemoryRateLimiter,
) -> TestClient:
    AuthService(db_session, rate_limiter=limiter).create_user(email=email, password=password)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_rate_limiter] = lambda: limiter
    client = TestClient(app)
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    client.headers.update({"X-CSRF-Token": resp.json()["csrf_token"]})
    return client


def test_all_protected_routes_deny_unauthenticated_and_cross_user_access(
    db_session: Session,
    tmp_path: Path,
) -> None:
    storage = ResumeStorage(tmp_path)
    limiter = InMemoryRateLimiter(max_attempts=50, window_seconds=300)
    app.dependency_overrides[get_resume_storage] = lambda: storage

    try:
        client_a = _login_new_client(db_session, "user-a@example.com", "PasswordA123!", limiter)
        client_b = _login_new_client(db_session, "user-b@example.com", "PasswordB123!", limiter)
        anon_client = TestClient(app)

        # Create a legacy unowned profile directly in DB
        legacy_profile = CandidateProfile(full_name="Legacy Unowned")
        db_session.add(legacy_profile)
        db_session.commit()
        db_session.refresh(legacy_profile)

        # Client-supplied user_id is rejected by schema (extra="forbid")
        forged_resp = client_a.post(
            "/api/v1/profiles",
            json={"full_name": "User A Profile", "user_id": str(uuid.uuid4())},
        )
        assert forged_resp.status_code == 422

        # User A creates profile A legitimately
        prof_a_resp = client_a.post(
            "/api/v1/profiles",
            json={"full_name": "User A Profile"},
        )
        assert prof_a_resp.status_code == 201
        profile_a_id = prof_a_resp.json()["id"]

        # User B creates profile B + child records + uploaded resume
        prof_b_resp = client_b.post("/api/v1/profiles", json={"full_name": "User B Profile"})
        assert prof_b_resp.status_code == 201
        profile_b_id = prof_b_resp.json()["id"]

        edu_b = client_b.post(
            f"/api/v1/profiles/{profile_b_id}/educations",
            json={
                "institution": "USP",
                "degree": "CS",
                "start_date": "2020-01-01",
                "is_current": True,
            },
        ).json()["id"]
        exp_b = client_b.post(
            f"/api/v1/profiles/{profile_b_id}/experiences",
            json={
                "company": "Acme",
                "job_title": "Dev",
                "employment_type": "full_time",
                "start_date": "2021-01-01",
                "is_current": True,
            },
        ).json()["id"]
        skill_b = client_b.post(
            f"/api/v1/profiles/{profile_b_id}/skills",
            json={"name": "Python", "category": "technical", "proficiency_level": "advanced"},
        ).json()["id"]
        cert_b = client_b.post(
            f"/api/v1/profiles/{profile_b_id}/certifications",
            json={"name": "AWS", "issuing_organization": "Amazon"},
        ).json()["id"]
        lang_b = client_b.post(
            f"/api/v1/profiles/{profile_b_id}/languages",
            json={"language": "English", "proficiency_level": "fluent"},
        ).json()["id"]
        proj_b = client_b.post(
            f"/api/v1/profiles/{profile_b_id}/projects",
            json={"name": "VagaNexo", "project_type": "personal"},
        ).json()["id"]
        upload_b = client_b.post(
            f"/api/v1/profiles/{profile_b_id}/resume-documents/upload",
            files={"file": ("bruno.pdf", _pdf_bytes("Bruno Secret Resume"), "application/pdf")},
        )
        assert upload_b.status_code == 201
        doc_b_id = upload_b.json()["id"]

        # Listing returns only own profiles (never B's or legacy)
        list_a = client_a.get("/api/v1/profiles").json()
        assert [p["id"] for p in list_a] == [profile_a_id]

        # Complete matrix of protected routes:
        # 1) Unauthenticated -> 401
        # 2) User A targeting User B -> 404
        # 3) User A targeting legacy unowned profile -> 404
        b_routes: list[tuple[str, str, dict[str, object] | None]] = [
            ("GET", "/api/v1/profiles", None),
            ("POST", "/api/v1/profiles", {"full_name": "Anon"}),
            ("GET", f"/api/v1/profiles/{profile_b_id}", None),
            ("PATCH", f"/api/v1/profiles/{profile_b_id}", {"full_name": "Hacked"}),
            ("GET", f"/api/v1/profiles/{profile_b_id}/educations", None),
            (
                "POST",
                f"/api/v1/profiles/{profile_b_id}/educations",
                {"institution": "X", "degree": "Y", "start_date": "2020-01-01"},
            ),
            (
                "PATCH",
                f"/api/v1/profiles/{profile_b_id}/educations/{edu_b}",
                {"institution": "Hacked"},
            ),
            ("DELETE", f"/api/v1/profiles/{profile_b_id}/educations/{edu_b}", None),
            ("GET", f"/api/v1/profiles/{profile_b_id}/experiences", None),
            (
                "POST",
                f"/api/v1/profiles/{profile_b_id}/experiences",
                {
                    "company": "X",
                    "job_title": "Y",
                    "employment_type": "full_time",
                    "start_date": "2020-01-01",
                },
            ),
            (
                "PATCH",
                f"/api/v1/profiles/{profile_b_id}/experiences/{exp_b}",
                {"company": "Hacked"},
            ),
            ("DELETE", f"/api/v1/profiles/{profile_b_id}/experiences/{exp_b}", None),
            ("GET", f"/api/v1/profiles/{profile_b_id}/skills", None),
            (
                "POST",
                f"/api/v1/profiles/{profile_b_id}/skills",
                {"name": "Go", "category": "technical", "proficiency_level": "beginner"},
            ),
            ("PATCH", f"/api/v1/profiles/{profile_b_id}/skills/{skill_b}", {"name": "Hacked"}),
            ("DELETE", f"/api/v1/profiles/{profile_b_id}/skills/{skill_b}", None),
            ("GET", f"/api/v1/profiles/{profile_b_id}/certifications", None),
            (
                "POST",
                f"/api/v1/profiles/{profile_b_id}/certifications",
                {"name": "X", "issuing_organization": "Y"},
            ),
            (
                "PATCH",
                f"/api/v1/profiles/{profile_b_id}/certifications/{cert_b}",
                {"name": "Hacked"},
            ),
            ("DELETE", f"/api/v1/profiles/{profile_b_id}/certifications/{cert_b}", None),
            ("GET", f"/api/v1/profiles/{profile_b_id}/languages", None),
            (
                "POST",
                f"/api/v1/profiles/{profile_b_id}/languages",
                {"language": "French", "proficiency_level": "basic"},
            ),
            (
                "PATCH",
                f"/api/v1/profiles/{profile_b_id}/languages/{lang_b}",
                {"language": "Hacked"},
            ),
            ("DELETE", f"/api/v1/profiles/{profile_b_id}/languages/{lang_b}", None),
            ("GET", f"/api/v1/profiles/{profile_b_id}/projects", None),
            (
                "POST",
                f"/api/v1/profiles/{profile_b_id}/projects",
                {"name": "X", "project_type": "personal"},
            ),
            ("PATCH", f"/api/v1/profiles/{profile_b_id}/projects/{proj_b}", {"name": "Hacked"}),
            ("DELETE", f"/api/v1/profiles/{profile_b_id}/projects/{proj_b}", None),
            ("GET", f"/api/v1/profiles/{profile_b_id}/preferences", None),
            ("PUT", f"/api/v1/profiles/{profile_b_id}/preferences", {"target_roles": ["Dev"]}),
            ("POST", f"/api/v1/profiles/{profile_b_id}/validation/skills/{skill_b}/confirm", None),
            ("POST", f"/api/v1/profiles/{profile_b_id}/validation/skills/{skill_b}/reject", None),
            ("GET", f"/api/v1/profiles/{profile_b_id}/resume-documents", None),
            (
                "POST",
                f"/api/v1/profiles/{profile_b_id}/resume-documents",
                {
                    "original_filename": "x.pdf",
                    "media_type": "application/pdf",
                    "file_size": 10,
                    "sha256_hash": "a" * 64,
                    "storage_key": f"uploads/{profile_b_id}/x.pdf",
                },
            ),
            ("GET", f"/api/v1/profiles/{profile_b_id}/resume-documents/{doc_b_id}", None),
            (
                "GET",
                f"/api/v1/profiles/{profile_b_id}/resume-documents/{doc_b_id}/extraction",
                None,
            ),
            (
                "PATCH",
                f"/api/v1/profiles/{profile_b_id}/resume-documents/{doc_b_id}",
                {"original_filename": "hacked.pdf"},
            ),
            ("DELETE", f"/api/v1/profiles/{profile_b_id}/resume-documents/{doc_b_id}", None),
        ]

        for method, url, json_body in b_routes:
            anon_resp = anon_client.request(method, url, json=json_body)
            assert anon_resp.status_code == 401, f"Anon {method} {url} -> {anon_resp.status_code}"

            if url != "/api/v1/profiles":
                cross_resp = client_a.request(method, url, json=json_body)
                assert cross_resp.status_code == 404, (
                    f"Cross {method} {url} -> {cross_resp.status_code}"
                )

        # Upload route also blocked for unauthenticated and cross-user
        assert (
            anon_client.post(
                f"/api/v1/profiles/{profile_b_id}/resume-documents/upload",
                files={"file": ("a.pdf", _pdf_bytes("A"), "application/pdf")},
            ).status_code
            == 401
        )
        assert (
            client_a.post(
                f"/api/v1/profiles/{profile_b_id}/resume-documents/upload",
                files={"file": ("a.pdf", _pdf_bytes("A"), "application/pdf")},
            ).status_code
            == 404
        )

        # Unowned legacy profile is inaccessible to User A and User B
        assert client_a.get(f"/api/v1/profiles/{legacy_profile.id}").status_code == 404
        assert client_b.get(f"/api/v1/profiles/{legacy_profile.id}").status_code == 404

        # Verify User B's data & extraction remain completely intact
        b_detail = client_b.get(f"/api/v1/profiles/{profile_b_id}").json()
        assert b_detail["full_name"] == "User B Profile"
        assert len(b_detail["educations"]) == 1
        assert len(b_detail["resume_documents"]) == 1
        b_ext = client_b.get(
            f"/api/v1/profiles/{profile_b_id}/resume-documents/{doc_b_id}/extraction"
        )
        assert b_ext.status_code == 200
        assert "Bruno Secret Resume" in b_ext.json()["extracted_text"]
    finally:
        app.dependency_overrides.clear()
