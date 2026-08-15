# SetuHaul — AI-Powered Freight Operations Platform

An end-to-end freight dock scheduling and driver assistance system built on **AWS Bedrock AgentCore**. Drivers report en-route issues through a conversational AI agent; operations staff manage shipments, approve ETA changes, and allocate dock slots through an admin dashboard with AI-powered suggestions.

---

## What It Does

**For Drivers:**
- Chat with an AI agent to report delays, breakdowns, traffic issues, or ETA changes
- Agent extracts structured incident data automatically — no forms to fill
- View shipment status, approved ETAs, and appointment slots in real-time
- Resume conversations across sessions with full message history

**For Operations:**
- Dashboard showing all shipments, statuses, and driver-reported exceptions
- AI-scored slot suggestions ranked by time proximity, priority, and dock compatibility
- Calendar view for slot assignment with multi-slot selection (1-3 consecutive)
- One-click ETA override with full audit trail
- Status management with automatic facility check-in tracking

---

## Architecture

```
                    Vercel                          Railway / Local
               ┌────────────────┐            ┌──────────────────────────┐
               │   React SPA    │───HTTPS───▶│   FastAPI (server.py)    │
               │                │            │   Port 8000              │
               │  /driver chat  │            │                          │
               │  /admin dash   │            │   ┌──────────────────┐   │
               └────────────────┘            │   │ agent_invoker.py │   │
                                             │   └────────┬─────────┘   │
                                             └────────────│─────────────┘
                                                          │
                              ┌────────────────────────────┼──────────────┐
                              │                            ▼              │
                              │         AWS Bedrock AgentCore Runtime     │
                              │     ┌──────────────────────────────┐     │
                              │     │  handler.py (Strands Agent)   │     │
                              │     │  + tools.py (record_issue)    │     │
                              │     │  + memory.py (STM)            │     │
                              │     │  + config.py (centralized)    │     │
                              │     └──────────────┬───────────────┘     │
                              │                    │                      │
                              └────────────────────│──────────────────────┘
                                                   │
                                                   ▼
                                            ┌─────────────┐
                                            │  Supabase   │
                                            │  (Postgres) │
                                            └─────────────┘
```

---

## Key Features

### Agent (AWS Bedrock AgentCore)

- **Model:** Claude Sonnet 4 on Amazon Bedrock
- **Framework:** Strands Agents with `@tool` decorators
- **Memory:** Short-Term Memory (STM) via AgentCore MemorySessionManager — maintains conversation context across invocations
- **Tool:** `record_driver_issue` — extracts and persists driver exceptions to the database
- **Deployment:** Containerized on AgentCore Runtime with VPC networking
- **Invocation:** `invoke_agent_runtime` via boto3 from the FastAPI server

### Driver Chat

- Phone-number login (maps to driver record in DB)
- Shipment-scoped sessions — driver selects which shipment they're discussing
- Agent pre-loaded with driver's shipment context (origin, destination, ETA, dock type, priority)
- No ID questions — agent already knows driver_id, vehicle_id, shipment_id from authentication
- Today/tomorrow date resolution injected into context
- Full message history persisted in `chat_messages` table
- Collapsible side panel showing shipment status and ETA approval state

### Admin Dashboard

- **Shipments table** with inline status dropdown (triggers facility check-in state machine)
- **Exceptions table** showing driver-reported issues with severity, delay, and declared ETA
- **Slot suggestions** — AI-scored available slots ranked by fitness (proximity to ETA, priority, weight headroom)
- **Calendar slot picker** — visual grid organized by dock and hour, color-coded (available/blocked/before-ETA/selected)
- **Multi-slot selection** — supports 1-3 consecutive slots for heavy or long-duration loads
- **ETA override modal** — operations person can reassign slots with a reason (recorded as `OPERATIONS_OVERRIDE` in `eta_updates`)
- **Driver info popup** — click any driver name to see phone, carrier, licence, home city
- **Slot management** — generate weekly slots, block/unblock individual or bulk slots
- **Shipment creation** — form with cascading dropdowns (carrier → drivers/vehicles) and automatic appointment + ETA record creation

### Thread Status Lifecycle

```
OPEN → driver reported issue, waiting for operations
RESOLVED → operations approved ETA / assigned slot
CLOSED → shipment completed or cancelled
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, TypeScript, Vite, React Router |
| Backend API | Python, FastAPI, Uvicorn |
| AI Agent | Strands Agents, Claude Sonnet 4, AWS Bedrock |
| Agent Runtime | AWS Bedrock AgentCore (HTTP protocol, STM memory) |
| Database | Supabase (PostgreSQL) |
| Deployment | Vercel (frontend), Railway (backend), AgentCore (agent) |

---

## Project Structure

```
Sethaul/
├── client/                      # React frontend (Vercel)
│   ├── src/
│   │   ├── components/          # ChatScreen, LoginScreen, SlotCalendarPicker, ...
│   │   ├── pages/               # AdminDashboard, AdminExceptionDetail, AdminCreateShipment, AdminSlotManager
│   │   ├── services/            # api.ts, adminApi.ts
│   │   └── styles/              # index.css
│   ├── vercel.json
│   └── package.json
│
├── server/                      # FastAPI backend (Railway)
│   ├── server.py                # Main API server (port 8000)
│   ├── agent_invoker.py         # Invokes agent via AgentCore or HTTP
│   ├── db.py                    # Full Supabase operations layer
│   ├── start.py                 # Unified launcher (both servers)
│   ├── generate_slots.py        # Weekly slot generation utility
│   │
│   └── agentcore/               # Deployed to AWS AgentCore Runtime
│       ├── handler.py           # Agent entrypoint (Strands + BedrockAgentCoreApp)
│       ├── tools.py             # @tool: record_driver_issue
│       ├── memory.py            # STM load/persist helpers
│       ├── config.py            # Centralized config + logger
│       ├── db.py                # Minimal DB client (only what tools need)
│       ├── agent_deploy.py      # Deployment script
│       └── requirements.txt     # Agent dependencies
│
├── Sethaul Database/            # Schema, seed data, ER diagrams
│   ├── setuhaul_schema_and_seed.sql
│   ├── setuhaul_database_guide.md
│   └── insert_weekly_slots.sql
│
├── requirements.txt             # Root Python dependencies
├── Procfile                     # Railway start command
├── DEPLOYMENT.md                # Deployment guide
└── README.md
```

---

## Database Schema

18 tables covering the full freight operations lifecycle:

| Domain | Tables |
|--------|--------|
| Identity | `carriers`, `drivers`, `vehicles`, `vehicle_types` |
| Facilities | `facilities`, `docks`, `facility_contacts`, `facility_rules` |
| Shipments | `shipments`, `eta_updates` |
| Scheduling | `appointment_slots`, `appointments`, `dock_status_events` |
| Operations | `facility_checkins` |
| Conversations | `chat_threads`, `chat_messages`, `driver_exceptions`, `operational_messages` |

4 views: `v_latest_eta`, `v_slot_availability`, `v_inbound_operational_state`, `v_current_facility_queue`

---

## Running Locally

```bash
# 1. Agent (port 8080)
cd server/agentcore
python handler.py

# 2. Backend API (port 8000)
cd server
python server.py

# 3. Frontend (port 3000)
cd client
npm install
npm run dev
```

Set environment variables in `.env`:
```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key
AWS_REGION=us-east-1
MEMORY_ID=your-memory-id
AGENT_ARN=arn:aws:bedrock-agentcore:us-east-1:123456:runtime/your-agent
```

---

## Deployment

| Component | Platform | Command |
|-----------|----------|---------|
| Frontend | Vercel | `cd client && vercel` |
| Backend | Railway | `cd server && railway up` |
| Agent | AgentCore | `cd server/agentcore && python agent_deploy.py` |

See `DEPLOYMENT.md` for detailed steps and environment variable reference.

---

## Agent Invocation Modes

The system supports two invocation modes controlled by a single env var:

```bash
# Production: AgentCore Runtime (set AGENT_ARN)
AGENT_ARN=arn:aws:bedrock-agentcore:us-east-1:123456:runtime/agent-id

# Local development: Direct HTTP (unset AGENT_ARN)
# Falls back to http://localhost:8080/invocations
```

No code changes needed to switch between modes.

---

## Slot Suggestion Scoring

When an operations person reviews a driver exception, the system scores available slots (0-100):

| Factor | Impact |
|--------|--------|
| Time proximity to driver's ETA (< 15 min) | +30 |
| Time proximity (15-30 min) | +25 |
| Time proximity (30-60 min) | +15 |
| Slot starts before ETA | -20 |
| CRITICAL/HIGH priority shipment | +10 |
| Weight capacity headroom > 20% | +5 |
| Weight capacity tight < 5% | -10 |

Labels: `HIGHLY_RECOMMENDED` (80+), `RECOMMENDED` (60+), `ACCEPTABLE` (40+), `SUB_OPTIMAL` (20+), `NOT_RECOMMENDED` (<20)

---

## ETA Audit Trail

Every ETA change is recorded in `eta_updates` with source attribution:

| Source | When |
|--------|------|
| `ORIGINAL_PLAN` | Shipment created |
| `DRIVER_DECLARED` | Driver reports via chat agent |
| `OPERATIONS_OVERRIDE` | Operations person manually reassigns |
| `WAREHOUSE_ESTIMATE` | Warehouse provides updated estimate |
