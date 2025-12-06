# Stock & Crypto Autonomous AI Trading Platform

<div align="center">

[![Docker](https://img.shields.io/badge/Docker-Compose-blue.svg)](https://docs.docker.com/compose/)
[![GitHub stars](https://img.shields.io/github/stars/jleboube/Automatic-AI-Stock-and-Crypto-Trader?style=social)](https://github.com/jleboube/Automatic-AI-Stock-and-Crypto-Trader/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/jleboube/Automatic-AI-Stock-and-Crypto-Trader?style=social)](https://github.com/jleboube/Automatic-AI-Stock-and-Crypto-Trader/network/members)
[![GitHub issues](https://img.shields.io/github/issues/jleboube/Automatic-AI-Stock-and-Crypto-Trader)](https://github.com/jleboube/Automatic-AI-Stock-and-Crypto-Trader/issues)
[![GitHub pull requests](https://img.shields.io/github/issues-pr/jleboube/Automatic-AI-Stock-and-Crypto-Trader)](https://github.com/jleboube/Automatic-AI-Stock-and-Crypto-Trader/pulls)
[![License: CC BY-NC-SA 4.0](https://img.shields.io/badge/License-CCBY--NC--SA4.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc-sa/4.0/)

[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/muscl3n3rd)

**WARNING: Trading stocks and crypto is very risky. This app is not intended for anyone that likes their money. This hasn't been backtested. This was literally one-shotted using Claude and I transferred $250 into the account and let the "Crypto Hunter" agent loose. Do not use this app if you want to save your money.**

[Quick Start](#quick-start) • [Crypto Hunter](#crypto-hunter) • [Options Trading](#options-trading-agents) • [API](#api-endpoints)

</div>

A web application for hosting, monitoring, and managing autonomous trading agents for both **cryptocurrency** (via Robinhood) and **QQQ options** trading.

## Crypto Hunter

The **Crypto Hunter** is an autonomous cryptocurrency trading agent that runs 24/7 via Robinhood's crypto trading API.

### Features

- **Real-time Market Scanning**: Screens all tradeable cryptocurrencies using CoinGecko data
- **Multi-factor Scoring**: Technical analysis, momentum indicators, and composite scoring
- **Automated Entry/Exit**: Places market orders based on configurable triggers
- **Position Management**: Tracks positions with stop-loss and take-profit levels
- **Live P&L Tracking**: Real-time unrealized P&L calculations with cost basis tracking
- **Scheduler**: Runs scans at configurable intervals (default: 15 minutes)

### Crypto Hunter Dashboard

| Tab | Description |
|-----|-------------|
| **Overview** | Agent status, capital allocation, daily/total P&L |
| **Watchlist** | Cryptocurrencies being monitored with scores and entry triggers |
| **Positions** | Open positions with quantity, entry price, current price, cost, value, P&L, and P&L % |
| **History** | Completed trades with entry/exit prices and realized P&L |
| **Settings** | Configure capital, position size, stop-loss, take-profit, and scan intervals |

### Configuration Options

| Setting | Description | Default |
|---------|-------------|---------|
| `allocated_capital` | Total capital to deploy | $100 |
| `max_positions` | Maximum concurrent positions | 5 |
| `position_size_percent` | % of capital per position | 20% |
| `stop_loss_percent` | Stop-loss trigger | 5% |
| `take_profit_percent` | Take-profit trigger | 15% |
| `min_composite_score` | Minimum score to enter watchlist | 0.6 |
| `scan_interval_minutes` | Minutes between market scans | 15 |
| `auto_trade` | Enable autonomous trading | false |

---

## Options Trading Agents

The system also includes 6 specialized AI agents for QQQ options trading:

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
   # Robinhood Crypto API (required for Crypto Hunter)
   ROBINHOOD_API_KEY=your_api_key
   ROBINHOOD_PRIVATE_KEY_BASE64=your_base64_encoded_private_key

   # Optional: Stock brokerage and market data API keys
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

### Crypto Hunter
- `GET /api/crypto/status` - Check Robinhood connection status
- `GET /api/crypto/account` - Get account buying power and equity
- `GET /api/crypto/holdings` - Get current crypto holdings
- `GET /api/crypto/hunter/state` - Get Crypto Hunter agent state
- `GET /api/crypto/hunter/watchlist` - Get watchlist entries
- `POST /api/crypto/hunter/watchlist/add` - Add symbol to watchlist
- `POST /api/crypto/hunter/watchlist/{symbol}/remove` - Remove from watchlist
- `GET /api/crypto/hunter/positions` - Get open positions
- `POST /api/crypto/hunter/positions/{id}/close` - Close a position
- `GET /api/crypto/hunter/history` - Get trade history
- `POST /api/crypto/hunter/scan` - Trigger manual market scan
- `GET /api/crypto/hunter/config` - Get configuration
- `PATCH /api/crypto/hunter/config` - Update configuration
- `GET /api/crypto/quotes/{symbol}` - Get quote for a symbol
- `POST /api/crypto/quotes` - Get quotes for multiple symbols
- `GET /api/crypto/pairs` - Get tradeable pairs
- `GET /api/crypto/orders` - Get orders
- `DELETE /api/crypto/orders/{id}` - Cancel an order

### Scheduler
- `GET /api/crypto/scheduler/status` - Get scheduler status and jobs
- `POST /api/crypto/scheduler/start` - Start the background scheduler
- `POST /api/crypto/scheduler/stop` - Stop the background scheduler

### Agents (Options)
- `GET /api/agents/` - List all agents
- `GET /api/agents/{id}` - Get agent details
- `POST /api/agents/{id}/start` - Start an agent
- `POST /api/agents/{id}/stop` - Stop an agent
- `POST /api/agents/{id}/pause` - Pause an agent

### Trades (Options)
- `GET /api/trades/` - List all trades
- `GET /api/trades/open` - List open trades
- `GET /api/trades/stats` - Get trade statistics

### Orchestrator (Options)
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

- **Backend**: FastAPI, SQLAlchemy, PostgreSQL, Redis, APScheduler
- **Frontend**: React, TypeScript, Tailwind CSS, Recharts
- **Crypto Trading**: Robinhood Crypto API, CoinGecko API (market data)
- **Infrastructure**: Docker, Docker Compose, Nginx

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `ROBINHOOD_API_KEY` | Robinhood API key for crypto trading | Yes (for Crypto) |
| `ROBINHOOD_PRIVATE_KEY_BASE64` | Base64-encoded private key | Yes (for Crypto) |
| `DATABASE_URL` | PostgreSQL connection string | Yes |
| `REDIS_URL` | Redis connection string | Yes |
| `COINGECKO_API_KEY` | CoinGecko API key (optional, increases rate limit) | No |
