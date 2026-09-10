"""Solana JSON-RPC client."""
import json
import logging
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional
from solana_sentinel.config import SOLANA_RPC_URL

logger = logging.getLogger(__name__)


class SolanaRPCClient:
    def __init__(self, rpc_url: Optional[str] = None, timeout: int = 15):
        self.rpc_url = rpc_url or SOLANA_RPC_URL
        self.timeout = timeout

    def _call(self, method: str, params: list) -> Any:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.rpc_url,
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "SolanaSentinel/1.0"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                res = json.loads(response.read().decode("utf-8"))
            if "error" in res:
                logger.error(f"RPC error for {method}: {res['error']}")
                raise RuntimeError(f"RPC {method} error: {res['error']}")
            return res.get("result")
        except urllib.error.URLError as e:
            logger.error(f"Network error calling RPC {method}: {e}")
            raise

    def get_balance(self, pubkey: str) -> int:
        """Returns balance in lamports."""
        res = self._call("getBalance", [pubkey])
        if isinstance(res, dict) and "value" in res:
            return int(res["value"])
        return 0

    def get_signatures_for_address(
        self, pubkey: str, limit: int = 10, commitment: str = "confirmed"
    ) -> List[Dict[str, Any]]:
        """Fetch recent transaction signatures for an address / reference key."""
        params = [pubkey, {"limit": limit, "commitment": commitment}]
        res = self._call("getSignaturesForAddress", params)
        if isinstance(res, list):
            return res
        return []

    def get_transaction(
        self, signature: str, commitment: str = "confirmed"
    ) -> Optional[Dict[str, Any]]:
        """Fetch transaction details."""
        params = [
            signature,
            {
                "commitment": commitment,
                "encoding": "jsonParsed",
                "maxSupportedTransactionVersion": 0,
            },
        ]
        res = self._call("getTransaction", params)
        if isinstance(res, dict):
            return res
        return None

    def get_account_info(
        self, pubkey: str, encoding: str = "jsonParsed"
    ) -> Optional[Dict[str, Any]]:
        """Fetch account info."""
        params = [pubkey, {"encoding": encoding}]
        res = self._call("getAccountInfo", params)
        if isinstance(res, dict) and "value" in res:
            return res["value"]
        return None

    def get_token_largest_accounts(self, mint: str) -> List[Dict[str, Any]]:
        """Fetch largest token accounts (top 20) for distribution analysis."""
        res = self._call("getTokenLargestAccounts", [mint])
        if isinstance(res, dict) and "value" in res:
            return res["value"]
        return []
