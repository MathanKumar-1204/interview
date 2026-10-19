import io
from app.models.interview import Interview, InterviewStatus
from unittest.mock import patch


def test_create_interview_success(client, sample_pdf_bytes):
    data = {
        "candidate_name": "Sarah Connor",
        "candidate_email": "sarah@example.com",
        "job_title": "Content Writer",
        "duration_minutes": "15",
        "difficulty": "Intermediate",
        "jd_text": "We are seeking a creative Content Writer to produce technical articles and social posts.",
        "resume_file": (io.BytesIO(sample_pdf_bytes), "sarah_resume.pdf")
    }

    response = client.post("/api/interviews", data=data, content_type="multipart/form-data")
    assert response.status_code == 201
    json_data = response.get_json()
    assert json_data["success"] is True
    assert "interview_id" in json_data


def test_create_interview_missing_resume_fails(client):
    data = {
        "candidate_name": "Sarah Connor",
        "job_title": "Content Writer",
        "jd_text": "Some JD text here"
    }
    response = client.post("/api/interviews", data=data, content_type="multipart/form-data")
    assert response.status_code == 400
    assert "resume file" in response.get_json()["error"].lower()


def test_create_interview_missing_candidate_name_fails(client, sample_pdf_bytes):
    data = {
        "candidate_name": "",
        "resume_file": (io.BytesIO(sample_pdf_bytes), "resume.pdf")
    }
    response = client.post("/api/interviews", data=data, content_type="multipart/form-data")
    assert response.status_code == 400
    assert "candidate name" in response.get_json()["error"].lower()


def test_create_interview_without_jd_succeeds(client, sample_pdf_bytes):
    data = {
        "candidate_name": "Maya Chen",
        "resume_file": (io.BytesIO(sample_pdf_bytes), "resume.pdf")
    }
    response = client.post("/api/interviews", data=data, content_type="multipart/form-data")
    assert response.status_code == 201
    assert response.get_json()["success"] is True


def test_prepare_interview(client, prepared_interview):
    # Test planning endpoint
    response = client.post(f"/api/interviews/{prepared_interview.id}/prepare")
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["status"] == InterviewStatus.PREPARED
    assert "plan" in data
    assert "required_competencies" in data["plan"]


def test_update_job_title(client, prepared_interview):
    response = client.post(
        f"/api/interviews/{prepared_interview.id}/update-title",
        json={"job_title": "Lead Editorial Strategist"}
    )
    assert response.status_code == 200
    assert response.get_json()["job_title"] == "Lead Editorial Strategist"


def test_get_interview_context(client, prepared_interview):
    response = client.get(f"/api/interviews/{prepared_interview.id}/context")
    assert response.status_code == 200
    data = response.get_json()
    assert data["candidate_name"] == prepared_interview.candidate_name
    assert "competencies" in data


def test_conversation_credentials_security(client, prepared_interview):
    with patch("app.services.elevenlabs_service.ElevenLabsService._request_signed_url") as mock_url:
        mock_url.return_value = "wss://api.elevenlabs.io/v1/convai/conversation?signed=mock_token"

        response = client.get(f"/api/interviews/{prepared_interview.id}/conversation-credentials")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "signed_url" in data
        assert "api_key" not in data  # Never expose server API keys!


def test_invalid_interview_id_returns_404(client):
    response = client.get("/api/interviews/non-existent-uuid-12345/status")
    assert response.status_code == 404
