import type { AgentStatus, RegimeType } from '../types';

interface StatusBadgeProps {
  status: AgentStatus | string;
  size?: 'sm' | 'md';
}

const statusColors: Record<string, string> = {
  idle: 'bg-slate-600 text-slate-200',
  running: 'bg-green-600 text-green-100',
  paused: 'bg-yellow-600 text-yellow-100',
  error: 'bg-red-600 text-red-100',
  stopped: 'bg-slate-700 text-slate-300',
  open: 'bg-blue-600 text-blue-100',
  closed: 'bg-slate-600 text-slate-200',
  expired: 'bg-slate-700 text-slate-300',
};

export function StatusBadge({ status, size = 'md' }: StatusBadgeProps) {
  const colorClass = statusColors[status] || 'bg-slate-600 text-slate-200';
  const sizeClass = size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-3 py-1 text-sm';

  return (
    <span className={`${colorClass} ${sizeClass} rounded-full font-medium capitalize`}>
      {status}
    </span>
  );
}

interface RegimeBadgeProps {
  regime: RegimeType | string | null;
}

const regimeColors: Record<string, string> = {
  normal_bull: 'bg-green-600 text-green-100',
  defense_trigger: 'bg-red-600 text-red-100',
  recovery_mode: 'bg-yellow-600 text-yellow-100',
  recovery_complete: 'bg-blue-600 text-blue-100',
};

const regimeLabels: Record<string, string> = {
  normal_bull: 'Normal Bull',
  defense_trigger: 'Defense Trigger',
  recovery_mode: 'Recovery Mode',
  recovery_complete: 'Recovery Complete',
};

export function RegimeBadge({ regime }: RegimeBadgeProps) {
  if (!regime) return null;

  const colorClass = regimeColors[regime] || 'bg-slate-600 text-slate-200';
  const label = regimeLabels[regime] || regime;

  return (
    <span className={`${colorClass} px-3 py-1 rounded-full text-sm font-medium`}>
      {label}
    </span>
  );
}
