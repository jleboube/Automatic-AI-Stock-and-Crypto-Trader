# QQQQ Agents - Options Trading Platform

<div align="center">

[![Docker](https://img.shields.io/badge/Docker-Compose-blue.svg)](https://docs.docker.com/compose/)
[![GitHub stars](https://img.shields.io/github/stars/jleboube/Strike-Zone-Alignment-Score?style=social)](https://github.com/jleboube/Strike-Zone-Alignment-Score/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/jleboube/Strike-Zone-Alignment-Score?style=social)](https://github.com/jleboube/Strike-Zone-Alignment-Score/network/members)
[![GitHub issues](https://img.shields.io/github/issues/jleboube/Strike-Zone-Alignment-Score)](https://github.com/jleboube/Strike-Zone-Alignment-Score/issues)
[![GitHub pull requests](https://img.shields.io/github/issues-pr/jleboube/Strike-Zone-Alignment-Score)](https://github.com/jleboube/Strike-Zone-Alignment-Score/pulls)
[![License: CC BY-NC-SA 4.0](https://img.shields.io/badge/License-CCBY--NC--SA4.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc-sa/4.0/)

[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/muscl3n3rd)



A Sabermetric web application for analyzing MLB strike zone dynamics. SZAS quantifies the alignment and divergences among three distinct strike zones: the textbook rulebook zone, the umpire-called zone, and the batter-swing zone.

[Demo](https://geoscout.leboube.ai) • [Quick Start](#quick-start) • [API](#api-endpoints) 


</div>


A web application for hosting, monitoring, and managing autonomous QQQ options trading agents.

## Architecture

The system consists of 6 specialized AI agents:

| Agent | Role |
|-------|------|
| **Short-Put Agent** | Executes weekly 25-wide put credit spreads |
| **Short-Call Agent** | Runs recovery campaigns (poor-man's covered calls) |
| **Long-Call Agent** | Buys far-dated anchor calls in recovery mode |
| **Long-Put Agent** | Defensive hedging (rarely used) |
| **Risk & Position Agent** | Real-time P&L, buying power, and drawdown guardian |
| **Orchestrator Agent** | The "brain" - regime detection and agent coordination |

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Node.js 20+ (for local development)
- Python 3.11+ (for local development)

### Setup

1. Clone and navigate to the project:
   ```bash
   cd QQQQ-agents
   ```

2. Copy the environment template:
   ```bash
   cp .env.example .env
   ```

3. Edit `.env` with your credentials:
   ```bash
   # Add your brokerage and market data API keys
   ```

4. Build and start all services:
   ```bash
   docker-compose up --build
   ```

5. Access the dashboard at: **http://localhost:47823**

## Services

| Service | Port | Description |
|---------|------|-------------|
| Frontend | 47823 | React dashboard |
| Backend | 8000 | FastAPI server |
| PostgreSQL | 5432 | Database |
| Redis | 6379 | Cache & pub/sub |

## API Endpoints

### Agents
- `GET /api/agents/` - List all agents
- `GET /api/agents/{id}` - Get agent details
- `POST /api/agents/{id}/start` - Start an agent
- `POST /api/agents/{id}/stop` - Stop an agent
- `POST /api/agents/{id}/pause` - Pause an agent

### Trades
- `GET /api/trades/` - List all trades
- `GET /api/trades/open` - List open trades
- `GET /api/trades/stats` - Get trade statistics

### Orchestrator
- `GET /api/orchestrator/status` - Get current status
- `GET /api/orchestrator/regime` - Get current regime
- `POST /api/orchestrator/execute` - Manual weekly execution
- `POST /api/orchestrator/shutdown` - Emergency shutdown

### Metrics
- `GET /api/metrics/dashboard` - Dashboard data
- `GET /api/metrics/pnl-chart` - P&L chart data

## Market Regimes

| Regime | Trigger | Active Agents |
|--------|---------|---------------|
| Normal Bull | QQQ > last short put strike | Short-Put, Risk |
| Defense Trigger | Put spread would expire ITM | Risk (close spread) |
| Recovery Mode | Just closed a loss | Long-Call, Short-Call, Risk |
| Recovery Complete | QQQ > recovery strike | Close all recovery positions |

## Development

### Backend (FastAPI)
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Frontend (React + Vite)
```bash
cd frontend
npm install
npm run dev
```

## Safety Controls

- Max 25% of account deployed at once
- Auto-reduce size if drawdown > 15%
- Auto-shutdown if VIX > 45 for 48+ hours
- Emergency shutdown via API or dashboard

## Tech Stack

- **Backend**: FastAPI, SQLAlchemy, PostgreSQL, Redis
- **Frontend**: React, TypeScript, Tailwind CSS, Recharts
- **Infrastructure**: Docker, Nginx
