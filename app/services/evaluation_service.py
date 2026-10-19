import json
from pathlib import Path
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from app.models.interview import Interview, InterviewReport, InterviewStatus
from app.services.llm_service import LLMService
from app.services.transcript_service import TranscriptService
from app.extensions import db

PROMPT_FILE = Path(__file__).resolve().parent.parent / "prompts" / "evaluator.txt"


class CompetencyScoreItem(BaseModel):
    id: str
    name: str
    score: Optional[int] = Field(None, ge=0, le=5, description="Score 0 to 5, or None if Not Assessed")
    weight: int = Field(20, description="Percentage weight from the interview plan")
    rationale: str
    supporting_quote: Optional[str] = None
    improvement_recommendation: str


class EvaluationReportSchema(BaseModel):
    overall_summary: str
    overall_score: int = Field(..., ge=0, le=100)
    competency_scores: List[CompetencyScoreItem]
    strengths: List[str]
    improvement_areas: List[str]
    evidence: List[str]
    suggested_practice_questions: List[str]
    recommendations: List[str]
    assessment_limitations: str


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

        user_prompt = prompt_template.format(
            candidate_name=interview.candidate_name,
            competencies_json=json.dumps(competencies, indent=2),
            transcript_text=transcript_text[:10000],
            resume_text=(interview.resume_text or "")[:4000]
        )

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
