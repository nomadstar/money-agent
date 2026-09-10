"""Configuration module for Solana Sentinel Agent."""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env if present
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

# Solana Network Configuration
SOLANA_NETWORK = os.getenv("SOLANA_NETWORK", "mainnet-beta")  # mainnet-beta or devnet
SOLANA_RECIPIENT = os.getenv("SOLANA_RECIPIENT", "JP7Ys4VPXHM2J2KsiMFCeA5bq99pA8zEeZdAJURZGpD")

# RPC URLs
DEFAULT_RPCS = {
    "mainnet-beta": "https://api.mainnet-beta.solana.com",
    "devnet": "https://api.devnet.solana.com",
}
SOLANA_RPC_URL = os.getenv("SOLANA_RPC_URL", DEFAULT_RPCS.get(SOLANA_NETWORK, DEFAULT_RPCS["mainnet-beta"]))

# Pricing (in SOL)
AUDIT_PRICE_SOL = float(os.getenv("AUDIT_PRICE_SOL", "0.01"))
TOKEN_SCAN_PRICE_SOL = float(os.getenv("TOKEN_SCAN_PRICE_SOL", "0.005"))

# LLM / Ollama Configuration
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:14b")
LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "180"))

# Telegram Bot
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
OPERATOR_TELEGRAM_ID = os.getenv("OPERATOR_TELEGRAM_ID", "")

# Server Configuration
SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("SERVER_PORT", "8000"))
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
