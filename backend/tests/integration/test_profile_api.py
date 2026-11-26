from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

API = "/api/v1/profiles"


def create_profile(client: TestClient, payload: dict[str, object]) -> dict[str, Any]:
    response = client.post(API, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_health_endpoint_is_preserved(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "application": "VagaNexo AI"}


def test_profile_lifecycle(client: TestClient, profile_payload: dict[str, object]) -> None:
    profile = create_profile(client, profile_payload)
    assert profile["full_name"] == "Ana Souza"
    assert profile["educations"] == []
    assert profile["preferences"] is None

    profile_id = profile["id"]
    response = client.get(f"{API}/{profile_id}")
    assert response.status_code == 200
    assert response.json()["email"] == "ana.souza@example.com"

    response = client.patch(
        f"{API}/{profile_id}",
        json={"professional_headline": "Senior Backend Engineer"},
    )
    assert response.status_code == 200
    assert response.json()["professional_headline"] == "Senior Backend Engineer"


def test_profile_not_found(client: TestClient) -> None:
    response = client.get(f"{API}/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
    assert response.json()["detail"] == "profile not found"


def test_profile_validation_error(client: TestClient) -> None:
    response = client.post(API, json={"full_name": ""})
    assert response.status_code == 422


def test_education_crud(client: TestClient, profile_payload: dict[str, object]) -> None:
    profile_id = create_profile(client, profile_payload)["id"]
    payload = {
        "institution": "USP",
        "degree": "Ciencia da Computacao",
        "start_date": "2018-02-01",
        "end_date": "2022-12-15",
    }
    response = client.post(f"{API}/{profile_id}/educations", json=payload)
    assert response.status_code == 201, response.text
    education = response.json()
    assert education["validation_status"] == "confirmed"
    assert education["source_type"] == "manual"

    response = client.get(f"{API}/{profile_id}/educations")
    assert response.status_code == 200
    assert len(response.json()) == 1

    response = client.patch(
        f"{API}/{profile_id}/educations/{education['id']}",
        json={"degree": "Bacharelado em Ciencia da Computacao"},
    )
    assert response.status_code == 200
    assert response.json()["degree"] == "Bacharelado em Ciencia da Computacao"

    response = client.delete(f"{API}/{profile_id}/educations/{education['id']}")
    assert response.status_code == 204
    assert client.get(f"{API}/{profile_id}/educations").json() == []


def test_education_invalid_dates_are_rejected(
    client: TestClient,
    profile_payload: dict[str, object],
) -> None:
    profile_id = create_profile(client, profile_payload)["id"]
    response = client.post(
        f"{API}/{profile_id}/educations",
        json={
            "institution": "USP",
            "degree": "Computacao",
            "start_date": "2022-01-01",
            "end_date": "2021-01-01",
        },
    )
    assert response.status_code == 422


def test_experience_crud(client: TestClient, profile_payload: dict[str, object]) -> None:
    profile_id = create_profile(client, profile_payload)["id"]
    payload = {
        "company": "VagaNexo",
        "job_title": "Backend Engineer",
        "employment_type": "full_time",
        "start_date": "2024-01-01",
        "achievements": ["Built the profile engine"],
    }
    response = client.post(f"{API}/{profile_id}/experiences", json=payload)
    assert response.status_code == 201, response.text
    experience = response.json()
    assert experience["achievements"] == ["Built the profile engine"]

    response = client.patch(
        f"{API}/{profile_id}/experiences/{experience['id']}",
        json={"is_current": True},
    )
    assert response.status_code == 200
    assert response.json()["is_current"] is True

    response = client.delete(f"{API}/{profile_id}/experiences/{experience['id']}")
    assert response.status_code == 204


def test_skill_crud_and_duplicate_conflict(
    client: TestClient,
    profile_payload: dict[str, object],
) -> None:
    profile_id = create_profile(client, profile_payload)["id"]
    response = client.post(
        f"{API}/{profile_id}/skills",
        json={"name": "Python", "category": "technical", "proficiency_level": "advanced"},
    )
    assert response.status_code == 201, response.text
    skill = response.json()
    assert skill["normalized_name"] == "python"

    duplicate = client.post(f"{API}/{profile_id}/skills", json={"name": "python"})
    assert duplicate.status_code == 409

    response = client.patch(
        f"{API}/{profile_id}/skills/{skill['id']}",
        json={"years_experience": 5},
    )
    assert response.status_code == 200
    assert response.json()["years_experience"] == 5

    response = client.delete(f"{API}/{profile_id}/skills/{skill['id']}")
    assert response.status_code == 204


def test_certification_language_and_project(
    client: TestClient,
    profile_payload: dict[str, object],
) -> None:
    profile_id = create_profile(client, profile_payload)["id"]

    certification = client.post(
        f"{API}/{profile_id}/certifications",
        json={
            "name": "AWS Solutions Architect",
            "issuing_organization": "Amazon Web Services",
            "credential_url": "https://example.com/credential",
        },
    )
    assert certification.status_code == 201, certification.text

    language = client.post(
        f"{API}/{profile_id}/languages",
        json={
            "language": "Ingles",
            "proficiency_level": "advanced",
            "proficiency_framework": "cefr",
            "cefr_level": "C1",
        },
    )
    assert language.status_code == 201, language.text
    assert language.json()["cefr_level"] == "C1"

    project = client.post(
        f"{API}/{profile_id}/projects",
        json={
            "name": "VagaNexo",
            "project_type": "personal",
            "technologies": ["Python", "FastAPI", "PostgreSQL"],
        },
    )
    assert project.status_code == 201, project.text
    assert project.json()["project_type"] == "personal"

    assert len(client.get(f"{API}/{profile_id}/certifications").json()) == 1
    assert len(client.get(f"{API}/{profile_id}/languages").json()) == 1
    assert len(client.get(f"{API}/{profile_id}/projects").json()) == 1


def test_preferences_upsert(client: TestClient, profile_payload: dict[str, object]) -> None:
    profile_id = create_profile(client, profile_payload)["id"]

    response = client.get(f"{API}/{profile_id}/preferences")
    assert response.status_code == 404

    response = client.put(
        f"{API}/{profile_id}/preferences",
        json={
            "preferred_job_titles": ["Backend Engineer"],
            "preferred_locations": ["Sao Paulo"],
            "work_modes": ["remote", "hybrid"],
            "employment_types": ["full_time"],
            "minimum_salary": 8000,
            "maximum_salary": 15000,
            "salary_currency": "brl",
            "willingness_to_relocate": True,
            "preferred_seniority": "senior",
        },
    )
    assert response.status_code == 200, response.text
    preferences = response.json()
    assert preferences["salary_currency"] == "BRL"
    assert preferences["work_modes"] == ["remote", "hybrid"]

    response = client.put(
        f"{API}/{profile_id}/preferences",
        json={"minimum_salary": 9000},
    )
    assert response.status_code == 200
    assert response.json()["minimum_salary"] == 9000
    assert response.json()["maximum_salary"] == 15000


def test_resume_document_metadata(client: TestClient, profile_payload: dict[str, object]) -> None:
    profile_id = create_profile(client, profile_payload)["id"]
    payload = {
        "original_filename": "curriculo.pdf",
        "media_type": "application/pdf",
        "file_size": 4096,
        "sha256_hash": "d" * 64,
        "storage_key": "uploads/curriculo.pdf",
    }
    response = client.post(f"{API}/{profile_id}/resume-documents", json=payload)
    assert response.status_code == 201, response.text
    document = response.json()
    assert document["parsing_status"] == "pending"

    response = client.get(f"{API}/{profile_id}/resume-documents")
    assert response.status_code == 200
    assert len(response.json()) == 1

    response = client.get(f"{API}/{profile_id}/resume-documents/{document['id']}")
    assert response.status_code == 200

    response = client.patch(
        f"{API}/{profile_id}/resume-documents/{document['id']}",
        json={"parsing_status": "parsed"},
    )
    assert response.status_code == 200
    assert response.json()["parsing_status"] == "parsed"

    response = client.delete(f"{API}/{profile_id}/resume-documents/{document['id']}")
    assert response.status_code == 204


def test_validation_confirmation_flow(
    client: TestClient,
    profile_payload: dict[str, object],
) -> None:
    profile_id = create_profile(client, profile_payload)["id"]
    response = client.post(
        f"{API}/{profile_id}/skills",
        json={
            "name": "Rust",
            "source_type": "ai",
            "confidence_score": 0.42,
        },
    )
    assert response.status_code == 201, response.text
    skill = response.json()
    assert skill["validation_status"] == "pending"

    response = client.post(f"{API}/{profile_id}/validation/skills/{skill['id']}/confirm")
    assert response.status_code == 200
    assert response.json()["validation_status"] == "confirmed"

    response = client.post(f"{API}/{profile_id}/validation/skills/{skill['id']}/reject")
    assert response.status_code == 200
    assert response.json()["validation_status"] == "rejected"


def test_records_cannot_be_accessed_from_another_profile(
    client: TestClient,
    profile_payload: dict[str, object],
) -> None:
    first = create_profile(client, profile_payload)["id"]
    second_payload = dict(profile_payload)
    second_payload["full_name"] = "Bruno Lima"
    second_payload["email"] = "bruno.lima@example.com"
    second = create_profile(client, second_payload)["id"]

    response = client.post(
        f"{API}/{first}/projects",
        json={"name": "Projeto privado"},
    )
    assert response.status_code == 201
    project_id = response.json()["id"]

    response = client.patch(
        f"{API}/{second}/projects/{project_id}",
        json={"name": "Alterado"},
    )
    assert response.status_code == 404

    response = client.delete(f"{API}/{second}/projects/{project_id}")
    assert response.status_code == 404


def test_profile_response_contains_nested_records(
    client: TestClient,
    profile_payload: dict[str, object],
) -> None:
    profile_id = create_profile(client, profile_payload)["id"]
    client.post(
        f"{API}/{profile_id}/skills",
        json={"name": "Python"},
    )
    client.put(
        f"{API}/{profile_id}/preferences",
        json={"work_modes": ["remote"]},
    )

    response = client.get(f"{API}/{profile_id}")
    assert response.status_code == 200
    body = response.json()
    assert len(body["skills"]) == 1
    assert body["preferences"]["work_modes"] == ["remote"]
