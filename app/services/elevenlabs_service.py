import hmac
import hashlib
from typing import Dict, Any, Optional, List
import requests
from flask import current_app, has_app_context
from app.config import Config


class ElevenLabsConfigError(Exception):
    """Raised when ElevenLabs credentials or settings are not properly configured."""
    pass


class ElevenLabsAPIError(Exception):
    """Raised when ElevenLabs API communication fails."""
    pass


class ElevenLabsService:
    """Manages secure communication, signed URL generation, and transcript retrieval with ElevenLabs."""

    BASE_URL = "https://api.elevenlabs.io/v1"

    def __init__(
        self,
        api_key: Optional[str] = None,
        agent_id: Optional[str] = None,
        auth_mode: Optional[str] = None
    ):
        cfg_key = current_app.config.get("ELEVENLABS_API_KEY") if has_app_context() else Config.ELEVENLABS_API_KEY
        cfg_agent = current_app.config.get("ELEVENLABS_AGENT_ID") if has_app_context() else Config.ELEVENLABS_AGENT_ID
        cfg_auth = current_app.config.get("ELEVENLABS_AUTH_MODE") if has_app_context() else Config.ELEVENLABS_AUTH_MODE

        self.api_key = api_key if api_key is not None else cfg_key
        self.agent_id = agent_id if agent_id is not None else cfg_agent
        self.auth_mode = (auth_mode if auth_mode is not None else cfg_auth or "signed_url").lower()

    def is_configured(self) -> bool:
        if self.auth_mode == "public":
            return bool(self.agent_id and not self.agent_id.startswith("your_"))
        return bool(
            self.api_key and not self.api_key.startswith("your_") and
            self.agent_id and not self.agent_id.startswith("your_")
        )

    def get_conversation_credentials(self, interview_id: str, candidate_name: str, job_title: str) -> Dict[str, Any]:
        """
        Generate temporary connection credentials for the client.
        Never returns ELEVENLABS_API_KEY.
        """
        if not self.is_configured():
            mode_desc = "Agent ID" if self.auth_mode == "public" else "API Key and Agent ID"
            raise ElevenLabsConfigError(
                f"ElevenLabs Conversational AI is not configured. Please supply a valid {mode_desc} "
                "in your .env file or environment variables."
            )

        dynamic_variables = {
            "interview_id": interview_id,
            "candidate_name": candidate_name,
            "job_title": job_title
        }

        # For public agent prototype mode
        if self.auth_mode == "public":
            return {
                "auth_mode": "public",
                "agent_id": self.agent_id,
                "dynamic_variables": dynamic_variables
            }

        # For authenticated signed_url mode
        signed_url = self._request_signed_url()
        return {
            "auth_mode": "signed_url",
            "signed_url": signed_url,
            "agent_id": self.agent_id,
            "dynamic_variables": dynamic_variables
        }

    def _request_signed_url(self) -> str:
        """Call ElevenLabs API to get a single-use signed WebSocket URL."""
        url = f"{self.BASE_URL}/convai/conversation/get_signed_url"
        headers = {
            "xi-api-key": self.api_key,
            "Accept": "application/json"
        }
        params = {"agent_id": self.agent_id}

        try:
            response = requests.get(url, headers=headers, params=params, timeout=12)
            if response.status_code == 401:
                raise ElevenLabsAPIError("Invalid ElevenLabs API key. Please check your credentials.")
            elif response.status_code == 404:
                raise ElevenLabsAPIError(f"ElevenLabs Agent with ID '{self.agent_id}' was not found.")
            elif not response.ok:
                raise ElevenLabsAPIError(
                    f"ElevenLabs API error ({response.status_code}): {response.text}"
                )

            data = response.json()
            signed_url = data.get("signed_url")
            if not signed_url:
                raise ElevenLabsAPIError("ElevenLabs did not return a signed_url in response.")
            return signed_url

        except requests.exceptions.Timeout:
            raise ElevenLabsAPIError("Request to ElevenLabs timed out. Please verify your network connection.")
        except requests.exceptions.RequestException as e:
            if isinstance(e, ElevenLabsAPIError):
                raise
            raise ElevenLabsAPIError(f"Failed to connect to ElevenLabs API: {str(e)}")

    def fetch_conversation_transcript(self, conversation_id: str) -> List[Dict[str, Any]]:
        """
        Retrieve complete conversation history and transcript from ElevenLabs API.
        URL: GET /v1/convai/conversations/{conversation_id}
        """
        if not self.api_key or self.api_key.startswith("your_"):
            raise ElevenLabsConfigError("ElevenLabs API Key is required to fetch conversation history.")

        url = f"{self.BASE_URL}/convai/conversations/{conversation_id}"
        headers = {
            "xi-api-key": self.api_key,
            "Accept": "application/json"
        }

        try:
            response = requests.get(url, headers=headers, timeout=15)
            if not response.ok:
                raise ElevenLabsAPIError(
                    f"Could not retrieve conversation history ({response.status_code}): {response.text}"
                )

            data = response.json()
            # ElevenLabs conversation response schema contains "transcript"
            raw_transcript = data.get("transcript", [])
            normalized_transcript = []

            for item in raw_transcript:
                role = item.get("role", "unknown")
                # Map role to candidate / agent
                mapped_role = "interviewer" if role in ("agent", "assistant") else "candidate"
                message = item.get("message", "") or item.get("text", "")
                time_in_call = item.get("time_in_call_secs", 0)
                if message.strip():
                    normalized_transcript.append({
                        "role": mapped_role,
                        "message": message.strip(),
                        "time_in_call_secs": time_in_call,
                    })

            return normalized_transcript

        except requests.exceptions.RequestException as e:
            raise ElevenLabsAPIError(f"Error fetching conversation transcript from ElevenLabs: {str(e)}")

    @staticmethod
    def verify_webhook_signature(payload: bytes, signature_header: str, secret: str) -> bool:
        """Verify HMAC SHA-256 signature on incoming webhooks from ElevenLabs."""
        if not secret:
            return True  # If no secret configured, bypass
        if not signature_header:
            return False
        expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature_header.strip())
