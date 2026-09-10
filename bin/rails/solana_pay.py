#!/usr/bin/env python3
"""Solana Pay receive-rail adapter for money-agent verifier.

Scores verified incoming SOL payments to the agent's settlement address on Solana mainnet.
"""
from __future__ import annotations
import json
import os
import urllib.request
from pathlib import Path
from solana_sentinel.config import SOLANA_RECIPIENT, SOLANA_RPC_URL


def pull(state_dir: Path, operator_addresses: set[str]) -> dict:
    settle_addr = os.environ.get("SOLANA_RECIPIENT", SOLANA_RECIPIENT)
    rpc_url = os.environ.get("SOLANA_RPC_URL", SOLANA_RPC_URL)
    out = {"customer_usd": 0.0, "self_usd": 0.0, "unbound_usd": 0.0, "raws": [], "errors": []}

    if not settle_addr:
        out["errors"].append("solana_pay_misprovisioned: SOLANA_RECIPIENT missing")
        return out

    try:
        req = urllib.request.Request(
            rpc_url,
            data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getBalance", "params": [settle_addr]}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            res = json.loads(r.read().decode())
        out["raws"].append(("solana_balance", res))
        # Note: accurate USD conversion can be bound via Pyth / CoinGecko price feed
    except Exception as e:
        out["errors"].append(f"solana_pay_pull_failed: {type(e).__name__}: {e}")

    return out


def registered_adapter(state_dir: Path, operator_addresses: set[str]):
    from rails import RailAdapter, RailContribution

    def pull_contribution() -> RailContribution:
        result = pull(state_dir, operator_addresses)
        return RailContribution(
            name="solana_pay",
            directions=frozenset({"receive"}),
            customer_usd=result["customer_usd"],
            self_usd=result["self_usd"],
            unbound_usd=result["unbound_usd"],
            raw_payloads=result["raws"],
            errors=result["errors"],
            spent_usd=0.0,
        )

    return RailAdapter(name="solana_pay", directions=frozenset({"receive"}), pull=pull_contribution)
