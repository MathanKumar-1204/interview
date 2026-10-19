import json
from pathlib import Path
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, model_validator
from app.models.interview import Interview, InterviewReport, InterviewStatus
from app.services.llm_service import LLMService
from app.services.transcript_service import TranscriptService
from app.extensions import db

PROMPT_FILE = Path(__file__).resolve().parent.parent / "prompts" / "evaluator.txt"


class CompetencyScoreItem(BaseModel):
    id: str = Field(default="")
    name: str = Field(default="Competency")
    score: Optional[int] = Field(None, ge=0, le=5, description="Score 0 to 5, or None if Not Assessed")
    weight: int = Field(20, description="Percentage weight from the interview plan")
    rationale: str = Field(default="")
    supporting_quote: Optional[str] = None
    improvement_recommendation: str = Field(default="")

    @model_validator(mode="before")
    @classmethod
    def handle_score_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if not data.get("id"):
                data["id"] = data.get("competency_id") or "comp"
            if not data.get("name"):
                data["name"] = data.get("title") or "Competency"
            if not data.get("rationale"):
                data["rationale"] = data.get("feedback") or data.get("assessment") or ""
            if not data.get("improvement_recommendation"):
                data["improvement_recommendation"] = data.get("recommendation") or data.get("improvement") or ""
        return data


class EvaluationReportSchema(BaseModel):
    overall_summary: str = Field(default="")
    overall_score: int = Field(default=0, ge=0, le=100)
    competency_scores: List[CompetencyScoreItem] = Field(default_factory=list)
    strengths: List[str] = Field(default_factory=list)
    improvement_areas: List[str] = Field(default_factory=list)
    evidence: List[str] = Field(default_factory=list)
    suggested_practice_questions: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    assessment_limitations: str = Field(default="")

    @model_validator(mode="before")
    @classmethod
    def extract_nested_report(cls, data: Any) -> Any:
        if isinstance(data, dict):
            for wrapper in ("evaluation_report", "report", "evaluation", "assessment"):
                if wrapper in data and isinstance(data[wrapper], dict) and len(data) <= 2:
                    sub = data[wrapper]
                    data = {**sub, **{k: v for k, v in data.items() if k != wrapper}}
            if not data.get("overall_summary") and data.get("summary"):
                data["overall_summary"] = data.get("summary")
            if not data.get("overall_score") and data.get("score") is not None:
                data["overall_score"] = int(data.get("score"))
            if not data.get("competency_scores") and data.get("competencies"):
                data["competency_scores"] = data.get("competencies")
        return data


class EvaluationService:
    """Evaluates interview transcripts against planned competencies and creates structured reports."""

    def __init__(self, llm_service: Optional[LLMService] = None):
        self.llm = llm_service or LLMService()

    @staticmethod
    def calculate_weighted_overall_score(competency_scores: List[CompetencyScoreItem]) -> int:
        """
        Calculate overall score strictly from assessed competency scores using explicit weights.
        Score = (sum((score / 5) * weight) / sum(assessed_weights)) * 100
        """
        assessed = [c for c in competency_scores if c.score is not None]
        if not assessed:
            return 0

        total_weight = sum(c.weight for c in assessed)
        if total_weight <= 0:
            total_weight = len(assessed) * 20

        weighted_points = sum((c.score / 5.0) * c.weight for c in assessed)
        overall = round((weighted_points / total_weight) * 100)
        return max(0, min(100, overall))

    def evaluate_interview(self, interview: Interview) -> InterviewReport:
        """
        Evaluate candidate performance and generate an InterviewReport.
        Idempotent: If report already exists, return it directly.
        """
        if interview.report:
            return interview.report

        # Validate transcript has sufficient substance
        TranscriptService.validate_transcript_for_evaluation(interview.transcript)

        with open(PROMPT_FILE, "r", encoding="utf-8") as f:
            prompt_template = f.read()

        plan = interview.interview_plan or {}
        competencies = plan.get("required_competencies", [])
        transcript_text = TranscriptService.format_transcript_as_text(interview.transcript)

        try:
            user_prompt = prompt_template.format(
                candidate_name=interview.candidate_name,
                competencies_json=json.dumps(competencies, indent=2),
                transcript_text=transcript_text[:10000],
                resume_text=(interview.resume_text or "")[:4000]
            )
        except (KeyError, IndexError, ValueError):
            user_prompt = prompt_template
            for placeholder, val in {
                "{candidate_name}": interview.candidate_name,
                "{competencies_json}": json.dumps(competencies, indent=2),
                "{transcript_text}": transcript_text[:10000],
                "{resume_text}": (interview.resume_text or "")[:4000]
            }.items():
                user_prompt = user_prompt.replace(placeholder, val)

        system_prompt = (
            "You are an objective hiring evaluator. "
            "You must score each competency on a 0-5 scale based strictly on the transcript evidence. "
            "Return valid JSON conforming to EvaluationReportSchema."
        )

        report_data = self.llm.generate_json(system_prompt, user_prompt, EvaluationReportSchema)

        # Re-verify and enforce mathematical overall score from assessed weights
        calculated_overall = self.calculate_weighted_overall_score(report_data.competency_scores)
        report_data.overall_score = calculated_overall

        # Create InterviewReport model
        report = InterviewReport(
            interview_id=interview.id,
            overall_score=report_data.overall_score,
            overall_summary=report_data.overall_summary,
            competency_scores=[c.model_dump() for c in report_data.competency_scores],
            strengths=report_data.strengths,
            improvement_areas=report_data.improvement_areas,
            evidence=report_data.evidence,
            suggested_practice_questions=report_data.suggested_practice_questions,
            recommendations=report_data.recommendations,
            assessment_limitations=report_data.assessment_limitations
        )

        db.session.add(report)
        interview.status = InterviewStatus.COMPLETED
        db.session.commit()
        return report
