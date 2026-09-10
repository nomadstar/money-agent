"""Solana Smart Contract (Rust / Anchor) Static and LLM Security Auditor."""
import re
import logging
from typing import Dict, Any, List, Optional
from solana_sentinel.analyzer.llm_client import LocalLLMClient

logger = logging.getLogger(__name__)


# Static vulnerability signatures for Solana Rust / Anchor programs
STATIC_CHECKS = [
    {
        "id": "SOL-001",
        "title": "Missing Signer Check / Raw AccountInfo",
        "severity": "CRITICAL",
        "pattern": r"(AccountInfo<'info>|AccountInfo\b)",
        "description": "Found raw AccountInfo without explicit Signer<'info> type. Ensure authorization and signer verification are enforced.",
    },
    {
        "id": "SOL-002",
        "title": "Unchecked Account Ownership",
        "severity": "HIGH",
        "pattern": r"(UncheckedAccount<'info>|/// CHECK:)",
        "description": "UncheckedAccount bypasses Anchor's automatic owner checks. Ensure strict manual account validation exists.",
    },
    {
        "id": "SOL-003",
        "title": "Potential Integer Overflow / Underflow",
        "severity": "MEDIUM",
        "pattern": r"(\b\w+\s*(\+|\-|\*)\s*\w+\b|\+\=|\-\=|\*\=)",
        "description": "Arithmetic operation without checked_add/sub/mul or saturating math, which can overflow or panic in release mode.",
    },
    {
        "id": "SOL-004",
        "title": "Arbitrary CPI (Cross-Program Invocation)",
        "severity": "CRITICAL",
        "pattern": r"(solana_program::program::invoke|invoke_signed)\s*\(",
        "description": "Direct invocation without verifying program_id. Attackers can substitute malicious programs unless strictly checked.",
    },
    {
        "id": "SOL-005",
        "title": "Missing PDA Canonical Bump Verification",
        "severity": "MEDIUM",
        "pattern": r"create_program_address\s*\(",
        "description": "create_program_address used instead of find_program_address. Non-canonical bump seeds can cause PDA collision vulnerabilities.",
    },
    {
        "id": "SOL-006",
        "title": "Account Closing / Reinitialization Risk",
        "severity": "HIGH",
        "pattern": r"(close\s*=\s*\w+|close_account)",
        "description": "Account closing detected. Ensure discriminator and data bytes are zeroed to prevent resurrection attacks.",
    },
]


class ContractAuditor:
    def __init__(self, llm_client: Optional[LocalLLMClient] = None):
        self.llm = llm_client or LocalLLMClient()

    def run_static_analysis(self, source_code: str) -> List[Dict[str, Any]]:
        findings = []
        lines = source_code.split("\n")
        for check in STATIC_CHECKS:
            regex = re.compile(check["pattern"], re.MULTILINE)
            for idx, line in enumerate(lines, 1):
                if regex.search(line):
                    findings.append({
                        "check_id": check["id"],
                        "title": check["title"],
                        "severity": check["severity"],
                        "line": idx,
                        "code_snippet": line.strip()[:100],
                        "description": check["description"],
                    })
        return findings

    def generate_audit_report(self, source_code: str) -> Dict[str, Any]:
        """Perform static scan and synthesize with LLM deep reasoning."""
        static_findings = self.run_static_analysis(source_code)

        static_summary = ""
        if static_findings:
            static_summary = "### Static Code Analysis Flags:\n"
            for f in static_findings:
                static_summary += f"- [{f['severity']}] Line {f['line']}: {f['title']} -> `{f['code_snippet']}`\n"
        else:
            static_summary = "No immediate static pattern anomalies detected."

        prompt = f"""You are a world-class Solana Smart Contract Security Auditor specializing in Rust and the Anchor Framework.
Analyze the following Solana program code for vulnerabilities, security flaws, and architectural risks.

Include in your audit:
1. **Executive Summary & Risk Score** (0 to 100, where 100 is perfectly secure).
2. **Vulnerability Breakdown**:
   - Title & Severity (CRITICAL, HIGH, MEDIUM, LOW, INFORMATIONAL)
   - Attack Scenario / Exploit Vector
   - Recommended Fix / Remediated Code
3. **Solana-Specific Checks Verified**:
   - Signer validation
   - Owner verification
   - Integer overflow protection
   - PDA bump derivation
   - Account closing / resurrection security
   - Reentrancy / CPI security

---
{static_summary}

---
### Source Code:
```rust
{source_code[:12000]}
```

Provide the audit report in clean GitHub-Flavored Markdown.
"""

        system_prompt = "You are an elite Solana and Rust security researcher. Produce clear, actionable, and precise smart contract audits."

        report_md = ""
        used_fallback = False
        try:
            if self.llm.is_available():
                report_md = self.llm.generate(prompt, system=system_prompt)
            else:
                used_fallback = True
        except Exception as e:
            logger.warning(f"Ollama inference error, using static report generator: {e}")
            used_fallback = True

        if used_fallback or not report_md.strip():
            report_md = self._build_fallback_report(source_code, static_findings)

        # Calculate high level risk score
        critical_count = sum(1 for f in static_findings if f["severity"] == "CRITICAL")
        high_count = sum(1 for f in static_findings if f["severity"] == "HIGH")
        medium_count = sum(1 for f in static_findings if f["severity"] == "MEDIUM")
        score = max(10, 100 - (critical_count * 35 + high_count * 20 + medium_count * 10))

        return {
            "score": score,
            "static_findings": static_findings,
            "report_markdown": report_md,
            "model_used": self.llm.model if not used_fallback else "static-engine",
        }

    def _build_fallback_report(self, code: str, findings: List[Dict[str, Any]]) -> str:
        lines = [
            "# Solana Smart Contract Security Audit",
            "**Auditor:** Solana Sentinel AI",
            "",
            "## 1. Executive Summary",
            f"- Total Anomalies Detected: {len(findings)}",
            f"- Critical: {sum(1 for f in findings if f['severity'] == 'CRITICAL')}",
            f"- High: {sum(1 for f in findings if f['severity'] == 'HIGH')}",
            f"- Medium: {sum(1 for f in findings if f['severity'] == 'MEDIUM')}",
            "",
            "## 2. Detailed Findings",
        ]
        if not findings:
            lines.append("No obvious vulnerability signatures were detected in the supplied code block.")
        for f in findings:
            lines.extend([
                f"### [{f['severity']}] {f['title']} (Line {f['line']})",
                f"**Snippet:** `{f['code_snippet']}`",
                f"**Description:** {f['description']}",
                "",
            ])
        lines.extend([
            "## 3. Best Practices Checklist for Solana / Anchor",
            "- [x] Always enforce `Signer<'info>` on authority accounts.",
            "- [x] Prefer `Account<'info, T>` over `UncheckedAccount<'info>`.",
            "- [x] Use `checked_add`, `checked_sub`, `checked_mul` for all arithmetic.",
            "- [x] Verify program IDs before invoking CPIs.",
            "- [x] Validate canonical PDA bump seeds on deserialization.",
        ])
        return "\n".join(lines)
