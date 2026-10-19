from flask import Blueprint, render_template
from app.models.interview import Interview, InterviewStatus
from app.config import Config

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
def index():
    """Home / Dashboard view."""
    interviews = Interview.query.order_by(Interview.created_at.desc()).all()
    
    # Calculate quick dashboard stats
    total_count = len(interviews)
    completed_count = sum(1 for i in interviews if i.status == InterviewStatus.COMPLETED)
    in_progress_count = sum(1 for i in interviews if i.status == InterviewStatus.IN_PROGRESS)
    
    scores = [i.report.overall_score for i in interviews if i.report and i.report.overall_score is not None]
    avg_score = round(sum(scores) / len(scores)) if scores else 0

    elevenlabs_ready = Config.is_elevenlabs_configured()
    llm_ready = Config.is_llm_configured()

    return render_template(
        "dashboard.html",
        interviews=interviews,
        total_count=total_count,
        completed_count=completed_count,
        in_progress_count=in_progress_count,
        avg_score=avg_score,
        elevenlabs_ready=elevenlabs_ready,
        llm_ready=llm_ready,
        InterviewStatus=InterviewStatus
    )
