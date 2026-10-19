from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator
from app.services.llm_service import LLMService

PROMPT_FILE = Path(__file__).resolve().parent.parent / "prompts" / "planner.txt"


class CompetencyItem(BaseModel):
    id: str = Field(..., description="Unique slug for the competency e.g. 'content_strategy'")
    name: str = Field(..., description="Human-readable competency title")
    weight: int = Field(..., description="Weight percentage (e.g. 20 for 20%)")
    difficulty: str = Field("Intermediate", description="Beginner, Intermediate, Advanced")
    objective: str = Field(..., description="What this competency aims to verify")
    expected_evidence: str = Field(..., description="Tangible examples or behaviors looked for")


class QuestionItem(BaseModel):
    id: str = Field(..., description="Question identifier e.g. 'q_1'")
    question_text: str = Field(..., description="The conversational spoken question")
    competency_id: str = Field(..., description="Referenced competency id")
    expected_evidence: str = Field(..., description="What constitutes an adequate answer")
    follow_up_guidance: str = Field(..., description="How to probe if the candidate answer is vague")


class InterviewSection(BaseModel):
    section_id: str = Field(..., description="Section slug e.g. 'resume_deep_dive'")
    title: str = Field(..., description="Section title")
    target_duration_minutes: int = Field(..., description="Approximate time allocated")
    questions: List[QuestionItem] = Field(default_factory=list, description="Questions in this section")


class InterviewPlanSchema(BaseModel):
    job_title: str
    responsibilities: List[str] = Field(default_factory=list)
    required_competencies: List[CompetencyItem] = Field(default_factory=list)
    resume_skills_found: List[str] = Field(default_factory=list)
    skill_gaps: List[str] = Field(default_factory=list)
    sections: List[InterviewSection] = Field(default_factory=list)
    conduct_guidelines: Optional[str] = None

    @field_validator("required_competencies")
    @classmethod
    def normalize_weights(cls, competencies: List[CompetencyItem]) -> List[CompetencyItem]:
        if not competencies:
            return competencies
        total = sum(c.weight for c in competencies)
        if total != 100 and total > 0:
            # Adjust weights proportionally so they sum to 100
            diff = 0
            for i, c in enumerate(competencies):
                new_w = round((c.weight / total) * 100)
                c.weight = new_w
                diff += new_w
            # Fix rounding remainder on first item
            competencies[0].weight += (100 - diff)
        return competencies


class InterviewPlannerService:
    """Generates structured, competency-based interview plans using the LLM."""

    def __init__(self, llm_service: Optional[LLMService] = None):
        self.llm = llm_service or LLMService()

    def generate_plan(
        self,
        candidate_name: str,
        job_title: str = "Content Creator / Content Writer",
        jd_text: str = "",
        resume_text: str = "",
        duration_minutes: int = 15,
        difficulty: str = "Intermediate",
        language: str = "English"
    ) -> InterviewPlanSchema:
        """Create structured interview plan tailored to Content Creator role and candidate resume."""
        with open(PROMPT_FILE, "r", encoding="utf-8") as f:
            prompt_template = f.read()

        user_prompt = prompt_template.format(
            candidate_name=candidate_name,
            duration_minutes=duration_minutes,
            difficulty=difficulty,
            language=language,
            resume_text=(resume_text or "")[:6000]
        )

        system_prompt = (
            "You are a specialized talent acquisition director and interview designer for Content Creators. "
            "Your output must strictly adhere to the InterviewPlanSchema structure in JSON format."
        )

        return self.llm.generate_json(system_prompt, user_prompt, InterviewPlanSchema)
