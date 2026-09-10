"""Telegram Bot daemon for Solana Sentinel AI."""
import asyncio
import io
import base64
import logging
from typing import Dict, Any
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from solana_sentinel.config import (
    TELEGRAM_BOT_TOKEN,
    SOLANA_RECIPIENT,
    AUDIT_PRICE_SOL,
    TOKEN_SCAN_PRICE_SOL,
)
from solana_sentinel.solana_pay import create_solana_pay_url, PaymentValidator
from solana_sentinel.analyzer.contract_auditor import ContractAuditor
from solana_sentinel.analyzer.token_scanner import TokenScanner

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("solana_sentinel.telegram")

validator = PaymentValidator()
auditor = ContractAuditor()
scanner = TokenScanner()


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🛡️ *Bienvenido a Solana Sentinel AI*\n\n"
        "Soy un agente autónomo de auditoría de seguridad y análisis on-chain en Solana.\n\n"
        "Comandos disponibles:\n"
        "• `/audit <código Rust / Anchor>` — Auditar un smart contract de Solana.\n"
        "• `/scan <dirección Mint>` — Análisis de seguridad y rug-check de un token.\n\n"
        f"💳 *Pagos:* 100% descentralizados vía *Solana Pay* a `{SOLANA_RECIPIENT[:8]}...{SOLANA_RECIPIENT[-6:]}`\n"
        f"• Auditoría: {AUDIT_PRICE_SOL} SOL\n"
        f"• Escaneo de Token: {TOKEN_SCAN_PRICE_SOL} SOL"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def scan_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Uso: `/scan <dirección_mint_solana>`", parse_mode="Markdown")
        return

    mint = args[0].strip()
    status_msg = await update.message.reply_text(f"🔍 Generando orden de escaneo para `{mint}`...", parse_mode="Markdown")

    sol_pay = create_solana_pay_url(
        recipient=SOLANA_RECIPIENT,
        amount=TOKEN_SCAN_PRICE_SOL,
        label="Solana Sentinel AI",
        message=f"Scan {mint[:6]}",
    )

    qr_bytes = base64.b64decode(sol_pay["qr_data_uri"].split(",")[1])
    bio = io.BytesIO(qr_bytes)
    bio.name = "solana_pay_qr.png"

    caption = (
        f"🪙 *Orden de Escaneo de Token*\n"
        f"• **Mint:** `{mint}`\n"
        f"• **Precio:** `{TOKEN_SCAN_PRICE_SOL} SOL`\n"
        f"• **Billetera:** `{SOLANA_RECIPIENT}`\n\n"
        f"Escanea el código QR con Phantom/Solflare o abre el enlace:\n"
        f"[Pagar con Billetera Solana]({sol_pay['solana_url']})\n\n"
        "⏳ *Esperando confirmación en la blockchain de Solana...*"
    )
    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=bio,
        caption=caption,
        parse_mode="Markdown",
    )
    await status_msg.delete()

    # Launch background polling task for this user
    asyncio.create_task(
        poll_and_deliver(
            chat_id=update.effective_chat.id,
            context=context,
            reference=sol_pay["reference"],
            amount=TOKEN_SCAN_PRICE_SOL,
            service="token",
            payload=mint,
        )
    )


async def audit_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.partition(" ")[2].strip()
    if not text:
        await update.message.reply_text("Uso: `/audit <pega aquí tu código Rust o Anchor>`", parse_mode="Markdown")
        return

    status_msg = await update.message.reply_text("🛡️ Generando orden de auditoría...", parse_mode="Markdown")

    sol_pay = create_solana_pay_url(
        recipient=SOLANA_RECIPIENT,
        amount=AUDIT_PRICE_SOL,
        label="Solana Sentinel AI",
        message="Smart Contract Audit",
    )

    qr_bytes = base64.b64decode(sol_pay["qr_data_uri"].split(",")[1])
    bio = io.BytesIO(qr_bytes)
    bio.name = "solana_pay_qr.png"

    caption = (
        f"🔒 *Orden de Auditoría de Smart Contract*\n"
        f"• **Precio:** `{AUDIT_PRICE_SOL} SOL`\n"
        f"• **Billetera:** `{SOLANA_RECIPIENT}`\n\n"
        f"Escanea el código QR con Phantom/Solflare o abre el enlace:\n"
        f"[Pagar con Billetera Solana]({sol_pay['solana_url']})\n\n"
        "⏳ *Esperando confirmación en la blockchain de Solana...*"
    )
    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=bio,
        caption=caption,
        parse_mode="Markdown",
    )
    await status_msg.delete()

    # Launch background polling task
    asyncio.create_task(
        poll_and_deliver(
            chat_id=update.effective_chat.id,
            context=context,
            reference=sol_pay["reference"],
            amount=AUDIT_PRICE_SOL,
            service="audit",
            payload=text,
        )
    )


async def poll_and_deliver(
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    reference: str,
    amount: float,
    service: str,
    payload: str,
):
    """Poll Solana RPC for up to 10 minutes until payment confirms."""
    max_attempts = 120  # 120 * 5s = 10 mins
    for _ in range(max_attempts):
        await asyncio.sleep(5)
        check = validator.check_payment(
            reference=reference,
            expected_recipient=SOLANA_RECIPIENT,
            min_amount_sol=amount,
        )
        if check.get("verified"):
            sig = check.get("signature")
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"✅ *Pago Verificado en Solana!*\nTx: `{sig}`\n\n⚙️ Ejecutando análisis con el modelo local de IA...",
                parse_mode="Markdown",
            )
            # Run local analysis
            if service == "audit":
                res = auditor.generate_audit_report(payload)
                report_text = f"📊 *Reporte de Auditoría Solana*\n*Puntuación de Seguridad:* {res.get('score')}/100\n\n"
                report_text += res.get("report_markdown", "")[:3500]
            else:
                res = scanner.scan_mint(payload)
                report_text = f"📊 *Reporte de Seguridad del Token*\n*Veredicto:* {res.get('verdict')} ({res.get('risk_score')}/100)\n\n"
                report_text += res.get("summary_markdown", "")[:3500]

            await context.bot.send_message(
                chat_id=chat_id,
                text=report_text,
                parse_mode="Markdown",
            )
            return

    await context.bot.send_message(
        chat_id=chat_id,
        text="⚠️ La orden ha expirado sin recibir confirmación en Solana. Si realizaste el pago, contacta al operador.",
    )


def run_telegram_bot(token: Optional[str] = None):
    bot_token = token or TELEGRAM_BOT_TOKEN
    if not bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN no configurado.")

    app = ApplicationBuilder().token(bot_token).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("audit", audit_cmd))
    app.add_handler(CommandHandler("scan", scan_cmd))

    logger.info("Iniciando Telegram Bot daemon...")
    app.run_polling()


if __name__ == "__main__":
    run_telegram_bot()
