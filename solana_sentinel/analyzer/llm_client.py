"""Ollama and Local LLM inference client with streaming and fallback."""
import json
import logging
import urllib.request
import urllib.error
from typing import Dict, Any, Generator, Optional
from solana_sentinel.config import OLLAMA_BASE_URL, OLLAMA_MODEL, LLM_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)


class LocalLLMClient:
    def __init__(self, base_url: str = OLLAMA_BASE_URL, model: str = OLLAMA_MODEL):
        self.base_url = base_url.rstrip("/")
        self.model = model

    def is_available(self) -> bool:
        """Check if local Ollama daemon is reachable."""
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                models = [m.get("name") for m in data.get("models", [])]
                logger.info(f"Ollama reachable. Available models: {models}")
                return True
        except Exception as e:
            logger.debug(f"Ollama check failed: {e}")
            return False

    def generate(self, prompt: str, system: Optional[str] = None) -> str:
        """Generate full completion synchronously."""
        url = f"{self.base_url}/api/generate"
        payload: Dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.2,
                "num_ctx": 4096,
            },
        }
        if system:
            payload["system"] = system

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=LLM_TIMEOUT_SECONDS) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                return res.get("response", "")
        except urllib.error.URLError as e:
            logger.error(f"Local LLM generation failed: {e}")
            raise RuntimeError(f"Ollama generation failed ({self.model} at {self.base_url}): {e}")

    def generate_stream(self, prompt: str, system: Optional[str] = None) -> Generator[str, None, None]:
        """Stream response tokens from Ollama."""
        url = f"{self.base_url}/api/generate"
        payload: Dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": 0.2,
                "num_ctx": 16384,
            },
        }
        if system:
            payload["system"] = system

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=LLM_TIMEOUT_SECONDS) as resp:
                for line in resp:
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line.decode("utf-8"))
                        text = chunk.get("response", "")
                        if text:
                            yield text
                        if chunk.get("done", False):
                            break
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.error(f"Streaming error from Ollama: {e}")
            raise
