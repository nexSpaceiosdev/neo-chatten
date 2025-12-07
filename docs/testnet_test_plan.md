# Chatten TestNet Test Plan

## Objectives
- Validate Chatten agent, tools, and NEP-11 contract behavior against a live Neo N3 TestNet environment.
- Confirm critical user flows for buying/selling compute capacity and managing liquidity.
- Verify observability and safety controls (pausing, admin/role enforcement) before MainNet launch.

## Scope
- **In scope:** agent startup/config validation (`main.py`), SpoonOS tools (bridge, token balance/transfer, Q-score analyzer), Chatten NEP-11 contract interactions (mint, transfer, buy/sell, admin paths), and end-to-end agent workflows using real RPC nodes.
- **Out of scope:** performance benchmarking beyond Q-score placeholder calculations, production monitoring stack, and UI components (none present).

## Environments
- **Network:** Neo N3 TestNet.
- **RPC endpoints:** `https://testnet1.neo.coz.io:443` (primary) with fallback to other public TestNet RPCs.
- **Wallets:**
  - Admin wallet (contract owner) with TestNet GAS.
  - Oracle/minter wallet configured in contract storage.
  - Trader wallet used by the Chatten agent (`NEO_WALLET_ADDRESS`).
- **Contract:** Deployed TestNet hash for `contracts/chatten_token.py` (record hash in `.env`).
- **Keys/config:** Populate `.env` with `NEO_PRIVATE_KEY`, `NEO_WALLET_ADDRESS`, `CHATTEN_CONTRACT_HASH`, `OPENAI_API_KEY` (if using LLM tools), and `SPOON_API_KEY` as available.

## Tooling & Data
- Python 3.12+ with project dependencies installed (`uv sync` or `pip install -e .[dev]`).
- Access to neo3-boa compiled contract artifact and deployment tx hash.
- Sample model IDs for Q-score/mint flows.

## Test Categories & Cases

### 1) Configuration & Startup
- **Config validation:** Run `python main.py` with incomplete `.env`; expect meaningful errors for missing RPC/keys.
- **Successful startup:** With full config, verify agent banner, network detection (TestNet), and no validation errors.
- **Debug/dry-run flags:** Toggle `DEBUG` and `DRY_RUN` to confirm logs and side effects are suppressed where expected.

### 2) Neo Bridge Connectivity (`tools/neo_bridge.py`)
- **RPC connectivity:** `connect` should succeed against primary RPC; `is_connected` returns true; gracefully handle bad endpoint by retry/fallback.
- **Wallet load:** Load NEP-6 wallet (or key import) and confirm `get_address` matches expected wallet.
- **Block/tx queries:** `get_block_height` returns a positive height; `get_transaction` fetches known deployment tx; `wait_for_transaction` times out appropriately.

### 3) Token Balance Operations (`tools/token_tools.py`)
- **Balance reads:** `get_balance` for trader wallet reflects on-chain state; zero when no tokens.
- **Ownership listing:** `get_tokens` returns minted token IDs for wallet after mint tests.
- **Token metadata:** `get_token_info` returns properties matching minted token (model_id hash, q_score, compute units).
- **Owner lookup:** `get_owner` matches mint recipient; handle nonexistent token gracefully.

### 4) Token Transfers (`tools/token_tools.py`)
- **Direct transfer success:** Transfer token from trader to secondary wallet; verify balances and `ownerOf` update on-chain.
- **Approval path:** Approve operator then transfer; ensure revocation works.
- **Batch transfers:** Execute multi-transfer sequence and confirm all tx hashes succeed or partial failures are reported.
- **Failure handling:** Attempt transfer with insufficient balance and verify tool surfaces contract error without state change.

### 5) Q-Score Analysis (`tools/market_tools.py`)
- **Metric fetch fallback:** `calculate_q_score` should fetch placeholder metrics when none provided; cache behavior for repeat calls.
- **Score scaling:** Validate component weights sum to 1 and composite score in 0–100 range; recommendations align with thresholds (mint vs improvement hints).
- **Model comparison:** Provide multiple model IDs and ensure sorted rankings are returned.
- **Market analysis stub:** Confirm graceful return of placeholder market metrics until oracle integration is completed.

### 6) Contract Functional Tests (`contracts/chatten_token.py`)
- **Minting rules:**
  - Oracle/minter accounts can mint when `quality >= 50`; balances, supply, and events update correctly.
  - Mint with `quality < 50` or unauthorized caller reverts.
- **Transfers:** Standard NEP-11 transfer emits `on_transfer`; contract callback executes when recipient is contract.
- **Buy flow:** `buy_compute` increases GAS reserve and mints compute based on price; rejects when price unset or gas too small.
- **Sell flow:** `sell_compute` burns tokens, pays GAS minus fee, and checks reserve sufficiency; ensure fee math correct.
- **Pause/resume:** When paused, state-changing methods revert; resume restores functionality.
- **Admin operations:** `set_oracle`, `set_minter`, and `withdraw_gas` enforce admin witness and update storage as expected.

### 7) Agent End-to-End Flow (`main.py`, `agents/chatten_trader.py`)
- **Lifecycle hooks:** `on_start` connects tools and loads state; `on_stop` cleans up without leaks.
- **Liquidity cycle:** Simulate fetch Q-score → mint (via oracle/minter) → buy/sell token loop using tools; verify market_state and position updates.
- **Error paths:** Network failure or invalid token_id surfaces actionable errors, not crashes.
- **Dry-run execution:** With `DRY_RUN=true`, confirm no signed transactions are broadcast but analysis/logging still occurs.

### 8) Security & Resilience
- **Witness checks:** Validate `check_witness` enforcement on mint/burn/withdraw/sell paths using unauthorized wallets.
- **Re-entrancy/callbacks:** Transfer to contract address triggers `onNEP11Payment` no-op; ensure no state corruption.
- **Rate limits:** Observe RPC limits; ensure tooling backs off or surfaces throttling errors clearly.
- **Data validation:** Invalid addresses/model IDs rejected at tool layer before on-chain invocation.

## Test Data & Fixtures
- Multiple wallet addresses with known balances (trader, admin, oracle).
- Model IDs (e.g., `b"model-alpha"`, `b"model-beta"`) with deterministic Q-score inputs for repeatability.
- GAS allocations sufficient for buy/sell cycles and admin withdrawals.

## Execution Steps (Happy Path)
1. Deploy contract to TestNet; record contract hash and admin/oracle/minter addresses.
2. Configure `.env` with RPC, wallet, and contract details; install dependencies.
3. Connect via NeoBridge; confirm block height retrieval.
4. Mint tokens using oracle/minter; verify balances and supply.
5. Execute buy and sell flows; validate GAS reserve accounting and transfer events.
6. Perform transfers/approvals between trader and secondary wallet.
7. Run agent end-to-end flow to evaluate Q-score, manage positions, and log actions (dry-run first, then live).
8. Test pause/resume and admin functions; ensure restricted actions fail for non-admins.
9. Capture logs, tx hashes, and contract storage snapshots for verification.

## Exit Criteria
- All critical functional cases pass (mint, buy/sell, transfer, pause/resume, admin checks).
- Agent can start, analyze Q-scores, and interact with contract on TestNet without unhandled exceptions.
- No unresolved high-severity defects; known limitations documented with mitigation or follow-up tasks.
