import { useState, useEffect } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import ControlCenter from './pages/ControlCenter';
import NetworkMap from './pages/NetworkMap';
import ScheduleView from './pages/ScheduleView';
import MetroSchedule from './pages/MetroSchedule';
import Trends from './pages/Trends';
import { getHealth, getLiveWeather } from './api/client';

function App() {
  const [health, setHealth] = useState(null);
  const [lastWeatherUpdate, setLastWeatherUpdate] = useState(null);
  
  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const h = await getHealth();
        setHealth(h);
      } catch { setHealth({ status: 'unknown' }); }
      
      try {
        const w = await getLiveWeather();
        setLastWeatherUpdate(w?.timestamp || new Date().toISOString());
      } catch { /* ignore */ }
    };
    
    fetchStatus();
    const interval = setInterval(fetchStatus, 60000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="flex h-screen overflow-hidden bg-slate-950 text-slate-100 font-sans antialiased selection:bg-cyan-500/30 selection:text-cyan-200">
      <Sidebar health={health} lastWeatherUpdate={lastWeatherUpdate} />
      <div className="flex-1 ml-64 overflow-y-auto relative h-full">
        <Routes>
          <Route path="/" element={<ControlCenter />} />
          <Route path="/map" element={<main className="p-6 md:p-8 max-w-7xl mx-auto min-h-full"><NetworkMap /></main>} />
          <Route path="/metro-schedule" element={<main className="p-6 md:p-8 max-w-7xl mx-auto min-h-full"><MetroSchedule /></main>} />
          <Route path="/schedule" element={<main className="p-6 md:p-8 max-w-7xl mx-auto min-h-full"><ScheduleView /></main>} />
          <Route path="/trends" element={<main className="p-6 md:p-8 max-w-7xl mx-auto min-h-full"><Trends /></main>} />
          <Route path="/event" element={<Navigate to="/" replace />} />
        </Routes>
      </div>
    </div>
  );
}

export default App;
