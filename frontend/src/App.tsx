import { Routes, Route } from 'react-router-dom';
import { useCallback } from 'react';
import { Layout } from './components/Layout';
import { Dashboard } from './pages/Dashboard';
import { Agents } from './pages/Agents';
import { Trades } from './pages/Trades';
import { Orchestrator } from './pages/Orchestrator';
import { Broker } from './pages/Broker';
import { GemHunter } from './pages/GemHunter';
import { CryptoHunter } from './pages/CryptoHunter';
import { useWebSocket } from './hooks/useWebSocket';
import type { WebSocketMessage } from './types';

function App() {
  const handleMessage = useCallback((msg: WebSocketMessage) => {
    // Handle global WebSocket messages here if needed
    console.log('WebSocket message:', msg);
  }, []);

  const { isConnected: wsConnected } = useWebSocket(handleMessage);

  return (
    <Routes>
      <Route path="/" element={<Layout isConnected={wsConnected} />}>
        <Route index element={<Dashboard />} />
        <Route path="agents" element={<Agents />} />
        <Route path="trades" element={<Trades />} />
        <Route path="orchestrator" element={<Orchestrator />} />
        <Route path="broker" element={<Broker />} />
        <Route path="gem-hunter" element={<GemHunter />} />
        <Route path="crypto" element={<CryptoHunter />} />
      </Route>
    </Routes>
  );
}

export default App;
