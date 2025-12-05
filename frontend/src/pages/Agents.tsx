import { useEffect, useState } from 'react';
import { getAgents, startAgent, stopAgent, pauseAgent, updateAgent, getAgentActivities, type AgentActivity } from '../services/api';
import type { Agent } from '../types';
import { StatusBadge } from '../components/StatusBadge';
import { Play, Pause, Square, Settings, Info, Save, X, Edit2, Activity } from 'lucide-react';
import { format } from 'date-fns';

export function Agents() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [editedConfig, setEditedConfig] = useState('');
  const [configError, setConfigError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [activities, setActivities] = useState<AgentActivity[]>([]);
  const [showActivities, setShowActivities] = useState(false);

  const fetchAgents = async () => {
    try {
      const data = await getAgents();
      setAgents(data);
    } catch (err) {
      console.error('Failed to load agents:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAgents();
  }, []);

  useEffect(() => {
    if (selectedAgent && showActivities) {
      getAgentActivities(selectedAgent.id, 30)
        .then(setActivities)
        .catch(console.error);
    }
  }, [selectedAgent, showActivities]);

  const handleStart = async (id: number) => {
    await startAgent(id);
    fetchAgents();
  };

  const handleStop = async (id: number) => {
    await stopAgent(id);
    fetchAgents();
  };

  const handlePause = async (id: number) => {
    await pauseAgent(id);
    fetchAgents();
  };

  const handleEditConfig = () => {
    if (selectedAgent) {
      setEditedConfig(JSON.stringify(selectedAgent.config, null, 2));
      setConfigError(null);
      setIsEditing(true);
    }
  };

  const handleCancelEdit = () => {
    setIsEditing(false);
    setEditedConfig('');
    setConfigError(null);
  };

  const handleSaveConfig = async () => {
    if (!selectedAgent) return;

    try {
      const parsedConfig = JSON.parse(editedConfig);
      setSaving(true);
      setConfigError(null);

      await updateAgent(selectedAgent.id, { config: parsedConfig });

      // Refresh agents list
      await fetchAgents();

      // Update selected agent with new config
      setSelectedAgent({ ...selectedAgent, config: parsedConfig });
      setIsEditing(false);
      setEditedConfig('');
    } catch (err) {
      if (err instanceof SyntaxError) {
        setConfigError('Invalid JSON format');
      } else {
        setConfigError('Failed to save configuration');
      }
      console.error('Failed to save config:', err);
    } finally {
      setSaving(false);
    }
  };

  // Format agent name for display
  const formatAgentName = (name: string) => {
    return name
      .split('_')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-slate-400">Loading agents...</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-white">Trading Agents</h2>
        <p className="text-slate-400">Manage and monitor your trading agents</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Agents List */}
        <div className="lg:col-span-2">
          <div className="card">
            <table className="w-full">
              <thead>
                <tr className="text-left text-slate-400 text-sm border-b border-slate-700">
                  <th className="pb-3 pr-4">Agent</th>
                  <th className="pb-3 pr-4">Type</th>
                  <th className="pb-3 pr-4">Status</th>
                  <th className="pb-3 pr-4">Last Run</th>
                  <th className="pb-3 pr-4">Active</th>
                  <th className="pb-3">Actions</th>
                </tr>
              </thead>
              <tbody>
                {agents.map((agent) => (
                  <tr
                    key={agent.id}
                    className={`border-b border-slate-700/50 cursor-pointer hover:bg-slate-700/30 ${
                      selectedAgent?.id === agent.id ? 'bg-slate-700/50' : ''
                    }`}
                    onClick={() => setSelectedAgent(agent)}
                  >
                    <td className="py-4 pr-4">
                      <div className="flex items-center gap-3">
                        <div className="p-2 bg-slate-700 rounded-lg">
                          <Settings className="w-4 h-4 text-primary-400" />
                        </div>
                        <div>
                          <p className="font-medium text-white">{formatAgentName(agent.name)}</p>
                          <p className="text-xs text-slate-400 truncate max-w-[200px]">
                            {agent.description}
                          </p>
                        </div>
                      </div>
                    </td>
                    <td className="py-4 pr-4 text-slate-300 capitalize">
                      {agent.agent_type.replace('_', ' ')}
                    </td>
                    <td className="py-4 pr-4">
                      <StatusBadge status={agent.status} size="sm" />
                    </td>
                    <td className="py-4 pr-4 text-sm">
                      {agent.last_run_at ? (
                        <span className="text-slate-300">
                          {format(new Date(agent.last_run_at), 'MMM d, HH:mm')}
                        </span>
                      ) : (
                        <span className="text-slate-500">Never</span>
                      )}
                    </td>
                    <td className="py-4 pr-4">
                      <span className={agent.is_active ? 'text-green-400' : 'text-slate-500'}>
                        {agent.is_active ? 'Yes' : 'No'}
                      </span>
                    </td>
                    <td className="py-4">
                      <div className="flex gap-2" onClick={(e) => e.stopPropagation()}>
                        {agent.status !== 'running' && (
                          <button
                            onClick={() => handleStart(agent.id)}
                            className="p-2 bg-green-600/20 text-green-400 rounded hover:bg-green-600/30"
                            title="Start"
                          >
                            <Play className="w-4 h-4" />
                          </button>
                        )}
                        {agent.status === 'running' && (
                          <>
                            <button
                              onClick={() => handlePause(agent.id)}
                              className="p-2 bg-yellow-600/20 text-yellow-400 rounded hover:bg-yellow-600/30"
                              title="Pause"
                            >
                              <Pause className="w-4 h-4" />
                            </button>
                            <button
                              onClick={() => handleStop(agent.id)}
                              className="p-2 bg-red-600/20 text-red-400 rounded hover:bg-red-600/30"
                              title="Stop"
                            >
                              <Square className="w-4 h-4" />
                            </button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Agent Details */}
        <div className="lg:col-span-1">
          {selectedAgent ? (
            <div className="card">
              <div className="flex items-center gap-3 mb-4">
                <Info className="w-5 h-5 text-primary-400" />
                <h3 className="text-lg font-semibold text-white">Agent Details</h3>
              </div>

              <div className="space-y-4">
                <div>
                  <p className="text-xs text-slate-400 mb-1">Name</p>
                  <p className="text-white font-medium">{formatAgentName(selectedAgent.name)}</p>
                </div>

                <div>
                  <p className="text-xs text-slate-400 mb-1">Type</p>
                  <p className="text-white capitalize">{selectedAgent.agent_type.replace('_', ' ')}</p>
                </div>

                <div>
                  <p className="text-xs text-slate-400 mb-1">Description</p>
                  <p className="text-slate-300 text-sm">{selectedAgent.description}</p>
                </div>

                <div>
                  <p className="text-xs text-slate-400 mb-1">Status</p>
                  <StatusBadge status={selectedAgent.status} />
                </div>

                <div>
                  <p className="text-xs text-slate-400 mb-1">Last Run</p>
                  <p className="text-slate-300 text-sm">
                    {selectedAgent.last_run_at
                      ? format(new Date(selectedAgent.last_run_at), 'MMM d, yyyy HH:mm')
                      : 'Never'}
                  </p>
                </div>

                <div>
                  <p className="text-xs text-slate-400 mb-1">Created</p>
                  <p className="text-slate-300 text-sm">
                    {format(new Date(selectedAgent.created_at), 'MMM d, yyyy HH:mm')}
                  </p>
                </div>

                {/* Activity Log Toggle */}
                <div>
                  <button
                    onClick={() => setShowActivities(!showActivities)}
                    className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors w-full ${
                      showActivities
                        ? 'bg-primary-600/20 text-primary-400 border border-primary-500'
                        : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                    }`}
                  >
                    <Activity className="w-4 h-4" />
                    {showActivities ? 'Hide Activity Log' : 'Show Activity Log'}
                  </button>
                </div>

                {/* Activity Log */}
                {showActivities && (
                  <div className="bg-slate-900 rounded-lg border border-slate-700 max-h-64 overflow-auto">
                    {activities.length === 0 ? (
                      <div className="p-4 text-center text-slate-500 text-sm">
                        No recent activity
                      </div>
                    ) : (
                      <div className="divide-y divide-slate-700">
                        {activities.map((activity) => (
                          <div key={activity.id} className="p-3 text-sm">
                            <div className="flex items-center justify-between mb-1">
                              <span className={`text-xs px-2 py-0.5 rounded ${
                                activity.activity_type === 'error' ? 'bg-red-500/20 text-red-400' :
                                activity.activity_type === 'cycle_end' ? 'bg-green-500/20 text-green-400' :
                                activity.activity_type === 'market_closed' ? 'bg-yellow-500/20 text-yellow-400' :
                                activity.activity_type === 'order_filled' ? 'bg-blue-500/20 text-blue-400' :
                                'bg-slate-600/50 text-slate-400'
                              }`}>
                                {activity.activity_type.replace(/_/g, ' ')}
                              </span>
                              <span className="text-xs text-slate-500">
                                {activity.created_at && format(new Date(activity.created_at), 'HH:mm:ss')}
                              </span>
                            </div>
                            <p className="text-slate-300">{activity.message}</p>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                <div>
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-xs text-slate-400">Configuration</p>
                    {!isEditing ? (
                      <button
                        onClick={handleEditConfig}
                        className="flex items-center gap-1 text-xs text-primary-400 hover:text-primary-300 transition-colors"
                      >
                        <Edit2 className="w-3 h-3" />
                        Edit
                      </button>
                    ) : (
                      <div className="flex items-center gap-2">
                        <button
                          onClick={handleSaveConfig}
                          disabled={saving}
                          className="flex items-center gap-1 text-xs text-green-400 hover:text-green-300 transition-colors disabled:opacity-50"
                        >
                          <Save className="w-3 h-3" />
                          {saving ? 'Saving...' : 'Save'}
                        </button>
                        <button
                          onClick={handleCancelEdit}
                          className="flex items-center gap-1 text-xs text-slate-400 hover:text-slate-300 transition-colors"
                        >
                          <X className="w-3 h-3" />
                          Cancel
                        </button>
                      </div>
                    )}
                  </div>
                  {configError && (
                    <p className="text-xs text-red-400 mb-2">{configError}</p>
                  )}
                  {isEditing ? (
                    <textarea
                      value={editedConfig}
                      onChange={(e) => setEditedConfig(e.target.value)}
                      className="w-full bg-slate-900 p-3 rounded-lg text-xs text-slate-300 font-mono border border-slate-600 focus:border-primary-500 focus:outline-none resize-none"
                      rows={15}
                      spellCheck={false}
                    />
                  ) : (
                    <pre className="bg-slate-900 p-3 rounded-lg text-xs text-slate-300 overflow-auto max-h-64">
                      {JSON.stringify(selectedAgent.config, null, 2)}
                    </pre>
                  )}
                </div>
              </div>
            </div>
          ) : (
            <div className="card flex items-center justify-center h-64 text-slate-400">
              Select an agent to view details
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
