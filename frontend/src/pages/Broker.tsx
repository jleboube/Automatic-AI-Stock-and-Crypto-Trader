import { useEffect, useState } from 'react';
import {
  Plug, PlugZap, DollarSign, TrendingUp, Briefcase, RefreshCw,
  Search, ShoppingCart, X, AlertCircle
} from 'lucide-react';
import {
  getBrokerStatus, connectBroker, disconnectBroker,
  getAccountSummary, getBrokerPositions, findPutSpread,
  getOpenOrders, cancelOrder,
  type BrokerStatus, type AccountSummary, type Position, type PutSpread
} from '../services/api';
import { MetricCard } from '../components/MetricCard';

export function Broker() {
  const [status, setStatus] = useState<BrokerStatus | null>(null);
  const [account, setAccount] = useState<AccountSummary | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [spread, setSpread] = useState<PutSpread | null>(null);
  const [orders, setOrders] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState(false);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchStatus = async () => {
    try {
      const data = await getBrokerStatus();
      setStatus(data);
      return data.connected;
    } catch (err) {
      console.error('Failed to get broker status:', err);
      return false;
    }
  };

  const fetchData = async () => {
    try {
      const [accountData, positionsData, ordersData] = await Promise.all([
        getAccountSummary().catch(() => null),
        getBrokerPositions().catch(() => []),
        getOpenOrders().catch(() => []),
      ]);
      setAccount(accountData);
      setPositions(positionsData);
      setOrders(ordersData);
      setError(null);
    } catch (err) {
      console.error('Failed to fetch broker data:', err);
    }
  };

  useEffect(() => {
    const init = async () => {
      setLoading(true);
      const connected = await fetchStatus();
      if (connected) {
        await fetchData();
      }
      setLoading(false);
    };
    init();

    const interval = setInterval(async () => {
      const connected = await fetchStatus();
      if (connected) {
        await fetchData();
      }
    }, 30000);

    return () => clearInterval(interval);
  }, []);

  const handleConnect = async () => {
    setConnecting(true);
    setError(null);
    try {
      await connectBroker();
      await fetchStatus();
      await fetchData();
    } catch (err: any) {
      setError(err.message || 'Failed to connect to IB');
    } finally {
      setConnecting(false);
    }
  };

  const handleDisconnect = async () => {
    try {
      await disconnectBroker();
      await fetchStatus();
      setAccount(null);
      setPositions([]);
      setOrders([]);
    } catch (err: any) {
      setError(err.message || 'Failed to disconnect');
    }
  };

  const handleFindSpread = async () => {
    setSearching(true);
    setError(null);
    try {
      const data = await findPutSpread();
      setSpread(data);
    } catch (err: any) {
      setError(err.message || 'No suitable spread found');
    } finally {
      setSearching(false);
    }
  };

  const handleCancelOrder = async (orderId: number) => {
    try {
      await cancelOrder(orderId);
      setOrders(orders.filter(o => o.order_id !== orderId));
    } catch (err: any) {
      setError(err.message || 'Failed to cancel order');
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-slate-400">Loading broker status...</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-white">Interactive Brokers</h2>
          <p className="text-slate-400">Connect and manage your IB account</p>
        </div>
        <button
          onClick={() => { fetchStatus().then(c => { if (c) fetchData(); }); }}
          className="btn bg-slate-700 hover:bg-slate-600 text-white flex items-center gap-2"
        >
          <RefreshCw className="w-4 h-4" />
          Refresh
        </button>
      </div>

      {error && (
        <div className="bg-red-900/50 border border-red-700 rounded-lg p-4 flex items-center gap-3">
          <AlertCircle className="w-5 h-5 text-red-400" />
          <p className="text-red-200">{error}</p>
        </div>
      )}

      {/* Connection Status */}
      <div className="card">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className={`p-3 rounded-lg ${status?.connected ? 'bg-green-600/20' : 'bg-slate-700'}`}>
              {status?.connected ? (
                <PlugZap className="w-6 h-6 text-green-400" />
              ) : (
                <Plug className="w-6 h-6 text-slate-400" />
              )}
            </div>
            <div>
              <h3 className="text-lg font-semibold text-white">
                {status?.connected ? 'Connected' : 'Not Connected'}
              </h3>
              <p className="text-slate-400 text-sm">
                {status ? `${status.host}:${status.port}` : 'IB Gateway / TWS'}
              </p>
            </div>
          </div>
          <div>
            {status?.connected ? (
              <button
                onClick={handleDisconnect}
                className="btn btn-danger"
              >
                Disconnect
              </button>
            ) : (
              <button
                onClick={handleConnect}
                disabled={connecting}
                className="btn btn-primary"
              >
                {connecting ? 'Connecting...' : 'Connect'}
              </button>
            )}
          </div>
        </div>

        {!status?.connected && (
          <div className="mt-4 p-4 bg-slate-900 rounded-lg">
            <p className="text-slate-300 text-sm mb-2">To connect:</p>
            <ol className="text-slate-400 text-sm space-y-1 list-decimal list-inside">
              <li>Open TWS or IB Gateway</li>
              <li>Go to Edit → Global Configuration → API → Settings</li>
              <li>Enable "Enable ActiveX and Socket Clients"</li>
              <li>Set Socket port to 7497 (paper) or 7496 (live)</li>
              <li>Click Connect above</li>
            </ol>
          </div>
        )}
      </div>

      {/* Account Summary */}
      {status?.connected && account && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <MetricCard
              title="Net Liquidation"
              value={`$${account.net_liquidation.toLocaleString()}`}
              icon={<DollarSign className="w-5 h-5 text-green-400" />}
            />
            <MetricCard
              title="Buying Power"
              value={`$${account.buying_power.toLocaleString()}`}
              icon={<Briefcase className="w-5 h-5 text-blue-400" />}
            />
            <MetricCard
              title="Unrealized P&L"
              value={`$${account.unrealized_pnl.toLocaleString()}`}
              valueColor={account.unrealized_pnl >= 0 ? 'success' : 'danger'}
              icon={<TrendingUp className="w-5 h-5 text-primary-400" />}
            />
            <MetricCard
              title="Realized P&L"
              value={`$${account.realized_pnl.toLocaleString()}`}
              valueColor={account.realized_pnl >= 0 ? 'success' : 'danger'}
              icon={<TrendingUp className="w-5 h-5 text-purple-400" />}
            />
          </div>

          {/* Positions */}
          <div className="card">
            <h3 className="text-lg font-semibold text-white mb-4">Positions</h3>
            {positions.length === 0 ? (
              <p className="text-slate-400 text-center py-8">No open positions</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="text-left text-slate-400 text-sm border-b border-slate-700">
                      <th className="pb-3 pr-4">Symbol</th>
                      <th className="pb-3 pr-4">Type</th>
                      <th className="pb-3 pr-4">Quantity</th>
                      <th className="pb-3 pr-4">Avg Cost</th>
                      <th className="pb-3 pr-4">Market Value</th>
                      <th className="pb-3">Unrealized P&L</th>
                    </tr>
                  </thead>
                  <tbody>
                    {positions.map((pos, i) => (
                      <tr key={i} className="border-b border-slate-700/50 text-sm">
                        <td className="py-3 pr-4 font-medium text-white">{pos.symbol}</td>
                        <td className="py-3 pr-4 text-slate-300">{pos.contract_type}</td>
                        <td className="py-3 pr-4 text-slate-300">{pos.quantity}</td>
                        <td className="py-3 pr-4 text-slate-300">${pos.avg_cost.toFixed(2)}</td>
                        <td className="py-3 pr-4 text-slate-300">${pos.market_value.toFixed(2)}</td>
                        <td className={`py-3 ${pos.unrealized_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                          ${pos.unrealized_pnl.toFixed(2)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Open Orders */}
          {orders.length > 0 && (
            <div className="card">
              <h3 className="text-lg font-semibold text-white mb-4">Open Orders</h3>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="text-left text-slate-400 text-sm border-b border-slate-700">
                      <th className="pb-3 pr-4">Order ID</th>
                      <th className="pb-3 pr-4">Symbol</th>
                      <th className="pb-3 pr-4">Action</th>
                      <th className="pb-3 pr-4">Quantity</th>
                      <th className="pb-3 pr-4">Type</th>
                      <th className="pb-3 pr-4">Status</th>
                      <th className="pb-3">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {orders.map((order) => (
                      <tr key={order.order_id} className="border-b border-slate-700/50 text-sm">
                        <td className="py-3 pr-4 text-slate-300">{order.order_id}</td>
                        <td className="py-3 pr-4 font-medium text-white">{order.symbol}</td>
                        <td className="py-3 pr-4 text-slate-300">{order.action}</td>
                        <td className="py-3 pr-4 text-slate-300">{order.quantity}</td>
                        <td className="py-3 pr-4 text-slate-300">{order.order_type}</td>
                        <td className="py-3 pr-4 text-slate-300">{order.status}</td>
                        <td className="py-3">
                          <button
                            onClick={() => handleCancelOrder(order.order_id)}
                            className="p-1 text-red-400 hover:text-red-300"
                          >
                            <X className="w-4 h-4" />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Find Put Spread */}
          <div className="card">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-lg font-semibold text-white">Put Spread Scanner</h3>
                <p className="text-slate-400 text-sm">Find optimal 25-wide put credit spread</p>
              </div>
              <button
                onClick={handleFindSpread}
                disabled={searching}
                className="btn btn-primary flex items-center gap-2"
              >
                <Search className="w-4 h-4" />
                {searching ? 'Searching...' : 'Find Spread'}
              </button>
            </div>

            {spread && (
              <div className="bg-slate-900 rounded-lg p-4">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                  <div>
                    <p className="text-xs text-slate-400">QQQ Price</p>
                    <p className="text-lg font-bold text-white">${spread.qqq_price.toFixed(2)}</p>
                  </div>
                  <div>
                    <p className="text-xs text-slate-400">Short Strike</p>
                    <p className="text-lg font-bold text-white">${spread.short_strike}</p>
                  </div>
                  <div>
                    <p className="text-xs text-slate-400">Long Strike</p>
                    <p className="text-lg font-bold text-white">${spread.long_strike}</p>
                  </div>
                  <div>
                    <p className="text-xs text-slate-400">Expiration</p>
                    <p className="text-lg font-bold text-white">{spread.expiration}</p>
                  </div>
                </div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                  <div>
                    <p className="text-xs text-slate-400">Net Credit</p>
                    <p className="text-lg font-bold text-green-400">${spread.net_credit.toFixed(2)}</p>
                  </div>
                  <div>
                    <p className="text-xs text-slate-400">Max Risk</p>
                    <p className="text-lg font-bold text-red-400">${spread.max_risk.toFixed(2)}</p>
                  </div>
                  <div>
                    <p className="text-xs text-slate-400">Short Delta</p>
                    <p className="text-lg font-bold text-white">{spread.short_delta.toFixed(3)}</p>
                  </div>
                  <div>
                    <p className="text-xs text-slate-400">Return on Risk</p>
                    <p className="text-lg font-bold text-white">
                      {((spread.net_credit / spread.max_risk) * 100).toFixed(1)}%
                    </p>
                  </div>
                </div>
                <button className="btn btn-success flex items-center gap-2">
                  <ShoppingCart className="w-4 h-4" />
                  Place Order (Manual Review Required)
                </button>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
