import React, { useState } from 'react';
import AutoPilotDashboard from '../components/AutoPilotPanel';
import EventProximityMap from '../components/EventProximityMap';

export default function ControlCenter() {
  const [showEventMap, setShowEventMap] = useState(false);

  return (
    <main className="p-6 md:p-8 max-w-7xl mx-auto min-h-full">
      {/* ─── Clean AutoPilot Dashboard ─── */}
      <AutoPilotDashboard
        onOpenEventMap={() => setShowEventMap(true)}
      />

      {/* ─── Event & Metro Proximity Map Modal ─── */}
      {showEventMap && (
        <EventProximityMap
          onClose={() => setShowEventMap(false)}
        />
      )}
    </main>
  );
}
