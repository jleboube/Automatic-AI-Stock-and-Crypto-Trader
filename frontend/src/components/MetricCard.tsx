import { TrendingUp, TrendingDown, Minus } from 'lucide-react';
import type { ReactNode } from 'react';

interface MetricCardProps {
  title: string;
  value: string | number | null;
  subtitle?: string;
  icon?: ReactNode;
  trend?: 'up' | 'down' | 'neutral';
  valueColor?: 'default' | 'success' | 'danger' | 'warning';
}

export function MetricCard({
  title,
  value,
  subtitle,
  icon,
  trend,
  valueColor = 'default'
}: MetricCardProps) {
  const colorClasses = {
    default: 'text-white',
    success: 'text-green-400',
    danger: 'text-red-400',
    warning: 'text-yellow-400',
  };

  const TrendIcon = trend === 'up' ? TrendingUp : trend === 'down' ? TrendingDown : Minus;
  const trendColor = trend === 'up' ? 'text-green-400' : trend === 'down' ? 'text-red-400' : 'text-slate-400';

  return (
    <div className="card">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-slate-400 mb-1">{title}</p>
          <p className={`text-2xl font-bold ${colorClasses[valueColor]}`}>
            {value ?? '--'}
          </p>
          {subtitle && (
            <p className="text-xs text-slate-500 mt-1">{subtitle}</p>
          )}
        </div>
        <div className="flex flex-col items-end gap-2">
          {icon && (
            <div className="p-2 bg-slate-700 rounded-lg">
              {icon}
            </div>
          )}
          {trend && (
            <TrendIcon className={`w-4 h-4 ${trendColor}`} />
          )}
        </div>
      </div>
    </div>
  );
}
