import React from 'react';
import { NavLink } from 'react-router-dom';
import { Monitor, Map, Train, TrendingUp, CheckCircle2 } from 'lucide-react';

export default function Sidebar({ health, lastWeatherUpdate }) {
  const navItems = [
    { name: 'Control Center', path: '/', icon: Monitor },
    { name: 'Network Map', path: '/map', icon: Map },
    { name: 'Schedule View', path: '/schedule', icon: Train },
    { name: 'Trends & Surges', path: '/trends', icon: TrendingUp },
  ];

  const isHealthy = health?.status === 'ok';

  return (
    <aside className="w-64 h-full bg-slate-900 border-r border-slate-800/80 text-slate-300 flex flex-col fixed left-0 top-0 z-50 select-none">
      {/* Brand Header */}
      <div className="p-6 border-b border-slate-800/80">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-slate-800 border border-slate-700/60 flex items-center justify-center text-cyan-400 shrink-0">
            <Train className="w-5 h-5" />
          </div>
          <div>
            <h1 className="text-base font-bold tracking-tight text-white">
              MetroMind
            </h1>
            <p className="text-xs text-slate-400 font-medium">
              Hyderabad Metro Transit
            </p>
          </div>
        </div>
      </div>

      {/* Navigation Links */}
      <nav className="flex-1 py-6 px-3 space-y-1 overflow-y-auto">
        {navItems.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.name}
              to={item.path}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-slate-800 text-white font-semibold shadow-sm'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
                }`
              }
            >
              <Icon className="w-4 h-4 text-slate-400" />
              <span>{item.name}</span>
            </NavLink>
          );
        })}
      </nav>

      {/* Clean Telemetry Footer */}
      <div className="p-4 border-t border-slate-800/80 m-3 rounded-xl bg-slate-950/40 border text-xs text-slate-400 space-y-1.5">
        <div className="flex items-center justify-between text-slate-300 font-medium">
          <div className="flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full ${isHealthy ? 'bg-emerald-400' : 'bg-rose-400'}`}></span>
            <span>{isHealthy ? 'System Active' : 'System Notice'}</span>
          </div>
          <span className="text-[11px] font-mono text-slate-500">v2.4</span>
        </div>
        <div className="text-[11px] text-slate-500 truncate">
          Weather sync: {lastWeatherUpdate ? new Date(lastWeatherUpdate).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : 'Live'}
        </div>
      </div>
    </aside>
  );
}
