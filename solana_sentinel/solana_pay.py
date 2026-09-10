"""Solana Pay protocol and payment verification engine."""
import base64
import io
import logging
import secrets
import urllib.parse
from typing import Dict, Any, Optional
import base58
import qrcode
from solana_sentinel.config import SOLANA_RECIPIENT
from solana_sentinel.rpc_client import SolanaRPCClient

logger = logging.getLogger(__name__)

LAMPORTS_PER_SOL = 1_000_000_000


def generate_reference() -> str:
    """Generate a unique 32-byte Ed25519-compatible public key encoded in Base58."""
    random_bytes = secrets.token_bytes(32)
    return base58.b58encode(random_bytes).decode("ascii")


def create_solana_pay_url(
    recipient: str = SOLANA_RECIPIENT,
    amount: float = 0.01,
    reference: Optional[str] = None,
    label: str = "Solana Sentinel AI",
    message: str = "AI Audit & Security Analysis",
    memo: Optional[str] = None,
) -> Dict[str, str]:
    """Create a Solana Pay compliant transfer URL and QR code."""
    if not reference:
        reference = generate_reference()

    params = {
        "amount": f"{amount:.4f}".rstrip("0").rstrip("."),
        "reference": reference,
        "label": label,
        "message": message,
    }
    if memo:
        params["memo"] = memo

    query_string = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    solana_url = f"solana:{recipient}?{query_string}"

    # Generate QR Code as base64 PNG
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=3,
    )
    qr.add_data(solana_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="#14F195", back_color="#0F172A")  # Solana neon green on dark
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    qr_base64 = base64.b64encode(buffered.getvalue()).decode("ascii")
    qr_data_uri = f"data:image/png;base64,{qr_base64}"

    return {
        "solana_url": solana_url,
        "reference": reference,
        "recipient": recipient,
        "amount": amount,
        "qr_data_uri": qr_data_uri,
    }


class PaymentValidator:
    def __init__(self, rpc_client: Optional[SolanaRPCClient] = None):
        self.rpc = rpc_client or SolanaRPCClient()

    def check_payment(
        self,
        reference: str,
        expected_recipient: str = SOLANA_RECIPIENT,
        min_amount_sol: float = 0.01,
    ) -> Dict[str, Any]:
        """Check if a confirmed transaction with the reference exists and transferred funds to recipient."""
        try:
            signatures = self.rpc.get_signatures_for_address(reference, limit=5, commitment="confirmed")
        except Exception as e:
            logger.error(f"Error checking signatures for reference {reference}: {e}")
            return {"verified": False, "error": f"RPC query error: {e}"}

        if not signatures:
            return {"verified": False, "status": "pending", "message": "No transaction detected yet"}

        min_lamports = int(min_amount_sol * LAMPORTS_PER_SOL)

        for sig_info in signatures:
            sig = sig_info.get("signature")
            if not sig:
                continue

            if sig_info.get("err") is not None:
                logger.warning(f"Transaction {sig} failed on-chain: {sig_info['err']}")
                continue

            # Fetch full parsed transaction
            tx = self.rpc.get_transaction(sig, commitment="confirmed")
            if not tx or not tx.get("meta"):
                continue

            meta = tx["meta"]
            if meta.get("err") is not None:
                continue

            # Find recipient account index
            transaction = tx.get("transaction", {})
            message = transaction.get("message", {})
            account_keys = message.get("accountKeys", [])

            recipient_index = None
            for idx, acc in enumerate(account_keys):
                pubkey = acc.get("pubkey") if isinstance(acc, dict) else acc
                if pubkey == expected_recipient:
                    recipient_index = idx
                    break

            if recipient_index is None:
                logger.warning(f"Tx {sig} did not include recipient {expected_recipient}")
                continue

            pre_balances = meta.get("preBalances", [])
            post_balances = meta.get("postBalances", [])

            if recipient_index < len(pre_balances) and recipient_index < len(post_balances):
                received_lamports = post_balances[recipient_index] - pre_balances[recipient_index]
                if received_lamports >= min_lamports:
                    received_sol = received_lamports / LAMPORTS_PER_SOL
                    logger.info(f"Payment verified: {received_sol} SOL to {expected_recipient} (tx: {sig})")
                    return {
                        "verified": True,
                        "status": "confirmed",
                        "signature": sig,
                        "slot": tx.get("slot"),
                        "amount_received_sol": received_sol,
                        "recipient": expected_recipient,
                        "reference": reference,
                    }
                else:
                    logger.warning(
                        f"Tx {sig} transferred {received_lamports} lamports, wanted {min_lamports}"
                    )

        return {"verified": False, "status": "pending", "message": "Transaction found but amount not met"}
