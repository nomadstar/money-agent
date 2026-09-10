"""Unified entrypoint for Solana Sentinel AI."""
import argparse
import sys
import uvicorn
from solana_sentinel.config import SERVER_HOST, SERVER_PORT, TELEGRAM_BOT_TOKEN
from solana_sentinel.telegram_bot import run_telegram_bot
from solana_sentinel.analyzer.contract_auditor import ContractAuditor
from solana_sentinel.analyzer.token_scanner import TokenScanner


def main():
    parser = argparse.ArgumentParser(description="Solana Sentinel AI Agent")
    parser.add_argument("--web", action="store_true", help="Start the FastAPI web server with Solana Pay UI")
    parser.add_argument("--bot", action="store_true", help="Start the Telegram Bot daemon")
    parser.add_argument("--test-audit", type=str, help="Run an audit on a local file path (free testing)")
    parser.add_argument("--test-scan", type=str, help="Run a token scan on a mint address (free testing)")

    args = parser.parse_args()

    if args.test_audit:
        with open(args.test_audit, "r", encoding="utf-8") as f:
            code = f.read()
        print(f"\n--- Ejecutando auditoría en {args.test_audit} ---")
        auditor = ContractAuditor()
        res = auditor.generate_audit_report(code)
        print(f"Puntuación de Seguridad: {res['score']}/100")
        print("\n" + res["report_markdown"])
        return

    if args.test_scan:
        print(f"\n--- Escaneando Mint {args.test_scan} ---")
        scanner = TokenScanner()
        res = scanner.scan_mint(args.test_scan)
        print(f"Veredicto: {res['verdict']} ({res['risk_score']}/100)")
        print("\n" + res["summary_markdown"])
        return

    if args.bot:
        if not TELEGRAM_BOT_TOKEN:
            print("ERROR: TELEGRAM_BOT_TOKEN no está configurado en .env")
            sys.exit(1)
        run_telegram_bot()
        return

    # Default: launch web server
    print(f"\n🚀 Iniciando Solana Sentinel Web Gateway en http://{SERVER_HOST}:{SERVER_PORT}")
    uvicorn.run("solana_sentinel.server:app", host=SERVER_HOST, port=SERVER_PORT, reload=False)


if __name__ == "__main__":
    main()
