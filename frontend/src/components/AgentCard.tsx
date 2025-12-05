import { Play, Pause, Square, Settings, TrendingUp, TrendingDown, Activity } from 'lucide-react';
import type { AgentStatusSummary } from '../types';
import { StatusBadge } from './StatusBadge';

interface AgentCardProps {
  agent: AgentStatusSummary;
  onStart: (id: number) => void;
  onStop: (id: number) => void;
  onPause: (id: number) => void;
}

const agentIcons: Record<string, typeof Activity> = {
  short_put: TrendingDown,
  short_call: TrendingDown,
  long_call: TrendingUp,
  long_put: TrendingUp,
  risk: Activity,
  orchestrator: Settings,
};

export function AgentCard({ agent, onStart, onStop, onPause }: AgentCardProps) {
  const Icon = agentIcons[agent.agent_type] || Activity;
  const isRunning = agent.status === 'running';
  const isPaused = agent.status === 'paused';

  return (
    <div className="card hover:border-slate-600 transition-colors">
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-slate-700 rounded-lg">
            <Icon className="w-5 h-5 text-primary-400" />
          </div>
          <div>
            <h3 className="font-semibold text-white">{agent.agent_name}</h3>
            <p className="text-xs text-slate-400 capitalize">{agent.agent_type.replace('_', ' ')}</p>
          </div>
        </div>
        <StatusBadge status={agent.status} size="sm" />
      </div>

      <div className="grid grid-cols-2 gap-4 mb-4">
        <div>
          <p className="text-xs text-slate-400">Total Runs</p>
          <p className="text-lg font-semibold text-white">{agent.total_runs}</p>
        </div>
        <div>
          <p className="text-xs text-slate-400">Success Rate</p>
          <p className="text-lg font-semibold text-white">
            {agent.total_runs > 0
              ? Math.round((agent.successful_runs / agent.total_runs) * 100)
              : 0}%
          </p>
        </div>
        <div>
          <p className="text-xs text-slate-400">Open Trades</p>
          <p className="text-lg font-semibold text-white">{agent.open_trades}</p>
        </div>
        <div>
          <p className="text-xs text-slate-400">Total P&L</p>
          <p className={`text-lg font-semibold ${agent.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            ${agent.total_pnl.toFixed(2)}
          </p>
        </div>
      </div>

      <div className="flex gap-2">
        {!isRunning && (
          <button
            onClick={() => onStart(agent.agent_id)}
            className="flex-1 btn btn-success flex items-center justify-center gap-2"
          >
            <Play className="w-4 h-4" />
            Start
          </button>
        )}
        {isRunning && (
          <>
            <button
              onClick={() => onPause(agent.agent_id)}
              className="flex-1 btn bg-yellow-600 hover:bg-yellow-700 text-white flex items-center justify-center gap-2"
            >
              <Pause className="w-4 h-4" />
              Pause
            </button>
            <button
              onClick={() => onStop(agent.agent_id)}
              className="flex-1 btn btn-danger flex items-center justify-center gap-2"
            >
              <Square className="w-4 h-4" />
              Stop
            </button>
          </>
        )}
        {isPaused && (
          <>
            <button
              onClick={() => onStart(agent.agent_id)}
              className="flex-1 btn btn-success flex items-center justify-center gap-2"
            >
              <Play className="w-4 h-4" />
              Resume
            </button>
            <button
              onClick={() => onStop(agent.agent_id)}
              className="flex-1 btn btn-danger flex items-center justify-center gap-2"
            >
              <Square className="w-4 h-4" />
              Stop
            </button>
          </>
        )}
      </div>
    </div>
  );
}
