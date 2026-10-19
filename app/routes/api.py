from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, url_for, session
from app.models.interview import Interview, InterviewStatus, InterviewEvent
from app.services.document_parser import DocumentParserService, DocumentParsingError, ScannedDocumentError
from app.services.interview_planner import InterviewPlannerService
from app.services.elevenlabs_service import ElevenLabsService, ElevenLabsConfigError, ElevenLabsAPIError
from app.services.transcript_service import TranscriptService, TranscriptValidationError
from app.services.evaluation_service import EvaluationService
from app.services.llm_service import LLMConfigError, LLMExecutionError
from app.services.session_store import get_or_restore_interview
from app.extensions import db

api_bp = Blueprint("api", __name__, url_prefix="/api")


DEFAULT_CONTENT_CREATOR_JOB_TITLE = "Content Creator / Content Writer"
DEFAULT_CONTENT_CREATOR_JD = (
    "Role: Content Creator & Content Writer. Plan, write, and edit high-impact articles, "
    "social copy, and newsletters. Conduct audience search intent and keyword optimization. "
    "Maintain brand voice consistency and track engagement metrics."
)


@api_bp.route("/interviews", methods=["POST"])
def create_interview():
    """Create a new interview record from candidate resume and pre-configured Content Creator role."""
    candidate_name = request.form.get("candidate_name", "").strip()
    candidate_email = request.form.get("candidate_email", "").strip() or None
    job_title = request.form.get("job_title", "").strip() or DEFAULT_CONTENT_CREATOR_JOB_TITLE
    duration = int(request.form.get("duration_minutes", 15))
    difficulty = request.form.get("difficulty", "Intermediate").strip()
    language = request.form.get("language", "English").strip()

    if not candidate_name:
        return jsonify({"error": "Candidate name is required."}), 400

    resume_file = request.files.get("resume_file")
    if not resume_file or not resume_file.filename:
        return jsonify({"error": "Candidate resume file (PDF or DOCX) is required."}), 400

    # Validate & extract Resume
    valid_res, err_res = DocumentParserService.validate_file(resume_file)
    if not valid_res:
        return jsonify({"error": f"Resume file error: {err_res}"}), 400

    try:
        resume_text = DocumentParserService.extract_text(resume_file)
    except ScannedDocumentError as sde:
        return jsonify({"error": f"Resume error: {str(sde)}"}), 422
    except DocumentParsingError as dpe:
        return jsonify({"error": f"Resume extraction error: {str(dpe)}"}), 422

    # Job description: pre-configured Content Creator JD (or optional custom text if provided)
    jd_text_input = request.form.get("jd_text", "").strip()
    jd_file = request.files.get("jd_file")
    jd_text = DEFAULT_CONTENT_CREATOR_JD
    jd_filename = None

    if jd_file and jd_file.filename:
        valid_jd, err_jd = DocumentParserService.validate_file(jd_file)
        if valid_jd:
            try:
                extracted_jd = DocumentParserService.extract_text(jd_file)
                jd_filename = jd_file.filename
                jd_text = f"{jd_text_input}\n\n{extracted_jd}" if jd_text_input else extracted_jd
            except Exception:
                pass
    elif jd_text_input:
        jd_text = jd_text_input

    try:
        interview = Interview(
            candidate_name=candidate_name,
            candidate_email=candidate_email,
            job_title=job_title,
            jd_text=jd_text,
            resume_text=resume_text,
            jd_filename=jd_filename,
            resume_filename=resume_file.filename,
            duration_minutes=duration,
            difficulty=difficulty,
            language=language,
            status=InterviewStatus.DRAFT
        )
        db.session.add(interview)
        db.session.commit()

        # Log creation event
        event = InterviewEvent(
            interview_id=interview.id,
            event_type="interview_created",
            event_data={"candidate_name": candidate_name, "job_title": job_title}
        )
        db.session.add(event)
        db.session.commit()

        session["active_interview"] = {
            "id": interview.id,
            "interview_id": interview.id,
            "candidate_name": candidate_name,
            "candidate_email": candidate_email,
            "job_title": job_title,
            "duration_minutes": duration,
            "difficulty": difficulty,
            "language": language,
            "status": interview.status
        }
        session.modified = True

        return jsonify({
            "success": True,
            "interview_id": interview.id,
            "interview": session["active_interview"],
            "redirect_url": url_for("interviews.view_preparation", interview_id=interview.id)
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Database error creating interview: {str(e)}"}), 500


@api_bp.route("/interviews/<interview_id>/prepare", methods=["POST"])
def prepare_interview(interview_id: str):
    """Generate structured interview plan from JD and Resume using the LLM."""
    interview = get_or_restore_interview(interview_id)
    if not interview:
        return jsonify({"error": "Interview not found."}), 404

    # Allow re-planning if in draft or prepared
    planner = InterviewPlannerService()
    try:
        plan_schema = planner.generate_plan(
            candidate_name=interview.candidate_name,
            job_title=interview.job_title,
            jd_text=interview.jd_text,
            resume_text=interview.resume_text,
            duration_minutes=interview.duration_minutes,
            difficulty=interview.difficulty,
            language=interview.language
        )

        plan_dict = plan_schema.model_dump()
        interview.interview_plan = plan_dict
        interview.job_title = plan_dict.get("job_title", interview.job_title)
        interview.status = InterviewStatus.PREPARED
        interview.error_message = None

        event = InterviewEvent(
            interview_id=interview.id,
            event_type="plan_generated",
            event_data={"competencies_count": len(plan_dict.get("required_competencies", []))}
        )
        db.session.add(event)
        db.session.commit()

        session["active_interview"] = {
            "id": interview.id,
            "interview_id": interview.id,
            "candidate_name": interview.candidate_name,
            "candidate_email": interview.candidate_email,
            "job_title": interview.job_title,
            "duration_minutes": interview.duration_minutes,
            "difficulty": interview.difficulty,
            "language": interview.language,
            "interview_plan": plan_dict,
            "status": interview.status
        }
        session.modified = True

        return jsonify({
            "success": True,
            "status": interview.status,
            "plan": plan_dict,
            "interview": session["active_interview"]
        })

    except LLMConfigError as lce:
        interview.error_message = str(lce)
        db.session.commit()
        return jsonify({"error": str(lce)}), 503
    except (LLMExecutionError, Exception) as ee:
        interview.error_message = f"Interview planning failed: {str(ee)}"
        db.session.commit()
        return jsonify({"error": f"Planning failed: {str(ee)}"}), 500


@api_bp.route("/interviews/<interview_id>/update-title", methods=["POST"])
def update_job_title(interview_id: str):
    """Update job title during preparation."""
    interview = get_or_restore_interview(interview_id)
    if not interview:
        return jsonify({"error": "Interview not found."}), 404

    new_title = request.json.get("job_title", "").strip() if request.is_json else request.form.get("job_title", "").strip()
    if not new_title:
        return jsonify({"error": "Job title cannot be empty."}), 400

    interview.job_title = new_title
    if interview.interview_plan:
        plan = dict(interview.interview_plan)
        plan["job_title"] = new_title
        interview.interview_plan = plan

    db.session.commit()
    if "active_interview" in session and session["active_interview"].get("id") == interview.id:
        session["active_interview"]["job_title"] = new_title
        session.modified = True

    return jsonify({"success": True, "job_title": interview.job_title})


@api_bp.route("/interviews/<interview_id>/conversation-credentials", methods=["GET"])
def get_conversation_credentials(interview_id: str):
    """
    Secure endpoint providing ephemeral credentials or signed WebSocket URL for ElevenLabs.
    Never returns ELEVENLABS_API_KEY.
    """
    interview = get_or_restore_interview(interview_id)
    if not interview:
        return jsonify({"error": "Interview not found."}), 404

    if interview.status not in (InterviewStatus.PREPARED, InterviewStatus.IN_PROGRESS):
        return jsonify({
            "error": f"Interview is in '{interview.status}' status and cannot be started. Please prepare the interview first."
        }), 400

    service = ElevenLabsService()
    try:
        credentials = service.get_conversation_credentials(
            interview_id=interview.id,
            candidate_name=interview.candidate_name,
            job_title=interview.job_title
        )

        # Mark interview in progress and set started_at if not set
        if interview.status != InterviewStatus.IN_PROGRESS:
            interview.status = InterviewStatus.IN_PROGRESS
            interview.started_at = datetime.now(timezone.utc)
            db.session.commit()

        return jsonify({"success": True, **credentials})

    except ElevenLabsConfigError as ece:
        return jsonify({"error": str(ece)}), 503
    except ElevenLabsAPIError as eae:
        return jsonify({"error": f"ElevenLabs connection failure: {str(eae)}"}), 502
    except Exception as e:
        return jsonify({"error": f"Failed to initialize conversation: {str(e)}"}), 500


@api_bp.route("/interviews/<interview_id>/context", methods=["GET"])
def get_interview_context(interview_id: str):
    """
    Protected endpoint for ElevenLabs agent tool call / context retrieval.
    Supplies the agent with role requirements, candidate background summary, and planned sections.
    """
    interview = get_or_restore_interview(interview_id)
    if not interview:
        return jsonify({"error": "Interview not found."}), 404

    plan = interview.interview_plan or {}
    return jsonify({
        "interview_id": interview.id,
        "candidate_name": interview.candidate_name,
        "job_title": interview.job_title,
        "difficulty": interview.difficulty,
        "duration_minutes": interview.duration_minutes,
        "competencies": plan.get("required_competencies", []),
        "planned_sections": plan.get("sections", []),
        "resume_highlights": plan.get("resume_skills_found", []),
        "conduct_guidelines": plan.get("conduct_guidelines", "")
    })


@api_bp.route("/interviews/<interview_id>/transcript", methods=["POST"])
def sync_transcript(interview_id: str):
    """Client-side transcript synchronization."""
    interview = get_or_restore_interview(interview_id)
    if not interview:
        return jsonify({"error": "Interview not found."}), 404

    data = request.get_json(silent=True) or {}
    turns = data.get("transcript", [])
    conversation_id = data.get("conversation_id")

    if conversation_id:
        interview.elevenlabs_conversation_id = conversation_id

    if turns and isinstance(turns, list):
        interview.transcript = turns

    db.session.commit()
    return jsonify({"success": True, "turns_count": len(interview.transcript or [])})


@api_bp.route("/interviews/<interview_id>/end", methods=["POST"])
def end_interview(interview_id: str):
    """Record that the interview session has ended."""
    interview = get_or_restore_interview(interview_id)
    if not interview:
        return jsonify({"error": "Interview not found."}), 404

    data = request.get_json(silent=True) or {}
    reason = data.get("reason", "normal")
    conversation_id = data.get("conversation_id")

    if conversation_id:
        interview.elevenlabs_conversation_id = conversation_id

    if reason == "interrupted":
        interview.status = InterviewStatus.INTERRUPTED
    else:
        interview.status = InterviewStatus.AWAITING_FINALIZATION

    event = InterviewEvent(
        interview_id=interview.id,
        event_type="interview_ended",
        event_data={"reason": reason, "conversation_id": conversation_id}
    )
    db.session.add(event)
    db.session.commit()

    return jsonify({"success": True, "status": interview.status})


@api_bp.route("/interviews/<interview_id>/finalize", methods=["POST"])
def finalize_interview(interview_id: str):
    """
    Idempotent finalization endpoint:
    1. Ingests transcript from ElevenLabs API or client payload.
    2. Runs EvaluationService against rubric.
    3. Persists InterviewReport and marks COMPLETED.
    """
    interview = get_or_restore_interview(interview_id)
    if not interview:
        return jsonify({"error": "Interview not found."}), 404

    # Idempotent return if already completed with report
    if interview.status == InterviewStatus.COMPLETED and interview.report:
        return jsonify({
            "success": True,
            "status": interview.status,
            "report_url": url_for("reports.view_report", interview_id=interview.id)
        })

    data = request.get_json(silent=True) or {}
    conv_id = data.get("conversation_id") or interview.elevenlabs_conversation_id
    client_turns = data.get("transcript")

    # Sync transcript
    ts_service = TranscriptService()
    ts_service.sync_transcript(interview, conversation_id=conv_id, client_transcript=client_turns)

    # Evaluate
    eval_service = EvaluationService()
    try:
        report = eval_service.evaluate_interview(interview)
        interview.completed_at = datetime.now(timezone.utc)
        interview.status = InterviewStatus.COMPLETED
        interview.error_message = None
        db.session.commit()

        session["active_report"] = report.to_dict()
        session.modified = True

        return jsonify({
            "success": True,
            "status": interview.status,
            "overall_score": report.overall_score,
            "report_url": url_for("reports.view_report", interview_id=interview.id)
        })

    except TranscriptValidationError as tve:
        interview.status = InterviewStatus.INTERRUPTED
        interview.error_message = str(tve)
        db.session.commit()
        return jsonify({"error": str(tve)}), 422

    except LLMConfigError as lce:
        interview.error_message = str(lce)
        db.session.commit()
        return jsonify({"error": str(lce)}), 503

    except (LLMExecutionError, Exception) as e:
        interview.error_message = f"Evaluation failed: {str(e)}"
        db.session.commit()
        return jsonify({"error": f"Evaluation processing error: {str(e)}"}), 500


@api_bp.route("/interviews/<interview_id>/webhook", methods=["POST"])
def elevenlabs_webhook(interview_id: str):
    """
    Optional post-call webhook receiver from ElevenLabs Conversational AI.
    """
    interview = db.session.get(Interview, interview_id)
    if not interview:
        return jsonify({"error": "Interview not found."}), 404

    payload = request.get_data()
    sig = request.headers.get("xi-signature", "")
    from app.config import Config
    if not ElevenLabsService.verify_webhook_signature(payload, sig, Config.ELEVENLABS_WEBHOOK_SECRET):
        return jsonify({"error": "Invalid webhook signature."}), 401

    data = request.get_json(silent=True) or {}
    transcript_data = data.get("transcript", [])
    if transcript_data:
        ts_service = TranscriptService()
        ts_service.sync_transcript(interview, client_transcript=transcript_data)

    return jsonify({"received": True})


@api_bp.route("/interviews/<interview_id>/status", methods=["GET"])
def get_interview_status(interview_id: str):
    """Check current interview status."""
    interview = db.session.get(Interview, interview_id)
    if not interview:
        return jsonify({"error": "Interview not found."}), 404

    return jsonify(interview.to_dict())


@api_bp.route("/interviews/<interview_id>", methods=["DELETE"])
def delete_interview(interview_id: str):
    """Delete an interview and all associated records."""
    interview = db.session.get(Interview, interview_id)
    if not interview:
        return jsonify({"error": "Interview not found."}), 404

    db.session.delete(interview)
    db.session.commit()
    return jsonify({"success": True, "message": "Interview deleted successfully."})


@api_bp.route("/interviews/restore", methods=["POST"])
def restore_interview():
    """Endpoint allowing client to restore interview state into an ephemeral serverless container."""
    data = request.get_json(silent=True) or {}
    interview_id = data.get("interview_id") or data.get("id")
    if not interview_id:
        return jsonify({"error": "interview_id is required."}), 400

    existing = db.session.get(Interview, interview_id)
    if existing:
        return jsonify({"success": True, "restored": False, "status": existing.status})

    try:
        restored = Interview(
            id=interview_id,
            candidate_name=data.get("candidate_name", "Candidate"),
            candidate_email=data.get("candidate_email"),
            job_title=data.get("job_title", DEFAULT_CONTENT_CREATOR_JOB_TITLE),
            jd_text=data.get("jd_text", DEFAULT_CONTENT_CREATOR_JD),
            resume_text=data.get("resume_text", ""),
            duration_minutes=int(data.get("duration_minutes", 15)),
            difficulty=data.get("difficulty", "Intermediate"),
            language=data.get("language", "English"),
            interview_plan=data.get("interview_plan"),
            transcript=data.get("transcript", []),
            status=data.get("status", InterviewStatus.PREPARED)
        )
        db.session.add(restored)
        db.session.commit()

        session["active_interview"] = {
            "id": restored.id,
            "interview_id": restored.id,
            "candidate_name": restored.candidate_name,
            "candidate_email": restored.candidate_email,
            "job_title": restored.job_title,
            "duration_minutes": restored.duration_minutes,
            "difficulty": restored.difficulty,
            "language": restored.language,
            "interview_plan": restored.interview_plan,
            "status": restored.status
        }
        session.modified = True

        return jsonify({"success": True, "restored": True, "status": restored.status})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Failed to restore interview: {str(e)}"}), 500

