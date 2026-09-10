"""Telegram Bot daemon for Solana Sentinel AI."""
import asyncio
import io
import base64
import html
import logging
import urllib.parse
from typing import Optional
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

from solana_sentinel.config import (
    TELEGRAM_BOT_TOKEN,
    OPERATOR_TELEGRAM_ID,
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


def is_operator(user_id: int) -> bool:
    try:
        return bool(OPERATOR_TELEGRAM_ID) and str(user_id) == str(OPERATOR_TELEGRAM_ID)
    except Exception:
        return False


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id if user else 0
    op_status = "👑 <i>Modo Operador Reconocido</i>\n\n" if is_operator(user_id) else ""

    text = (
        "🛡️ <b>Bienvenido a Solana Sentinel AI</b>\n\n"
        f"{op_status}"
        "Soy un agente autónomo de auditoría de seguridad y análisis on-chain en Solana.\n\n"
        "<b>Comandos disponibles:</b>\n"
        "• <code>/audit &lt;código Rust / Anchor&gt;</code> — Auditar un smart contract de Solana.\n"
        "• <code>/scan &lt;dirección Mint&gt;</code> — Análisis de seguridad y rug-check de un token.\n"
    )
    if is_operator(user_id):
        text += "• <code>/testaudit &lt;código&gt;</code> — Auditoría instantánea sin pago (Operador).\n"
        text += "• <code>/testscan &lt;mint&gt;</code> — Escaneo instantáneo sin pago (Operador).\n"

    text += (
        f"\n💳 <b>Pagos descentralizados con Solana Pay:</b>\n"
        f"• Auditoría: <code>{AUDIT_PRICE_SOL} SOL</code>\n"
        f"• Escaneo de Token: <code>{TOKEN_SCAN_PRICE_SOL} SOL</code>\n"
        f"• Billetera de depósito: <code>{SOLANA_RECIPIENT}</code>"
    )
    await update.message.reply_html(text)


async def scan_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_html("Uso: <code>/scan &lt;dirección_mint_solana&gt;</code>")
        return

    mint = args[0].strip()
    status_msg = await update.message.reply_html(f"🔍 Generando orden de escaneo para <code>{html.escape(mint)}</code>...")

    sol_pay = create_solana_pay_url(
        recipient=SOLANA_RECIPIENT,
        amount=TOKEN_SCAN_PRICE_SOL,
        label="Solana Sentinel AI",
        message=f"Scan {mint[:6]}",
    )

    qr_bytes = base64.b64decode(sol_pay["qr_data_uri"].split(",")[1])
    bio = io.BytesIO(qr_bytes)
    bio.name = "solana_pay_qr.png"

    # Phantom wallet link
    encoded_uri = urllib.parse.quote(sol_pay["solana_url"])
    phantom_url = f"https://phantom.app/ul/browse/{encoded_uri}"

    caption = (
        f"🪙 <b>Orden de Escaneo de Token</b>\n\n"
        f"• <b>Mint:</b> <code>{html.escape(mint)}</code>\n"
        f"• <b>Precio:</b> <code>{TOKEN_SCAN_PRICE_SOL} SOL</code>\n"
        f"• <b>Billetera:</b> <code>{SOLANA_RECIPIENT}</code>\n\n"
        f"📱 <b>Para Pagar:</b>\n"
        f"1. Escanea el código QR con Phantom o Solflare.\n"
        f"2. O copia el URI de Solana Pay:\n<code>{html.escape(sol_pay['solana_url'])}</code>\n\n"
        f"⏳ <i>Esperando confirmación en la blockchain de Solana...</i>"
    )
    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=bio,
        caption=caption,
        parse_mode="HTML",
    )
    await status_msg.delete()

    asyncio.create_task(
        poll_and_deliver(
            chat_id=update.effective_chat.id,
            user_name=update.effective_user.first_name if update.effective_user else "Anon",
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
        await update.message.reply_html("Uso: <code>/audit &lt;pega aquí tu código Rust o Anchor&gt;</code>")
        return

    status_msg = await update.message.reply_html("🛡️ Generando orden de auditoría...")

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
        f"🔒 <b>Orden de Auditoría de Smart Contract</b>\n\n"
        f"• <b>Precio:</b> <code>{AUDIT_PRICE_SOL} SOL</code>\n"
        f"• <b>Billetera:</b> <code>{SOLANA_RECIPIENT}</code>\n\n"
        f"📱 <b>Para Pagar:</b>\n"
        f"1. Escanea el código QR con tu billetera Solana.\n"
        f"2. O copia el URI de Solana Pay:\n<code>{html.escape(sol_pay['solana_url'])}</code>\n\n"
        f"⏳ <i>Esperando confirmación en la blockchain de Solana...</i>"
    )
    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=bio,
        caption=caption,
        parse_mode="HTML",
    )
    await status_msg.delete()

    asyncio.create_task(
        poll_and_deliver(
            chat_id=update.effective_chat.id,
            user_name=update.effective_user.first_name if update.effective_user else "Anon",
            context=context,
            reference=sol_pay["reference"],
            amount=AUDIT_PRICE_SOL,
            service="audit",
            payload=text,
        )
    )


async def test_audit_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_operator(update.effective_user.id):
        await update.message.reply_html("⛔ Comando exclusivo para el operador.")
        return
    text = update.message.text.partition(" ")[2].strip()
    if not text:
        await update.message.reply_html("Uso: <code>/testaudit &lt;código&gt;</code>")
        return

    msg = await update.message.reply_html("⚙️ <i>Ejecutando auditoría gratuita de operador...</i>")
    res = auditor.generate_audit_report(text)
    score = res.get("score", 90)
    report_text = f"📊 <b>Reporte de Auditoría (Operador)</b>\n<b>Score:</b> {score}/100\n\n<pre>{html.escape(res.get('report_markdown', '')[:3500])}</pre>"
    await update.message.reply_html(report_text)
    await msg.delete()


async def test_scan_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_operator(update.effective_user.id):
        await update.message.reply_html("⛔ Comando exclusivo para el operador.")
        return
    args = context.args
    if not args:
        await update.message.reply_html("Uso: <code>/testscan &lt;mint&gt;</code>")
        return
    mint = args[0].strip()
    msg = await update.message.reply_html(f"⚙️ <i>Escaneando token {html.escape(mint)}...</i>")
    res = scanner.scan_mint(mint)
    report_text = (
        f"📊 <b>Escaneo de Token (Operador)</b>\n"
        f"• <b>Veredicto:</b> {res.get('verdict')}\n"
        f"• <b>Puntuación:</b> {res.get('risk_score')}/100\n"
        f"• <b>Supply:</b> {res.get('supply'):,.2f}\n"
        f"• <b>Mint Auth:</b> {res.get('mint_authority') or 'Revoked'}\n"
        f"• <b>Freeze Auth:</b> {res.get('freeze_authority') or 'Revoked'}\n\n"
        f"<pre>{html.escape(res.get('summary_markdown', '')[:3000])}</pre>"
    )
    await update.message.reply_html(report_text)
    await msg.delete()


async def poll_and_deliver(
    chat_id: int,
    user_name: str,
    context: ContextTypes.DEFAULT_TYPE,
    reference: str,
    amount: float,
    service: str,
    payload: str,
):
    max_attempts = 120  # 120 * 5s = 10 min
    for _ in range(max_attempts):
        await asyncio.sleep(5)
        check = validator.check_payment(
            reference=reference,
            expected_recipient=SOLANA_RECIPIENT,
            min_amount_sol=amount,
        )
        if check.get("verified"):
            sig = check.get("signature")
            # Notify the paying user
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"✅ <b>¡Pago Verificado en Solana!</b>\nTx: <code>{sig}</code>\n\n⚙️ <i>Ejecutando análisis de seguridad con el agente local...</i>",
                parse_mode="HTML",
            )

            # Notify the operator (@Nomad_star)
            if OPERATOR_TELEGRAM_ID and str(chat_id) != str(OPERATOR_TELEGRAM_ID):
                try:
                    await context.bot.send_message(
                        chat_id=int(OPERATOR_TELEGRAM_ID),
                        text=(
                            f"💰 <b>¡Nuevo Pago Recibido!</b>\n"
                            f"• <b>Usuario:</b> {html.escape(user_name)} (ID: {chat_id})\n"
                            f"• <b>Servicio:</b> {service}\n"
                            f"• <b>Monto:</b> <code>{amount} SOL</code>\n"
                            f"• <b>Tx:</b> <code>{sig}</code>"
                        ),
                        parse_mode="HTML",
                    )
                except Exception as e:
                    logger.warning(f"No se pudo notificar al operador: {e}")

            # Run local analysis
            if service == "audit":
                res = auditor.generate_audit_report(payload)
                score = res.get("score", 90)
                report_text = f"📊 <b>Reporte de Auditoría Solana</b>\n<b>Score:</b> {score}/100\n\n<pre>{html.escape(res.get('report_markdown', '')[:3500])}</pre>"
            else:
                res = scanner.scan_mint(payload)
                report_text = (
                    f"📊 <b>Reporte de Seguridad del Token</b>\n"
                    f"<b>Veredicto:</b> {res.get('verdict')} ({res.get('risk_score')}/100)\n\n"
                    f"<pre>{html.escape(res.get('summary_markdown', '')[:3500])}</pre>"
                )

            await context.bot.send_message(
                chat_id=chat_id,
                text=report_text,
                parse_mode="HTML",
            )
            return

    await context.bot.send_message(
        chat_id=chat_id,
        text="⚠️ <i>La orden ha expirado sin recibir confirmación en Solana.</i>",
        parse_mode="HTML",
    )


def run_telegram_bot(token: Optional[str] = None):
    bot_token = token or TELEGRAM_BOT_TOKEN
    if not bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN no configurado.")

    app = ApplicationBuilder().token(bot_token).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("audit", audit_cmd))
    app.add_handler(CommandHandler("scan", scan_cmd))
    app.add_handler(CommandHandler("testaudit", test_audit_cmd))
    app.add_handler(CommandHandler("testscan", test_scan_cmd))

    logger.info("Iniciando Telegram Bot daemon...")
    app.run_polling()


if __name__ == "__main__":
    run_telegram_bot()
