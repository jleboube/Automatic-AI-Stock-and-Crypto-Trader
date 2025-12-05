import { NavLink, Outlet } from 'react-router-dom';
import { LayoutDashboard, Bot, LineChart, Zap, Wifi, WifiOff, Plug, Target, Bitcoin } from 'lucide-react';

interface LayoutProps {
  isConnected: boolean;
}

interface NavSection {
  title?: string;
  items: { to: string; icon: typeof LayoutDashboard; label: string }[];
}

const navSections: NavSection[] = [
  {
    items: [
      { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
    ],
  },
  {
    title: 'Markets',
    items: [
      { to: '/agents', icon: Bot, label: 'Agents' },
      { to: '/trades', icon: LineChart, label: 'Trades' },
      { to: '/orchestrator', icon: Zap, label: 'Orchestrator' },
      { to: '/broker', icon: Plug, label: 'IB Broker' },
      { to: '/gem-hunter', icon: Target, label: 'Gem Hunter' },
    ],
  },
  {
    title: 'Crypto',
    items: [
      { to: '/crypto', icon: Bitcoin, label: 'Crypto Hunter' },
    ],
  },
];

export function Layout({ isConnected }: LayoutProps) {
  return (
    <div className="min-h-screen bg-slate-900">
      {/* Header */}
      <header className="bg-slate-800 border-b border-slate-700 px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-primary-600 rounded-lg">
              <Zap className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-white">QQQQ Agents</h1>
              <p className="text-xs text-slate-400">Options Trading Platform</p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              {isConnected ? (
                <>
                  <Wifi className="w-4 h-4 text-green-400" />
                  <span className="text-sm text-green-400">Connected</span>
                </>
              ) : (
                <>
                  <WifiOff className="w-4 h-4 text-red-400" />
                  <span className="text-sm text-red-400">Disconnected</span>
                </>
              )}
            </div>
          </div>
        </div>
      </header>

      <div className="flex">
        {/* Sidebar */}
        <nav className="w-64 bg-slate-800 border-r border-slate-700 min-h-[calc(100vh-73px)]">
          <div className="p-4 space-y-4">
            {navSections.map((section, sectionIdx) => (
              <div key={sectionIdx}>
                {section.title && (
                  <div className="px-4 py-2 text-xs font-semibold text-slate-500 uppercase tracking-wider">
                    {section.title}
                  </div>
                )}
                <div className="space-y-1">
                  {section.items.map((item) => (
                    <NavLink
                      key={item.to}
                      to={item.to}
                      className={({ isActive }) =>
                        `flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
                          isActive
                            ? 'bg-primary-600 text-white'
                            : 'text-slate-300 hover:bg-slate-700 hover:text-white'
                        }`
                      }
                    >
                      <item.icon className="w-5 h-5" />
                      <span className="font-medium">{item.label}</span>
                    </NavLink>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </nav>

        {/* Main Content */}
        <main className="flex-1 p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
