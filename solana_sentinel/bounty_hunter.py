"""Autonomous Bounty Hunter Engine for Solana and Web3 platforms.

Interacts with Superteam Earn Agent API, filters agent-eligible bounties,
evaluates viability using local 14B LLM, solves tasks, and notifies the operator.
"""
import json
import logging
import urllib.request
import urllib.error
from typing import Dict, Any, List, Optional
from pathlib import Path

from solana_sentinel.config import OLLAMA_MODEL, OPERATOR_TELEGRAM_ID
from solana_sentinel.analyzer.llm_client import LocalLLMClient

logger = logging.getLogger("solana_sentinel.bounty_hunter")

SUPERTEAM_BASE_URL = "https://superteam.fun"
AGENT_CREDENTIALS_FILE = Path(__file__).resolve().parent.parent / "superteam_agent.json"


class SuperteamClient:
    def __init__(self, credentials_path: Path = AGENT_CREDENTIALS_FILE):
        self.creds_path = credentials_path
        self.creds = self._load_or_register()

    def _load_or_register(self) -> Dict[str, Any]:
        """Load stored agent credentials or register a new agent on Superteam Earn."""
        if self.creds_path.exists():
            try:
                data = json.loads(self.creds_path.read_text())
                if data.get("apiKey"):
                    return data
            except Exception as e:
                logger.warning(f"Error reading {self.creds_path}: {e}")

        # Register new agent
        url = f"{SUPERTEAM_BASE_URL}/api/agents"
        req = urllib.request.Request(
            url,
            data=json.dumps({"name": "SolanaSentinelAgent"}).encode(),
            headers={"Content-Type": "application/json", "User-Agent": "SolanaSentinel/1.0"},
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                res = json.loads(r.read().decode())
                self.creds_path.write_text(json.dumps(res, indent=2))
                logger.info(f"Registered on Superteam Earn! AgentId: {res.get('agentId')}")
                return res
        except Exception as e:
            logger.error(f"Failed to register on Superteam Earn: {e}")
            return {}

    @property
    def api_key(self) -> str:
        return self.creds.get("apiKey", "")

    @property
    def claim_code(self) -> str:
        return self.creds.get("claimCode", "")

    def fetch_live_listings(self, take: int = 20) -> List[Dict[str, Any]]:
        """Fetch listings available for agents."""
        url = f"{SUPERTEAM_BASE_URL}/api/agents/listings/live?take={take}"
        headers = {
            "User-Agent": "SolanaSentinel/1.0",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            logger.error(f"Error fetching live listings: {e}")
            return []

    def fetch_listing_details(self, slug: str) -> Dict[str, Any]:
        """Fetch full listing details."""
        url = f"{SUPERTEAM_BASE_URL}/api/agents/listings/details/{slug}"
        headers = {
            "User-Agent": "SolanaSentinel/1.0",
            "Authorization": f"Bearer {self.api_key}",
        }
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            logger.error(f"Error fetching details for {slug}: {e}")
            return {}


class BountyHunter:
    def __init__(self, llm_client: Optional[LocalLLMClient] = None):
        self.superteam = SuperteamClient()
        self.llm = llm_client or LocalLLMClient()

    def scan_for_opportunities(self) -> List[Dict[str, Any]]:
        """Find active open bounties from Superteam Earn."""
        listings = []
        # 1. Try agent-specific listings
        try:
            agent_listings = self.superteam.fetch_live_listings(take=20)
            for item in agent_listings:
                if item.get("status") == "OPEN" and not item.get("isWinnersAnnounced"):
                    listings.append(item)
        except Exception as e:
            logger.warning(f"Error fetching agent listings: {e}")

        # 2. Also fetch public listings
        try:
            req = urllib.request.Request("https://earn.superteam.fun/api/listings", headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as r:
                public_listings = json.loads(r.read().decode())
                for item in public_listings:
                    if item.get("status") == "OPEN" and not item.get("isWinnersAnnounced"):
                        # Avoid duplicates
                        if not any(x.get("id") == item.get("id") for x in listings):
                            listings.append(item)
        except Exception as e:
            logger.warning(f"Error fetching public listings: {e}")

        logger.info(f"Found {len(listings)} open bounties on Superteam.")
        return listings

    def evaluate_bounty_viability(self, bounty: Dict[str, Any]) -> Dict[str, Any]:
        """Use local 14B LLM to evaluate if the bounty can be solved autonomously."""
        title = bounty.get("title", "")
        reward = f"{bounty.get('rewardAmount')} {bounty.get('token')}"
        bounty_type = bounty.get("type", "bounty")
        slug = bounty.get("slug", "")

        prompt = f"""You are an autonomous AI software engineer and bounty hunter.
Evaluate this Web3 bounty opportunity:
- Title: {title}
- Type: {bounty_type}
- Reward: {reward}
- Platform: Superteam Earn (Solana)

Can an AI agent write working code, documentation, scripts, or technical analysis to solve this?
Answer with a strict JSON format:
{{
  "is_viable": true/false,
  "confidence_score": 1-100,
  "task_category": "coding" | "writing" | "design" | "community" | "research",
  "reasoning": "brief explanation",
  "suggested_solution_plan": "brief 2-step plan"
}}
"""
        system = "You are a pragmatic, highly competent Web3 software engineer. Return only valid JSON."

        try:
            raw_response = self.llm.generate(prompt, system=system)
            # Clean JSON formatting from response
            cleaned = raw_response.strip()
            if "```json" in cleaned:
                cleaned = cleaned.split("```json")[1].split("```")[0].strip()
            elif "```" in cleaned:
                cleaned = cleaned.split("```")[1].split("```")[0].strip()
            eval_result = json.loads(cleaned)
            eval_result["bounty_id"] = bounty.get("id")
            eval_result["title"] = title
            eval_result["reward"] = reward
            eval_result["slug"] = slug
            return eval_result
        except Exception as e:
            logger.warning(f"Error evaluating bounty with LLM: {e}")
            # Fallback heuristic
            is_coding = any(k in title.lower() for k in ["code", "rust", "solana", "agent", "tool", "dapp", "repo", "audit", "build"])
            return {
                "is_viable": is_coding,
                "confidence_score": 75 if is_coding else 30,
                "task_category": "coding" if is_coding else "other",
                "reasoning": "Heuristic match on technical keywords.",
                "bounty_id": bounty.get("id"),
                "title": title,
                "reward": reward,
                "slug": slug,
            }

    def solve_bounty(self, bounty: Dict[str, Any], evaluation: Dict[str, Any]) -> str:
        """Produce technical solution or implementation with local Qwen 14B model."""
        title = bounty.get("title", "")
        plan = evaluation.get("suggested_solution_plan", "Implement production-ready solution.")

        prompt = f"""You are an expert Solana & Web3 engineer. Write the technical submission for this bounty:
Bounty: {title}
Reward: {evaluation.get('reward')}
Plan: {plan}

Produce complete, clean, working code, technical architecture, and documentation.
Explain the architecture, design choices, and how it directly meets the requirements.
"""
        return self.llm.generate(prompt, system="You are an elite autonomous developer. Deliver complete, production-grade technical code and solutions.")
