from pathlib import Path
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field, field_validator, model_validator
from app.services.llm_service import LLMService

PROMPT_FILE = Path(__file__).resolve().parent.parent / "prompts" / "planner.txt"


class CompetencyItem(BaseModel):
    id: str = Field(default="", description="Unique slug for the competency e.g. 'content_strategy'")
    name: str = Field(default="Content Competency", description="Human-readable competency title")
    weight: int = Field(default=20, description="Weight percentage (e.g. 20 for 20%)")
    difficulty: str = Field("Intermediate", description="Beginner, Intermediate, Advanced")
    objective: str = Field(default="", description="What this competency aims to verify")
    expected_evidence: str = Field(default="", description="Tangible examples or behaviors looked for")

    @model_validator(mode="before")
    @classmethod
    def handle_competency_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if not data.get("id"):
                data["id"] = data.get("competency_id") or data.get("slug") or data.get("name", "comp").lower().replace(" ", "_")[:30]
            if not data.get("name"):
                data["name"] = data.get("title") or data.get("competency_name") or "Core Competency"
            if not data.get("objective"):
                data["objective"] = data.get("description") or data.get("goal") or "Assess candidate proficiency."
            if not data.get("expected_evidence"):
                data["expected_evidence"] = data.get("evidence") or data.get("criteria") or "Demonstrates clear capability."
            if not data.get("weight") or not isinstance(data.get("weight"), (int, float)):
                data["weight"] = 20
        return data


class QuestionItem(BaseModel):
    id: str = Field(default="q_1", description="Question identifier e.g. 'q_1'")
    question_text: str = Field(default="", description="The conversational spoken question")
    competency_id: str = Field(default="", description="Referenced competency id")
    expected_evidence: str = Field(default="", description="What constitutes an adequate answer")
    follow_up_guidance: str = Field(default="", description="How to probe if the candidate answer is vague")

    @model_validator(mode="before")
    @classmethod
    def handle_question_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if not data.get("id"):
                data["id"] = data.get("question_id") or "q_1"
            if not data.get("question_text"):
                data["question_text"] = data.get("question") or data.get("prompt") or data.get("text") or ""
            if not data.get("competency_id"):
                data["competency_id"] = data.get("competency") or ""
            if not data.get("expected_evidence"):
                data["expected_evidence"] = data.get("expected_response") or data.get("evaluation_criteria") or ""
            if not data.get("follow_up_guidance"):
                data["follow_up_guidance"] = data.get("follow_up") or data.get("probe") or ""
        return data


class InterviewSection(BaseModel):
    section_id: str = Field(default="section", description="Section slug e.g. 'resume_deep_dive'")
    title: str = Field(default="Section", description="Section title")
    target_duration_minutes: int = Field(default=3, description="Approximate time allocated")
    questions: List[QuestionItem] = Field(default_factory=list, description="Questions in this section")

    @model_validator(mode="before")
    @classmethod
    def handle_section_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if not data.get("section_id"):
                data["section_id"] = data.get("id") or data.get("slug") or "section"
            if not data.get("title"):
                data["title"] = data.get("name") or "Section"
            if not data.get("target_duration_minutes"):
                data["target_duration_minutes"] = data.get("duration_minutes") or data.get("duration") or 3
        return data


class InterviewPlanSchema(BaseModel):
    job_title: str = Field(default="Content Creator & Content Writer")
    responsibilities: List[str] = Field(default_factory=list)
    required_competencies: List[CompetencyItem] = Field(default_factory=list)
    resume_skills_found: List[str] = Field(default_factory=list)
    skill_gaps: List[str] = Field(default_factory=list)
    sections: List[InterviewSection] = Field(default_factory=list)
    conduct_guidelines: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def extract_nested_metadata(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # 1. Unnest top-level wrappers like {"interview_plan": {...}} or {"plan": {...}}
            for wrapper in ("interview_plan", "plan", "interview", "output", "data"):
                if wrapper in data and isinstance(data[wrapper], dict) and len(data) <= 2:
                    sub = data[wrapper]
                    data = {**sub, **{k: v for k, v in data.items() if k != wrapper}}

            # 2. Extract nested interview_metadata dictionary if present
            if "interview_metadata" in data and isinstance(data["interview_metadata"], dict):
                meta = data["interview_metadata"]
                for k, v in meta.items():
                    if k not in data or not data[k]:
                        data[k] = v

            # 3. Ensure job_title is populated from any synonym
            if not data.get("job_title"):
                data["job_title"] = (
                    data.get("title") or
                    data.get("role") or
                    data.get("position") or
                    data.get("target_role") or
                    "Content Creator & Content Writer"
                )

            # 4. Map potential alternate keys
            if not data.get("required_competencies") and data.get("competencies"):
                data["required_competencies"] = data["competencies"]
            if not data.get("sections") and data.get("interview_sections"):
                data["sections"] = data["interview_sections"]
            if not data.get("responsibilities") and data.get("key_responsibilities"):
                data["responsibilities"] = data["key_responsibilities"]
            if not data.get("resume_skills_found") and data.get("candidate_skills"):
                data["resume_skills_found"] = data["candidate_skills"]

        return data

    @field_validator("required_competencies")
    @classmethod
    def normalize_weights(cls, competencies: List[CompetencyItem]) -> List[CompetencyItem]:
        if not competencies:
            return competencies
        total = sum(c.weight for c in competencies)
        if total != 100 and total > 0:
            diff = 0
            for c in competencies:
                new_w = round((c.weight / total) * 100)
                c.weight = new_w
                diff += new_w
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
        with open(PROMPT_FILE, "r", encoding="utf-8") as f:
            prompt_template = f.read()

        try:
            user_prompt = prompt_template.format(
                candidate_name=candidate_name,
                duration_minutes=duration_minutes,
                difficulty=difficulty,
                language=language,
                resume_text=(resume_text or "")[:6000]
            )
        except (KeyError, IndexError, ValueError):
            user_prompt = prompt_template
            for placeholder, val in {
                "{candidate_name}": candidate_name,
                "{duration_minutes}": str(duration_minutes),
                "{difficulty}": difficulty,
                "{language}": language,
                "{resume_text}": (resume_text or "")[:6000]
            }.items():
                user_prompt = user_prompt.replace(placeholder, val)

        system_prompt = (
            "You are a specialized talent acquisition director and interview designer for Content Creators. "
            "Your output must strictly adhere to the InterviewPlanSchema structure in JSON format."
        )

        return self.llm.generate_json(system_prompt, user_prompt, InterviewPlanSchema)
