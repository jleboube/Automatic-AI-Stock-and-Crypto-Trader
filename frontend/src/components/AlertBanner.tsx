import { AlertTriangle, AlertCircle, Info, CheckCircle, X } from 'lucide-react';
import type { Alert } from '../types';

interface AlertBannerProps {
  alert: Alert;
  onDismiss: () => void;
}

const alertStyles = {
  error: {
    bg: 'bg-red-900/50 border-red-700',
    icon: AlertCircle,
    iconColor: 'text-red-400',
  },
  warning: {
    bg: 'bg-yellow-900/50 border-yellow-700',
    icon: AlertTriangle,
    iconColor: 'text-yellow-400',
  },
  info: {
    bg: 'bg-blue-900/50 border-blue-700',
    icon: Info,
    iconColor: 'text-blue-400',
  },
  success: {
    bg: 'bg-green-900/50 border-green-700',
    icon: CheckCircle,
    iconColor: 'text-green-400',
  },
};

export function AlertBanner({ alert, onDismiss }: AlertBannerProps) {
  const style = alertStyles[alert.level as keyof typeof alertStyles] || alertStyles.info;
  const Icon = style.icon;

  return (
    <div className={`${style.bg} border rounded-lg p-4 flex items-start gap-3`}>
      <Icon className={`w-5 h-5 ${style.iconColor} flex-shrink-0 mt-0.5`} />
      <div className="flex-1">
        <p className="text-white font-medium">{alert.type}</p>
        <p className="text-slate-300 text-sm">{alert.message}</p>
      </div>
      <button
        onClick={onDismiss}
        className="text-slate-400 hover:text-white transition-colors"
      >
        <X className="w-5 h-5" />
      </button>
    </div>
  );
}

interface AlertsListProps {
  alerts: Alert[];
  onDismiss: (index: number) => void;
}

export function AlertsList({ alerts, onDismiss }: AlertsListProps) {
  if (alerts.length === 0) return null;

  return (
    <div className="space-y-2">
      {alerts.map((alert, index) => (
        <AlertBanner
          key={`${alert.timestamp}-${index}`}
          alert={alert}
          onDismiss={() => onDismiss(index)}
        />
      ))}
    </div>
  );
}
