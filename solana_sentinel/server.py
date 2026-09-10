"""FastAPI Web Server and Solana Pay Gateway for Solana Sentinel."""
import time
import uuid
import logging
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from solana_sentinel.config import (
    SOLANA_RECIPIENT,
    AUDIT_PRICE_SOL,
    TOKEN_SCAN_PRICE_SOL,
    SOLANA_NETWORK,
    OLLAMA_MODEL,
)
from solana_sentinel.solana_pay import create_solana_pay_url, PaymentValidator
from solana_sentinel.analyzer.contract_auditor import ContractAuditor
from solana_sentinel.analyzer.token_scanner import TokenScanner

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("solana_sentinel.server")

app = FastAPI(title="Solana Sentinel AI", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory database of orders
orders: Dict[str, Dict[str, Any]] = {}

payment_validator = PaymentValidator()
contract_auditor = ContractAuditor()
token_scanner = TokenScanner()


class CreateOrderRequest(BaseModel):
    service: str  # "audit" or "token"
    payload: str  # Rust source code or Mint address


def execute_analysis(order_id: str):
    """Background task: execute auditor/scanner once payment is confirmed."""
    order = orders.get(order_id)
    if not order:
        return

    order["status"] = "processing"
    try:
        if order["service"] == "audit":
            res = contract_auditor.generate_audit_report(order["payload"])
            order["report"] = res
        elif order["service"] == "token":
            res = token_scanner.scan_mint(order["payload"].strip())
            order["report"] = res
        order["status"] = "completed"
        logger.info(f"Order {order_id} analysis completed.")
    except Exception as e:
        logger.error(f"Error processing order {order_id}: {e}")
        order["status"] = "failed"
        order["error"] = str(e)


@app.post("/api/orders")
async def create_order(req: CreateOrderRequest):
    if req.service not in ("audit", "token"):
        raise HTTPException(status_code=400, detail="Invalid service type. Choose 'audit' or 'token'.")

    amount = AUDIT_PRICE_SOL if req.service == "audit" else TOKEN_SCAN_PRICE_SOL
    label = "Solana Sentinel AI"
    msg = "Smart Contract Audit" if req.service == "audit" else "Token Security Scan"

    order_id = str(uuid.uuid4())[:8]
    sol_pay = create_solana_pay_url(
        recipient=SOLANA_RECIPIENT,
        amount=amount,
        label=label,
        message=f"{msg} #{order_id}",
        memo=f"order_{order_id}",
    )

    orders[order_id] = {
        "id": order_id,
        "service": req.service,
        "payload": req.payload,
        "amount_sol": amount,
        "recipient": SOLANA_RECIPIENT,
        "reference": sol_pay["reference"],
        "solana_url": sol_pay["solana_url"],
        "qr_data_uri": sol_pay["qr_data_uri"],
        "status": "pending",  # pending -> confirmed -> processing -> completed
        "created_at": time.time(),
        "tx_signature": None,
        "report": None,
    }

    return orders[order_id]


@app.get("/api/orders/{order_id}")
async def get_order_status(order_id: str, background_tasks: BackgroundTasks):
    order = orders.get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # If pending, poll Solana blockchain
    if order["status"] == "pending":
        check = payment_validator.check_payment(
            reference=order["reference"],
            expected_recipient=order["recipient"],
            min_amount_sol=order["amount_sol"],
        )
        if check.get("verified"):
            order["status"] = "confirmed"
            order["tx_signature"] = check.get("signature")
            order["amount_received_sol"] = check.get("amount_received_sol")
            # Trigger analysis
            background_tasks.add_task(execute_analysis, order_id)

    return order


@app.get("/", response_class=HTMLResponse)
async def index():
    return f"""<!DOCTYPE html>
<html lang="en" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Solana Sentinel AI — Autonomous Security & Intelligence</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
  <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap');
    body {{ font-family: 'Space Grotesk', sans-serif; }}
    pre, code {{ font-family: 'JetBrains Mono', monospace; }}
    .glow-green {{ box-shadow: 0 0 25px rgba(20, 241, 149, 0.25); }}
  </style>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen">
  <!-- Header -->
  <header class="border-b border-slate-800/80 bg-slate-900/50 backdrop-blur sticky top-0 z-30">
    <div class="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
      <div class="flex items-center gap-3">
        <div class="w-10 h-10 rounded-xl bg-gradient-to-tr from-emerald-500 to-teal-300 flex items-center justify-center text-slate-950 font-bold text-xl shadow-lg shadow-emerald-500/20">
          <i class="fa-solid fa-shield-halved"></i>
        </div>
        <div>
          <h1 class="text-xl font-bold tracking-tight bg-gradient-to-r from-emerald-400 to-teal-200 bg-clip-text text-transparent">
            Solana Sentinel AI
          </h1>
          <p class="text-xs text-slate-400">Autonomous Security & Pay-Per-Query Intelligence</p>
        </div>
      </div>
      <div class="flex items-center gap-4 text-xs font-mono">
        <span class="px-3 py-1 rounded-full bg-slate-800 border border-slate-700 text-slate-300 flex items-center gap-2">
          <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
          Net: {SOLANA_NETWORK}
        </span>
        <span class="px-3 py-1 rounded-full bg-slate-800 border border-slate-700 text-slate-300">
          Model: {OLLAMA_MODEL}
        </span>
      </div>
    </div>
  </header>

  <!-- Main Container -->
  <main class="max-w-5xl mx-auto px-6 py-10">
    <!-- Intro -->
    <div class="text-center mb-10">
      <h2 class="text-3xl sm:text-4xl font-extrabold tracking-tight mb-3">
        On-Chain Security Audits Powered by Local AI
      </h2>
      <p class="text-slate-400 max-w-2xl mx-auto text-sm sm:text-base">
        Zero accounts, zero signups. Pay instantly in SOL via 
        <span class="text-emerald-400 font-semibold">Solana Pay</span> directly to the autonomous agent.
      </p>
    </div>

    <!-- Service Selector Tabs -->
    <div class="flex justify-center mb-8">
      <div class="bg-slate-900 border border-slate-800 p-1.5 rounded-2xl flex gap-2">
        <button id="tabAudit" onclick="selectService('audit')" class="px-6 py-2.5 rounded-xl font-semibold text-sm transition-all bg-emerald-500 text-slate-950 shadow-md">
          <i class="fa-solid fa-code mr-2"></i> Smart Contract Audit ({AUDIT_PRICE_SOL} SOL)
        </button>
        <button id="tabToken" onclick="selectService('token')" class="px-6 py-2.5 rounded-xl font-semibold text-sm transition-all text-slate-400 hover:text-slate-200">
          <i class="fa-solid fa-coins mr-2"></i> Token / Rug Check ({TOKEN_SCAN_PRICE_SOL} SOL)
        </button>
      </div>
    </div>

    <!-- Audit Input Form -->
    <div class="bg-slate-900/60 border border-slate-800 rounded-2xl p-6 glow-green relative">
      <div id="auditSection">
        <label class="block text-sm font-semibold text-slate-300 mb-2">
          Solana Rust / Anchor Source Code:
        </label>
        <textarea id="sourceCode" rows="12" class="w-full bg-slate-950 border border-slate-800 rounded-xl p-4 font-mono text-xs text-emerald-300 focus:outline-none focus:border-emerald-500 transition-all placeholder-slate-600" placeholder="// Paste your Solana program / Anchor instruction code here...
#[program]
pub mod token_vault {{
    use super::*;
    pub fn withdraw(ctx: Context<Withdraw>, amount: u64) -> Result<()> {{
        // Unsafe raw transfer...
    }}
}}"></textarea>
      </div>

      <div id="tokenSection" class="hidden">
        <label class="block text-sm font-semibold text-slate-300 mb-2">
          Solana Token Mint Address:
        </label>
        <input id="mintAddress" type="text" class="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 font-mono text-sm text-emerald-300 focus:outline-none focus:border-emerald-500 transition-all placeholder-slate-600" placeholder="e.g. DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263 (BONK)">
      </div>

      <div class="mt-6 flex items-center justify-between">
        <div class="text-xs text-slate-400">
          Recipient: <span class="font-mono text-emerald-400">{SOLANA_RECIPIENT[:8]}...{SOLANA_RECIPIENT[-6:]}</span>
        </div>
        <button id="submitBtn" onclick="requestAnalysis()" class="px-8 py-3 bg-gradient-to-r from-emerald-400 to-teal-400 text-slate-950 font-bold rounded-xl hover:opacity-95 transition-all flex items-center gap-2 shadow-lg shadow-emerald-500/20">
          <span>Continue to Solana Pay</span>
          <i class="fa-solid fa-arrow-right"></i>
        </button>
      </div>
    </div>

    <!-- Modal for Solana Pay -->
    <div id="payModal" class="fixed inset-0 bg-slate-950/80 backdrop-blur-sm z-50 flex items-center justify-center p-4 hidden">
      <div class="bg-slate-900 border border-slate-800 rounded-2xl max-w-md w-full p-6 text-center shadow-2xl relative">
        <button onclick="closeModal()" class="absolute top-4 right-4 text-slate-400 hover:text-slate-100">
          <i class="fa-solid fa-xmark text-lg"></i>
        </button>
        
        <h3 class="text-xl font-bold mb-1">Pay with Solana</h3>
        <p class="text-xs text-slate-400 mb-4">Scan with Phantom, Solflare or any Solana Pay wallet</p>

        <!-- QR Code -->
        <div class="p-3 bg-slate-950 rounded-2xl border border-slate-800 inline-block mb-4">
          <img id="modalQr" src="" alt="Solana Pay QR" class="w-56 h-56 rounded-xl mx-auto">
        </div>

        <div class="bg-slate-950/60 p-3 rounded-xl border border-slate-800 text-xs font-mono text-left mb-4 space-y-1">
          <div class="flex justify-between text-slate-400">
            <span>Amount:</span>
            <span id="modalAmount" class="font-bold text-emerald-400"></span>
          </div>
          <div class="flex justify-between text-slate-400">
            <span>Recipient:</span>
            <span class="text-slate-300">{SOLANA_RECIPIENT[:6]}...{SOLANA_RECIPIENT[-4:]}</span>
          </div>
        </div>

        <a id="modalDeepLink" href="#" class="block w-full py-3 bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold rounded-xl mb-3 text-sm transition-all">
          <i class="fa-solid fa-wallet mr-2"></i> Open in Wallet App
        </a>

        <!-- Status indicator -->
        <div id="modalStatus" class="flex items-center justify-center gap-2 text-xs font-mono text-amber-400 animate-pulse">
          <i class="fa-solid fa-spinner fa-spin"></i>
          <span>Listening for Solana transaction...</span>
        </div>
      </div>
    </div>

    <!-- Results Container -->
    <div id="reportContainer" class="mt-12 hidden">
      <div class="bg-slate-900 border border-slate-800 rounded-2xl p-8">
        <div class="flex items-center justify-between pb-6 border-b border-slate-800 mb-6">
          <div>
            <h3 class="text-2xl font-bold text-emerald-400 flex items-center gap-2">
              <i class="fa-solid fa-check-circle"></i> Security Report Verified
            </h3>
            <p id="reportSub" class="text-xs text-slate-400 font-mono mt-1"></p>
          </div>
          <div class="text-right">
            <span class="text-xs text-slate-400 block font-mono">Security Score</span>
            <span id="reportScore" class="text-3xl font-black text-emerald-400"></span>
          </div>
        </div>
        <div id="reportMarkdown" class="prose prose-invert max-w-none text-slate-300 text-sm leading-relaxed"></div>
      </div>
    </div>
  </main>

  <script>
    let currentService = 'audit';
    let activeOrderId = null;
    let pollInterval = null;

    function selectService(s) {{
      currentService = s;
      if (s === 'audit') {{
        document.getElementById('auditSection').classList.remove('hidden');
        document.getElementById('tokenSection').classList.add('hidden');
        document.getElementById('tabAudit').className = "px-6 py-2.5 rounded-xl font-semibold text-sm bg-emerald-500 text-slate-950 shadow-md";
        document.getElementById('tabToken').className = "px-6 py-2.5 rounded-xl font-semibold text-sm text-slate-400 hover:text-slate-200";
      }} else {{
        document.getElementById('auditSection').classList.add('hidden');
        document.getElementById('tokenSection').classList.remove('hidden');
        document.getElementById('tabToken').className = "px-6 py-2.5 rounded-xl font-semibold text-sm bg-emerald-500 text-slate-950 shadow-md";
        document.getElementById('tabAudit').className = "px-6 py-2.5 rounded-xl font-semibold text-sm text-slate-400 hover:text-slate-200";
      }}
    }}

    async function requestAnalysis() {{
      const payload = currentService === 'audit' 
        ? document.getElementById('sourceCode').value 
        : document.getElementById('mintAddress').value;

      if (!payload.trim()) {{
        alert("Please provide the code or mint address.");
        return;
      }}

      document.getElementById('submitBtn').disabled = true;
      document.getElementById('submitBtn').innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Generating Solana Pay Request...';

      try {{
        const resp = await fetch('/api/orders', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ service: currentService, payload: payload }})
        }});
        const data = await resp.json();
        activeOrderId = data.id;

        document.getElementById('modalQr').src = data.qr_data_uri;
        document.getElementById('modalAmount').innerText = data.amount_sol + ' SOL';
        document.getElementById('modalDeepLink').href = data.solana_url;
        document.getElementById('payModal').classList.remove('hidden');

        // Start polling order status
        if (pollInterval) clearInterval(pollInterval);
        pollInterval = setInterval(pollOrderStatus, 2500);

      }} catch (err) {{
        alert("Error creating order: " + err);
      }} finally {{
        document.getElementById('submitBtn').disabled = false;
        document.getElementById('submitBtn').innerHTML = '<span>Continue to Solana Pay</span><i class="fa-solid fa-arrow-right ml-2"></i>';
      }}
    }}

    function closeModal() {{
      document.getElementById('payModal').classList.add('hidden');
      if (pollInterval) clearInterval(pollInterval);
    }}

    async function pollOrderStatus() {{
      if (!activeOrderId) return;
      try {{
        const res = await fetch('/api/orders/' + activeOrderId);
        const data = await res.json();

        if (data.status === 'confirmed' || data.status === 'processing') {{
          document.getElementById('modalStatus').innerHTML = '<i class="fa-solid fa-gear fa-spin text-emerald-400"></i><span class="text-emerald-400 font-bold">Payment Verified! Running Local AI Analysis...</span>';
        }} else if (data.status === 'completed') {{
          clearInterval(pollInterval);
          closeModal();
          displayReport(data);
        }}
      }} catch (e) {{
        console.error(e);
      }}
    }}

    function displayReport(order) {{
      document.getElementById('reportContainer').classList.remove('hidden');
      document.getElementById('reportContainer').scrollIntoView({{ behavior: 'smooth' }});
      
      const rep = order.report;
      document.getElementById('reportSub').innerText = "Tx Signature: " + (order.tx_signature || "Direct / Test");
      
      if (order.service === 'audit') {{
        document.getElementById('reportScore').innerText = (rep.score || 85) + '/100';
        document.getElementById('reportMarkdown').innerHTML = marked.parse(rep.report_markdown || "Audit completed.");
      }} else {{
        document.getElementById('reportScore').innerText = (rep.risk_score || 90) + '/100';
        document.getElementById('reportMarkdown').innerHTML = marked.parse(rep.summary_markdown || "Token scan completed.");
      }}
    }}
  </script>
</body>
</html>
"""
