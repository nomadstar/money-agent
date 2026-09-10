"""Solana Token / Memecoin Risk Scanner and Rug-Check Engine."""
import logging
from typing import Dict, Any, List, Optional
from solana_sentinel.rpc_client import SolanaRPCClient
from solana_sentinel.analyzer.llm_client import LocalLLMClient

logger = logging.getLogger(__name__)


class TokenScanner:
    def __init__(
        self,
        rpc_client: Optional[SolanaRPCClient] = None,
        llm_client: Optional[LocalLLMClient] = None,
    ):
        self.rpc = rpc_client or SolanaRPCClient()
        self.llm = llm_client or LocalLLMClient()

    def scan_mint(self, mint_address: str) -> Dict[str, Any]:
        """Fetch on-chain parameters and evaluate rug-pull / security risks."""
        info = self.rpc.get_account_info(mint_address)
        if not info:
            raise ValueError(f"Mint address {mint_address} not found on Solana network.")

        data = info.get("data", {})
        parsed = data.get("parsed", {}) if isinstance(data, dict) else {}
        token_info = parsed.get("info", {})

        decimals = token_info.get("decimals", 9)
        supply_raw = int(token_info.get("supply", 0))
        supply = supply_raw / (10 ** decimals) if decimals else supply_raw

        mint_authority = token_info.get("mintAuthority")
        freeze_authority = token_info.get("freezeAuthority")

        # Fetch largest accounts with rate-limit tolerance
        top_holders = []
        top_10_sum = 0
        top_10_concentration = 0
        try:
            largest = self.rpc.get_token_largest_accounts(mint_address)
            for item in largest[:10]:
                amt = float(item.get("uiAmount", 0) or 0)
                top_10_sum += amt
                top_holders.append({
                    "address": item.get("address"),
                    "amount": amt,
                    "percentage": round((amt / supply * 100), 2) if supply > 0 else 0,
                })
            top_10_concentration = round((top_10_sum / supply * 100), 2) if supply > 0 else 0
        except Exception as e:
            logger.warning(f"Could not fetch top holders (RPC rate-limit or error): {e}")

        # Risk scoring
        red_flags = []
        if mint_authority is not None:
            red_flags.append({
                "severity": "CRITICAL",
                "title": "Mint Authority Not Revoked",
                "detail": f"Creator/Owner ({mint_authority}) can mint unlimited new tokens, potentially dumping on holders.",
            })

        if freeze_authority is not None:
            red_flags.append({
                "severity": "CRITICAL",
                "title": "Freeze Authority Active (Honeypot Risk)",
                "detail": f"Creator/Owner ({freeze_authority}) has the power to freeze user accounts and prevent selling.",
            })

        if top_10_concentration > 50:
            red_flags.append({
                "severity": "HIGH",
                "title": f"High Whale Concentration ({top_10_concentration}%)",
                "detail": "Top 10 holders control more than 50% of the circulating supply.",
            })
        elif top_10_concentration > 30:
            red_flags.append({
                "severity": "MEDIUM",
                "title": f"Moderate Concentration ({top_10_concentration}%)",
                "detail": "Top 10 holders control over 30% of supply.",
            })

        risk_score = 100
        for flag in red_flags:
            if flag["severity"] == "CRITICAL":
                risk_score -= 40
            elif flag["severity"] == "HIGH":
                risk_score -= 20
            elif flag["severity"] == "MEDIUM":
                risk_score -= 10
        risk_score = max(5, risk_score)

        verdict = "SAFE"
        if risk_score < 40:
            verdict = "EXTREME_RISK_RUGPULL"
        elif risk_score < 70:
            verdict = "WARNING_HIGH_RISK"

        # LLM Synthesis
        summary_prompt = f"""You are a Solana on-chain analyst. Analyze this Solana token scan:
Mint: {mint_address}
Supply: {supply:,.2f}
Mint Authority: {'REVOKED (Safe)' if mint_authority is None else f'ACTIVE: {mint_authority} (DANGEROUS)'}
Freeze Authority: {'REVOKED (Safe)' if freeze_authority is None else f'ACTIVE: {freeze_authority} (HONEYPOT RISK)'}
Top 10 Holders Share: {top_10_concentration}%
Calculated Risk Score: {risk_score}/100 ({verdict})

Write a concise 3-paragraph executive summary:
1. Verdict and immediate safety summary
2. Breakdown of the red flags and holder distribution
3. Clear recommendation for crypto traders.
"""
        llm_summary = ""
        try:
            if self.llm.is_available():
                llm_summary = self.llm.generate(summary_prompt)
        except Exception as e:
            logger.warning(f"Ollama inference error during token scan: {e}")

        if not llm_summary.strip():
            llm_summary = f"**Verdict:** {verdict} (Score: {risk_score}/100).\n\n"
            if red_flags:
                llm_summary += "Identified risks:\n" + "\n".join([f"- {f['title']}: {f['detail']}" for f in red_flags])
            else:
                llm_summary += "Mint and freeze authorities are revoked. Holder distribution within normal parameters."

        return {
            "mint": mint_address,
            "supply": supply,
            "decimals": decimals,
            "mint_authority": mint_authority,
            "freeze_authority": freeze_authority,
            "top_10_concentration": top_10_concentration,
            "top_holders": top_holders,
            "red_flags": red_flags,
            "risk_score": risk_score,
            "verdict": verdict,
            "summary_markdown": llm_summary,
        }
