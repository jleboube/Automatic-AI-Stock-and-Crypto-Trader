import { useEffect, useState } from 'react';
import { format } from 'date-fns';
import {
  Zap,
  Play,
  AlertOctagon,
  RefreshCw,
  Clock,
  Activity,
  Search,
  Check,
  X,
  Send,
  FileText,
  AlertTriangle,
  Sun,
  Moon,
  Sunrise
} from 'lucide-react';
import {
  getOrchestratorStatus,
  executeWeekly,
  emergencyShutdown,
  analyzeMarket,
  getRecommendations,
  approveRecommendation,
  rejectRecommendation,
  executeRecommendation,
  type TradeRecommendation,
  type AnalyzeResult,
  type MarketHoursStatus
} from '../services/api';
import { RegimeBadge } from '../components/StatusBadge';

interface OrchestratorStatus {
  current_regime: string | null;
  regime_started_at: string | null;
  market_data: {
    qqq_price: number;
    vix: number;
    iv_7day_atm: number;
    timestamp: string;
  };
  market_hours: MarketHoursStatus;
  active_agents: string[];
  total_agents: number;
  pending_recommendations: number;
}

const getSessionIcon = (session: string) => {
  switch (session) {
    case 'regular':
      return Sun;
    case 'pre_market':
    case 'after_hours':
      return Sunrise;
    default:
      return Moon;
  }
};

const getSessionLabel = (session: string) => {
  const labels: Record<string, string> = {
    closed: 'Closed',
    pre_market: 'Pre-Market',
    regular: 'Regular Hours',
    after_hours: 'After-Hours',
    weekend: 'Weekend',
    holiday: 'Holiday'
  };
  return labels[session] || session;
};

const getSessionColor = (session: string) => {
  switch (session) {
    case 'regular':
      return 'text-green-400';
    case 'pre_market':
    case 'after_hours':
      return 'text-yellow-400';
    default:
      return 'text-slate-400';
  }
};

export function Orchestrator() {
  const [status, setStatus] = useState<OrchestratorStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [shutdownConfirm, setShutdownConfirm] = useState(false);
  const [lastAnalysisResult, setLastAnalysisResult] = useState<AnalyzeResult | null>(null);
  const [recommendations, setRecommendations] = useState<TradeRecommendation[]>([]);
  const [selectedRecommendation, setSelectedRecommendation] = useState<TradeRecommendation | null>(null);
  const [actionInProgress, setActionInProgress] = useState<number | null>(null);
  const [showHistory, setShowHistory] = useState(false);

  const fetchStatus = async () => {
    try {
      const data = await getOrchestratorStatus();
      setStatus(data);
    } catch (err) {
      console.error('Failed to load orchestrator status:', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchRecommendations = async () => {
    try {
      const data = await getRecommendations(!showHistory);
      setRecommendations(data);
    } catch (err) {
      console.error('Failed to load recommendations:', err);
    }
  };

  useEffect(() => {
    fetchStatus();
    fetchRecommendations();
    const interval = setInterval(() => {
      fetchStatus();
      fetchRecommendations();
    }, 10000);
    return () => clearInterval(interval);
  }, [showHistory]);

  const handleAnalyze = async () => {
    setAnalyzing(true);
    try {
      const result = await analyzeMarket();
      setLastAnalysisResult(result);
      fetchRecommendations();
      fetchStatus();
    } catch (err) {
      console.error('Analysis failed:', err);
    } finally {
      setAnalyzing(false);
    }
  };

  const handleExecuteWeekly = async () => {
    setExecuting(true);
    try {
      await executeWeekly();
      fetchStatus();
    } catch (err) {
      console.error('Execution failed:', err);
    } finally {
      setExecuting(false);
    }
  };

  const handleShutdown = async () => {
    try {
      await emergencyShutdown();
      setShutdownConfirm(false);
      fetchStatus();
    } catch (err) {
      console.error('Shutdown failed:', err);
    }
  };

  const handleApprove = async (id: number) => {
    setActionInProgress(id);
    try {
      await approveRecommendation(id);
      fetchRecommendations();
    } catch (err) {
      console.error('Approve failed:', err);
    } finally {
      setActionInProgress(null);
    }
  };

  const handleReject = async (id: number) => {
    setActionInProgress(id);
    try {
      await rejectRecommendation(id, 'User rejected');
      fetchRecommendations();
    } catch (err) {
      console.error('Reject failed:', err);
    } finally {
      setActionInProgress(null);
    }
  };

  const handleExecute = async (id: number) => {
    setActionInProgress(id);
    try {
      await executeRecommendation(id);
      fetchRecommendations();
      fetchStatus();
    } catch (err) {
      console.error('Execute failed:', err);
    } finally {
      setActionInProgress(null);
    }
  };

  const getStatusBadge = (status: string) => {
    const styles: Record<string, string> = {
      pending: 'bg-yellow-600/20 text-yellow-400',
      approved: 'bg-blue-600/20 text-blue-400',
      rejected: 'bg-red-600/20 text-red-400',
      executed: 'bg-green-600/20 text-green-400',
      expired: 'bg-slate-600/20 text-slate-400'
    };
    return styles[status] || 'bg-slate-600/20 text-slate-400';
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-slate-400">Loading orchestrator status...</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-white">Orchestrator</h2>
          <p className="text-slate-400">Control center for the trading system</p>
        </div>
        <button
          onClick={() => { fetchStatus(); fetchRecommendations(); }}
          className="btn bg-slate-700 hover:bg-slate-600 text-white flex items-center gap-2"
        >
          <RefreshCw className="w-4 h-4" />
          Refresh
        </button>
      </div>

      {/* Market Hours Banner */}
      {status?.market_hours && (
        <div className={`p-4 rounded-lg border ${
          status.market_hours.is_open
            ? 'bg-green-900/20 border-green-700'
            : status.market_hours.can_trade_stocks
            ? 'bg-yellow-900/20 border-yellow-700'
            : 'bg-slate-800/50 border-slate-700'
        }`}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              {(() => {
                const Icon = getSessionIcon(status.market_hours.session);
                return <Icon className={`w-6 h-6 ${getSessionColor(status.market_hours.session)}`} />;
              })()}
              <div>
                <div className={`font-semibold ${getSessionColor(status.market_hours.session)}`}>
                  {getSessionLabel(status.market_hours.session)}
                </div>
                <div className="text-slate-400 text-sm">
                  {status.market_hours.current_time_et}
                </div>
              </div>
            </div>
            <div className="flex gap-6 text-sm">
              <div className="text-center">
                <div className="text-slate-400">Stocks</div>
                <div className={status.market_hours.can_trade_stocks ? 'text-green-400' : 'text-red-400'}>
                  {status.market_hours.can_trade_stocks ? 'Available' : 'Closed'}
                </div>
              </div>
              <div className="text-center">
                <div className="text-slate-400">Options</div>
                <div className={status.market_hours.can_trade_options ? 'text-green-400' : 'text-red-400'}>
                  {status.market_hours.can_trade_options ? 'Available' : 'Closed'}
                </div>
              </div>
              {status.market_hours.time_until_open && (
                <div className="text-center">
                  <div className="text-slate-400">Opens In</div>
                  <div className="text-white">{status.market_hours.time_until_open}</div>
                </div>
              )}
              {status.market_hours.time_until_close && (
                <div className="text-center">
                  <div className="text-slate-400">Closes In</div>
                  <div className="text-white">{status.market_hours.time_until_close}</div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Status Overview */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Current State */}
        <div className="card">
          <div className="flex items-center gap-3 mb-4">
            <Zap className="w-5 h-5 text-primary-400" />
            <h3 className="text-lg font-semibold text-white">Current State</h3>
          </div>

          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-slate-400">Regime</span>
              <RegimeBadge regime={status?.current_regime || null} />
            </div>

            {status?.regime_started_at && (
              <div className="flex items-center justify-between">
                <span className="text-slate-400">Regime Started</span>
                <span className="text-white">
                  {format(new Date(status.regime_started_at), 'MMM d, yyyy HH:mm')}
                </span>
              </div>
            )}

            <div className="flex items-center justify-between">
              <span className="text-slate-400">Active Agents</span>
              <span className="text-white">
                {status?.active_agents.length || 0} / {status?.total_agents || 0}
              </span>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-slate-400">Pending Recommendations</span>
              <span className={`font-semibold ${(status?.pending_recommendations || 0) > 0 ? 'text-yellow-400' : 'text-slate-400'}`}>
                {status?.pending_recommendations || 0}
              </span>
            </div>

            {status?.active_agents && status.active_agents.length > 0 && (
              <div>
                <span className="text-slate-400 text-sm">Running:</span>
                <div className="flex flex-wrap gap-2 mt-2">
                  {status.active_agents.map((agent) => (
                    <span
                      key={agent}
                      className="px-2 py-1 bg-green-600/20 text-green-400 rounded text-xs"
                    >
                      {agent}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Market Data */}
        <div className="card">
          <div className="flex items-center gap-3 mb-4">
            <Activity className="w-5 h-5 text-primary-400" />
            <h3 className="text-lg font-semibold text-white">Market Data</h3>
          </div>

          {status?.market_data && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-slate-400">QQQ Price</span>
                <span className="text-white text-xl font-bold">
                  ${status.market_data.qqq_price.toFixed(2)}
                </span>
              </div>

              <div className="flex items-center justify-between">
                <span className="text-slate-400">VIX</span>
                <span className={`text-xl font-bold ${
                  status.market_data.vix > 30 ? 'text-red-400' : 'text-white'
                }`}>
                  {status.market_data.vix.toFixed(2)}
                </span>
              </div>

              <div className="flex items-center justify-between">
                <span className="text-slate-400">7-Day ATM IV</span>
                <span className="text-white">{status.market_data.iv_7day_atm.toFixed(1)}%</span>
              </div>

              <div className="flex items-center justify-between">
                <span className="text-slate-400">Last Update</span>
                <span className="text-slate-300 text-sm">
                  {format(new Date(status.market_data.timestamp), 'HH:mm:ss')}
                </span>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Actions */}
      <div className="card">
        <div className="flex items-center gap-3 mb-4">
          <Clock className="w-5 h-5 text-primary-400" />
          <h3 className="text-lg font-semibold text-white">Actions</h3>
        </div>

        <div className="flex flex-wrap gap-4">
          <button
            onClick={handleAnalyze}
            disabled={analyzing}
            className="btn btn-primary flex items-center gap-2"
          >
            <Search className="w-4 h-4" />
            {analyzing ? 'Analyzing...' : 'Analyze Market'}
          </button>

          <button
            onClick={handleExecuteWeekly}
            disabled={executing}
            className="btn bg-amber-600 hover:bg-amber-700 text-white flex items-center gap-2"
          >
            <Play className="w-4 h-4" />
            {executing ? 'Executing...' : 'Execute Weekly (Direct)'}
          </button>

          {!shutdownConfirm ? (
            <button
              onClick={() => setShutdownConfirm(true)}
              className="btn btn-danger flex items-center gap-2"
            >
              <AlertOctagon className="w-4 h-4" />
              Emergency Shutdown
            </button>
          ) : (
            <div className="flex items-center gap-2">
              <span className="text-red-400">Are you sure?</span>
              <button onClick={handleShutdown} className="btn btn-danger">
                Yes, Shutdown
              </button>
              <button
                onClick={() => setShutdownConfirm(false)}
                className="btn bg-slate-700 hover:bg-slate-600 text-white"
              >
                Cancel
              </button>
            </div>
          )}
        </div>

        <div className="mt-4 p-3 bg-blue-900/30 border border-blue-700 rounded-lg">
          <div className="flex items-start gap-2">
            <AlertTriangle className="w-5 h-5 text-blue-400 mt-0.5" />
            <div className="text-sm">
              <p className="text-blue-300 font-medium">Recommended Workflow:</p>
              <p className="text-blue-200/80">
                Click "Analyze Market" to generate trade recommendations for your review.
                Review each recommendation below and Approve/Reject before executing.
                "Execute Weekly (Direct)" bypasses the approval workflow.
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Last Analysis Result */}
      {lastAnalysisResult && (
        <div className="card">
          <div className="flex items-center gap-3 mb-4">
            <Search className="w-5 h-5 text-green-400" />
            <h3 className="text-lg font-semibold text-white">Latest Analysis</h3>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            <div className="bg-slate-800 p-3 rounded-lg">
              <div className="text-slate-400 text-xs">Regime</div>
              <div className="text-white font-medium">{lastAnalysisResult.regime}</div>
            </div>
            <div className="bg-slate-800 p-3 rounded-lg">
              <div className="text-slate-400 text-xs">QQQ Price</div>
              <div className="text-white font-medium">${lastAnalysisResult.market_data.qqq_price.toFixed(2)}</div>
            </div>
            <div className="bg-slate-800 p-3 rounded-lg">
              <div className="text-slate-400 text-xs">Data Source</div>
              <div className={`font-medium ${
                lastAnalysisResult.market_data.source === 'live' ? 'text-green-400' :
                lastAnalysisResult.market_data.source === 'delayed' ? 'text-yellow-400' :
                'text-orange-400'
              }`}>
                {lastAnalysisResult.market_data.source === 'live' ? '● Live' :
                 lastAnalysisResult.market_data.source === 'delayed' ? '● Delayed' :
                 '○ Mock'}
              </div>
            </div>
            <div className="bg-slate-800 p-3 rounded-lg">
              <div className="text-slate-400 text-xs">Recommendations</div>
              <div className="text-white font-medium">{lastAnalysisResult.recommendations_count}</div>
            </div>
          </div>

          {lastAnalysisResult.recommendations_count === 0 && (
            <div className="text-slate-400 text-sm">
              No trade opportunities found matching current criteria.
            </div>
          )}
        </div>
      )}

      {/* Pending Recommendations */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <FileText className="w-5 h-5 text-yellow-400" />
            <h3 className="text-lg font-semibold text-white">Trade Recommendations</h3>
          </div>
          <button
            onClick={() => setShowHistory(!showHistory)}
            className="text-sm text-slate-400 hover:text-white"
          >
            {showHistory ? 'Show Pending Only' : 'Show All History'}
          </button>
        </div>

        {recommendations.length === 0 ? (
          <div className="text-slate-400 text-center py-8">
            No {showHistory ? '' : 'pending '}recommendations.
            {!showHistory && ' Click "Analyze Market" to generate new recommendations.'}
          </div>
        ) : (
          <div className="space-y-4">
            {recommendations.map((rec) => (
              <div
                key={rec.id}
                className={`border rounded-lg p-4 ${
                  selectedRecommendation?.id === rec.id
                    ? 'border-primary-500 bg-slate-800/50'
                    : 'border-slate-700 hover:border-slate-600'
                }`}
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-2">
                      <span className={`px-2 py-0.5 rounded text-xs ${getStatusBadge(rec.status)}`}>
                        {rec.status.toUpperCase()}
                      </span>
                      <span className="text-white font-medium">
                        {rec.action.replace(/_/g, ' ').toUpperCase()}
                      </span>
                      <span className="text-slate-400 text-sm">
                        {rec.symbol} {rec.trade_type}
                      </span>
                    </div>

                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm mb-3">
                      {rec.short_strike && (
                        <div>
                          <span className="text-slate-400">Short Strike:</span>
                          <span className="text-white ml-2">${rec.short_strike}</span>
                        </div>
                      )}
                      {rec.long_strike && (
                        <div>
                          <span className="text-slate-400">Long Strike:</span>
                          <span className="text-white ml-2">${rec.long_strike}</span>
                        </div>
                      )}
                      {rec.contracts && (
                        <div>
                          <span className="text-slate-400">Contracts:</span>
                          <span className="text-white ml-2">{rec.contracts}</span>
                        </div>
                      )}
                      {rec.expiration && (
                        <div>
                          <span className="text-slate-400">Expiration:</span>
                          <span className="text-white ml-2">{rec.expiration}</span>
                        </div>
                      )}
                      {rec.estimated_credit && (
                        <div>
                          <span className="text-slate-400">Est. Credit:</span>
                          <span className="text-green-400 ml-2">${rec.estimated_credit.toFixed(2)}</span>
                        </div>
                      )}
                      {rec.max_risk && (
                        <div>
                          <span className="text-slate-400">Max Risk:</span>
                          <span className="text-red-400 ml-2">${rec.max_risk.toFixed(0)}</span>
                        </div>
                      )}
                      {rec.short_delta && (
                        <div>
                          <span className="text-slate-400">Short Delta:</span>
                          <span className="text-white ml-2">{Math.abs(rec.short_delta).toFixed(3)}</span>
                        </div>
                      )}
                      <div>
                        <span className="text-slate-400">QQQ:</span>
                        <span className="text-white ml-2">${rec.qqq_price.toFixed(2)}</span>
                      </div>
                    </div>

                    {selectedRecommendation?.id === rec.id && rec.reasoning && (
                      <div className="mt-3 p-3 bg-slate-900 rounded text-sm">
                        <div className="text-slate-400 font-medium mb-2">Analysis:</div>
                        <pre className="text-slate-300 whitespace-pre-wrap font-sans">
                          {rec.reasoning}
                        </pre>
                        {rec.risk_assessment && (
                          <>
                            <div className="text-slate-400 font-medium mt-4 mb-2">Risk Assessment:</div>
                            <pre className="text-slate-300 whitespace-pre-wrap font-sans">
                              {rec.risk_assessment}
                            </pre>
                          </>
                        )}
                      </div>
                    )}

                    <div className="flex items-center gap-2 mt-3 text-xs text-slate-500">
                      <span>Created: {rec.created_at ? format(new Date(rec.created_at), 'MMM d HH:mm') : 'N/A'}</span>
                      {rec.expires_at && rec.status === 'pending' && (
                        <span>| Expires: {format(new Date(rec.expires_at), 'MMM d HH:mm')}</span>
                      )}
                      {rec.order_id && (
                        <span>| Order ID: {rec.order_id}</span>
                      )}
                    </div>
                  </div>

                  <div className="flex flex-col gap-2 ml-4">
                    <button
                      onClick={() => setSelectedRecommendation(
                        selectedRecommendation?.id === rec.id ? null : rec
                      )}
                      className="text-xs text-slate-400 hover:text-white"
                    >
                      {selectedRecommendation?.id === rec.id ? 'Hide Details' : 'View Details'}
                    </button>

                    {rec.status === 'pending' && (
                      <>
                        <button
                          onClick={() => handleApprove(rec.id)}
                          disabled={actionInProgress === rec.id}
                          className="btn bg-green-600 hover:bg-green-700 text-white text-xs py-1 px-3 flex items-center gap-1"
                        >
                          <Check className="w-3 h-3" />
                          Approve
                        </button>
                        <button
                          onClick={() => handleReject(rec.id)}
                          disabled={actionInProgress === rec.id}
                          className="btn bg-red-600 hover:bg-red-700 text-white text-xs py-1 px-3 flex items-center gap-1"
                        >
                          <X className="w-3 h-3" />
                          Reject
                        </button>
                      </>
                    )}

                    {rec.status === 'approved' && (
                      <button
                        onClick={() => handleExecute(rec.id)}
                        disabled={actionInProgress === rec.id}
                        className="btn bg-blue-600 hover:bg-blue-700 text-white text-xs py-1 px-3 flex items-center gap-1"
                      >
                        <Send className="w-3 h-3" />
                        Execute
                      </button>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Schedule Info */}
      <div className="card bg-slate-800/50">
        <h3 className="text-lg font-semibold text-white mb-4">Weekly Schedule</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
          <div>
            <p className="text-slate-400 mb-2">Recommended Workflow:</p>
            <ul className="space-y-1 text-slate-300">
              <li>1. Click "Analyze Market" before market close</li>
              <li>2. Review generated recommendations</li>
              <li>3. Approve trades you want to execute</li>
              <li>4. Click "Execute" on approved trades</li>
              <li>5. Monitor positions in Broker page</li>
            </ul>
          </div>
          <div>
            <p className="text-slate-400 mb-2">Regime Actions:</p>
            <ul className="space-y-1 text-slate-300">
              <li><span className="text-green-400">Normal Bull:</span> Open put credit spread</li>
              <li><span className="text-red-400">Defense:</span> Close losing spread</li>
              <li><span className="text-yellow-400">Recovery:</span> Sell calls, hold anchor</li>
              <li><span className="text-blue-400">Complete:</span> Close recovery, reset</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
