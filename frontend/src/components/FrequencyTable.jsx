import React from 'react';
import { Clock, TrendingUp, Minus } from 'lucide-react';

export default function FrequencyTable({ rows, corridorInfo }) {
  if (!rows || rows.length === 0) {
    return (
      <div className="p-8 text-center text-slate-400 bg-slate-900/50 rounded-xl border border-slate-800 text-sm">
        No schedule data available for the selected parameters.
      </div>
    );
  }

  const inboundRoute = corridorInfo?.inbound?.route || corridorInfo?.inboundRoute || 'Inbound';
  const outboundRoute = corridorInfo?.outbound?.route || corridorInfo?.outboundRoute || 'Outbound';

  const getPeriodBadge = (hour) => {
    if (hour >= 6 && hour <= 10) {
      return (
        <span className="px-2 py-0.5 rounded-md text-xs font-semibold bg-amber-500/10 text-amber-300 border border-amber-500/20">
          Morning Peak
        </span>
      );
    }
    if (hour >= 16 && hour <= 21) {
      return (
        <span className="px-2 py-0.5 rounded-md text-xs font-semibold bg-indigo-500/10 text-indigo-300 border border-indigo-500/20">
          Evening Peak
        </span>
      );
    }
    return (
      <span className="px-2 py-0.5 rounded-md text-xs font-medium bg-slate-800/80 text-slate-400">
        Off-Peak
      </span>
    );
  };

  return (
    <div className="overflow-x-auto rounded-xl border border-slate-800/80 bg-slate-900/60">
      <table className="min-w-full divide-y divide-slate-800/80 text-sm text-left">
        <thead className="bg-slate-950/80 text-slate-300 font-semibold tracking-wide">
          <tr>
            <th scope="col" className="py-3.5 px-4">
              Operating Window
            </th>
            <th scope="col" className="py-3.5 px-4">
              <div className="flex items-center gap-2 text-cyan-300">
                <span className="w-2.5 h-2.5 rounded-full bg-cyan-400 inline-block"></span>
                <span>Inbound ({inboundRoute})</span>
              </div>
            </th>
            <th scope="col" className="py-3.5 px-4">
              <div className="flex items-center gap-2 text-rose-300">
                <span className="w-2.5 h-2.5 rounded-full bg-rose-400 inline-block"></span>
                <span>Outbound ({outboundRoute})</span>
              </div>
            </th>
            <th scope="col" className="py-3.5 px-4 text-slate-300">
              GTFS Baseline
            </th>
            <th scope="col" className="py-3.5 px-4 text-slate-300">
              Directional Priority
            </th>
            <th scope="col" className="py-3.5 px-4 text-slate-300">
              Flow Split
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800/60">
          {rows.map((row, idx) => {
            const hour = row.hour;
            const hourLabel = `${String(hour).padStart(2, '0')}:00 - ${String(hour + 1).padStart(2, '0')}:00`;
            const inboundHw = row.inbound_headway ?? row.recommended_headway;
            const outboundHw = row.outbound_headway ?? row.recommended_headway;
            const baselineHw = row.baseline_headway ?? row.current_headway_min;
            const inTph = row.inbound_tph ?? (inboundHw ? Math.round((60 / inboundHw) * 10) / 10 : '-');
            const outTph = row.outbound_tph ?? (outboundHw ? Math.round((60 / outboundHw) * 10) / 10 : '-');
            const inFrac = row.inbound_fraction ? Math.round(row.inbound_fraction * 100) : 50;
            const outFrac = row.outbound_fraction ? Math.round(row.outbound_fraction * 100) : 50;

            const isPeak = (hour >= 7 && hour <= 10) || (hour >= 17 && hour <= 21);

            return (
              <tr
                key={idx}
                className={`transition-colors hover:bg-slate-800/40 ${isPeak ? 'bg-slate-800/20' : ''}`}
              >
                {/* Operating Window */}
                <td className="whitespace-nowrap py-3 px-4 text-slate-200">
                  <div className="flex items-center gap-2.5">
                    <span className="font-semibold text-white">{hourLabel}</span>
                    {getPeriodBadge(hour)}
                  </div>
                </td>

                {/* Inbound */}
                <td className="whitespace-nowrap py-3 px-4">
                  <div className="flex items-baseline gap-2 font-mono">
                    <span className="text-base font-bold text-cyan-300">
                      {inboundHw ? `${inboundHw.toFixed(1)}m` : '—'}
                    </span>
                    <span className="text-xs text-slate-400 font-sans">
                      ({inTph} TPH)
                    </span>
                  </div>
                </td>

                {/* Outbound */}
                <td className="whitespace-nowrap py-3 px-4">
                  <div className="flex items-baseline gap-2 font-mono">
                    <span className="text-base font-bold text-rose-300">
                      {outboundHw ? `${outboundHw.toFixed(1)}m` : '—'}
                    </span>
                    <span className="text-xs text-slate-400 font-sans">
                      ({outTph} TPH)
                    </span>
                  </div>
                </td>

                {/* Baseline GTFS */}
                <td className="whitespace-nowrap py-3 px-4 text-slate-300 font-mono">
                  {baselineHw ? `${baselineHw.toFixed(1)}m` : '—'}
                </td>

                {/* Directional Priority */}
                <td className="whitespace-nowrap py-3 px-4 text-xs">
                  {inboundHw < outboundHw ? (
                    <span className="inline-flex items-center gap-1.5 text-cyan-300 bg-cyan-950/40 px-2.5 py-1 rounded-md border border-cyan-500/20 font-medium">
                      <TrendingUp className="w-3.5 h-3.5" />
                      Inbound prioritized (+{(outboundHw - inboundHw).toFixed(1)}m faster)
                    </span>
                  ) : outboundHw < inboundHw ? (
                    <span className="inline-flex items-center gap-1.5 text-rose-300 bg-rose-950/40 px-2.5 py-1 rounded-md border border-rose-500/20 font-medium">
                      <TrendingUp className="w-3.5 h-3.5" />
                      Outbound prioritized (+{(inboundHw - outboundHw).toFixed(1)}m faster)
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1.5 text-slate-400 bg-slate-800/40 px-2.5 py-1 rounded-md border border-slate-700/40">
                      <Minus className="w-3.5 h-3.5" />
                      Balanced dispatch (50/50)
                    </span>
                  )}
                </td>

                {/* Flow Split */}
                <td className="whitespace-nowrap py-3 px-4">
                  <div className="w-32 flex flex-col gap-1">
                    <div className="flex justify-between text-xs text-slate-300 font-mono">
                      <span className="text-cyan-400 font-semibold">{inFrac}%</span>
                      <span className="text-rose-400 font-semibold">{outFrac}%</span>
                    </div>
                    <div className="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden flex">
                      <div className="bg-cyan-400" style={{ width: `${inFrac}%` }}></div>
                      <div className="bg-rose-400" style={{ width: `${outFrac}%` }}></div>
                    </div>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
