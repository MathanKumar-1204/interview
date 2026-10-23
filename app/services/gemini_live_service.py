"""
Gemini Flash Live Voice Interviewer Service
Drives real-time conversational voice interview sessions powered by Google Gemini Flash.
"""
import json
import re
from typing import Dict, Any, List, Optional
from flask import current_app, has_app_context
from app.models.interview import Interview
from app.services.llm_service import LLMService, LLMExecutionError
from app.config import Config


def extract_clean_speech(text: str) -> str:
    """Ensure the response is pure spoken dialogue, stripping any accidental JSON wrapping or quotes."""
    if not text:
        return ""
    cleaned = text.strip()
    # Strip markdown code blocks
    if "```" in cleaned:
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        cleaned = cleaned.strip()

    # If the model wrapped the response in a JSON object like {"response": "..."}
    if (cleaned.startswith("{") and cleaned.endswith("}")) or '"response"' in cleaned:
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                for key in ("response", "message", "text", "content", "answer", "speech"):
                    if key in parsed and isinstance(parsed[key], str):
                        return parsed[key].strip()
                for val in parsed.values():
                    if isinstance(val, str):
                        return val.strip()
        except Exception:
            # Fallback regex extraction if json.loads failed
            m = re.search(r'"(?:response|message|text|content|answer)"\s*:\s*"([^"]+)"', cleaned)
            if m:
                return m.group(1).replace(r'\"', '"').strip()

    # Strip outer quotes if entire text is quoted
    if (cleaned.startswith('"') and cleaned.endswith('"')) or (cleaned.startswith("'") and cleaned.endswith("'")):
        cleaned = cleaned[1:-1].strip()

    return cleaned


class GeminiLiveService:
    """Manages conversational dialogue turns for the Gemini Flash Live voice engine."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        cfg_provider = current_app.config.get("LLM_PROVIDER") if has_app_context() else Config.LLM_PROVIDER
        provider = "mock" if cfg_provider == "mock" else "gemini"
        self.llm = LLMService(provider=provider, api_key=api_key, model=model or "gemini-3.8-flash")

    def build_system_instruction(self, interview: Interview) -> str:
        """Construct the prompt guiding Alex during Gemini Flash Live voice assessment."""
        plan = interview.interview_plan or {}
        competencies = plan.get("required_competencies", [])
        sections = plan.get("sections", [])
        
        comp_summary = "\n".join([
            f"- {c.get('name', 'Competency')}: {c.get('objective', '')} (Evidence sought: {c.get('expected_evidence', '')})"
            for c in competencies
        ]) or "Core role competencies, problem solving, communication craft, and practical experience."

        sections_summary = "\n".join([
            f"- {s.get('title', 'Section')}: target {s.get('target_duration_minutes', 3)} mins"
            for s in sections
        ])

        return (
            f"You are Alex, an expert, conversational, warm, and encouraging AI voice interviewer conducting a live spoken interview "
            f"with {interview.candidate_name} for the {interview.job_title} role.\n\n"
            f"CRITICAL SPOKEN VOICE GUIDELINES:\n"
            f"1. You are speaking aloud directly to the candidate. Output ONLY plain, conversational English dialogue.\n"
            f"2. NEVER output JSON, curly braces, code blocks, or markdown formatting.\n"
            f"3. Keep each turn short, engaging, and natural (2 to 3 sentences maximum).\n"
            f"4. Ask only ONE focused question per turn. Never dump multiple questions.\n"
            f"5. First acknowledge what the candidate said with an encouraging or insightful remark, then ask your next question.\n"
            f"6. If the candidate's answer is brief or vague, probe deeper for a specific metric, project, or concrete example.\n"
            f"7. Maintain a professional yet friendly, encouraging conversational rhythm.\n\n"
            f"EVALUATION COMPETENCIES TO COVER:\n{comp_summary}\n\n"
            f"INTERVIEW STRUCTURE:\n{sections_summary}\n\n"
            f"Candidate: {interview.candidate_name} applying for {interview.job_title}."
        )

    def get_initial_greeting(self, interview: Interview) -> Dict[str, Any]:
        """Generate the opening greeting message for the interview."""
        return {
            "role": "interviewer",
            "message": (
                f"Hello {interview.candidate_name}! Welcome to your spoken interview for the {interview.job_title} role. "
                f"I am Alex, your AI interviewer powered by Gemini Flash Live. To get started, could you please introduce yourself "
                f"and share what interests you most about this position?"
            ),
            "engine": "gemini_live"
        }

    def process_turn(
        self,
        interview: Interview,
        candidate_message: str,
        conversation_history: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Generate Alex's conversational follow-up response given the candidate's speech and dialogue history."""
        system_instruction = self.build_system_instruction(interview)

        # Build chronological dialogue history formatted for the model
        history_lines = []
        for turn in conversation_history[-10:]:  # Keep recent context window
            speaker = "Candidate" if turn.get("role") in ("candidate", "user") else "Alex (Interviewer)"
            history_lines.append(f"{speaker}: {extract_clean_speech(turn.get('message', ''))}")

        history_context = "\n".join(history_lines) if history_lines else "None (Start of conversation)"

        user_prompt = (
            f"--- Previous Conversation Turns ---\n"
            f"{history_context}\n\n"
            f"--- Candidate's Latest Spoken Answer ---\n"
            f"Candidate: {candidate_message}\n\n"
            f"Alex, give your next spoken response. Remember: acknowledge their answer, stay under 3 sentences, ask your next question, and speak in plain English with NO JSON."
        )

        try:
            # Call Gemini directly with json_mode=False for conversational speech
            raw_response = self.llm._call_gemini(system_instruction, user_prompt, json_mode=False)
            clean_response = extract_clean_speech(raw_response)
            if not clean_response:
                clean_response = f"Thank you for sharing that, {interview.candidate_name}. Could you describe a challenging project in this domain and how you navigated it?"

            return {
                "role": "interviewer",
                "message": clean_response,
                "engine": "gemini_live"
            }
        except Exception as e:
            # Fallback response so the interview is never abruptly broken
            return {
                "role": "interviewer",
                "message": f"Thank you for sharing that, {interview.candidate_name}. Could you elaborate on a key project where you had to tailor your strategy to achieve high measurable impact?",
                "engine": "gemini_live",
                "error": str(e)
            }
