import { motion } from 'framer-motion';
import { 
  MapPin, 
  Warehouse, 
  Package, 
  Navigation, 
  Clock, 
  CheckCircle2, 
  AlertTriangle, 
  Info,
  ShieldAlert,
  ArrowRight
} from 'lucide-react';

export default function CompactScenarioVisualization() {
  return (
    <section className="relative w-full py-16 sm:py-20 bg-gradient-to-b from-[#FAFBFF] to-[#F5F7FC]/80 border-t border-slate-200/60">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        
        {/* Section Header */}
        <div className="max-w-3xl mb-10">
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-mono font-semibold text-indigo-700 bg-indigo-50 border border-indigo-200 mb-3">
            <Info className="w-3.5 h-3.5 text-indigo-600" />
            <span>END-TO-END DEMONSTRATION SCENARIO</span>
          </div>

          <h2 className="text-2xl sm:text-3xl lg:text-4xl font-extrabold text-slate-900 tracking-tight leading-tight">
            Integrated Scenario Visualization
          </h2>

          <p className="mt-2 text-sm sm:text-base text-slate-600 leading-relaxed font-normal">
            Illustrative walkthrough demonstrating how incident intake, multi-depot inventory, route hazard avoidance, and mission tracking unite during a simulated flash flood.
          </p>
        </div>

        {/* Cohesive Scenario Card (5 Linked Pillars) */}
        <div className="rounded-3xl border border-slate-200/90 bg-white shadow-sm p-6 sm:p-8 overflow-hidden">
          
          {/* Prominent Demonstration Disclaimer Banner */}
          <div className="mb-6 p-3.5 rounded-2xl bg-amber-50/80 border border-amber-200/80 text-xs text-amber-900 flex items-start gap-2.5">
            <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
            <p className="leading-relaxed">
              <strong>Demonstration Visualization Only:</strong> All metrics, locations, and quantities shown below represent an illustrative training scenario designed to explain system integration. They do not represent live disaster deployments, real casualty counts, or actual road conditions.
            </p>
          </div>

          {/* 5 Integrated Modules Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            
            {/* 1. Incident Location */}
            <div className="p-5 rounded-2xl bg-slate-50 border border-slate-200/80 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between mb-3">
                  <div className="w-9 h-9 rounded-xl bg-rose-50 border border-rose-200 text-rose-600 flex items-center justify-center">
                    <MapPin className="w-4 h-4" />
                  </div>
                  <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-rose-100 text-rose-800">
                    ELEMENT 01
                  </span>
                </div>

                <h3 className="text-sm font-bold text-slate-900 mb-1">
                  1. Incident Location
                </h3>
                <div className="font-mono text-xs text-slate-700 font-semibold mb-2">
                  Sector 4 Riverside Corridor
                </div>

                <p className="text-xs text-slate-500 leading-relaxed font-normal mb-3">
                  12 citizens stranded on elevated terrace due to sudden inundation. Coordinates resolved to 28.6139&deg; N, 77.2090&deg; E.
                </p>
              </div>

              <div className="pt-3 border-t border-slate-200/60 flex items-center justify-between text-[11px] font-mono text-slate-500">
                <span>Triage Urgency:</span>
                <span className="font-bold text-rose-600">Priority 1 (Critical)</span>
              </div>
            </div>

            {/* 2. Nearby Resource Hubs */}
            <div className="p-5 rounded-2xl bg-slate-50 border border-slate-200/80 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between mb-3">
                  <div className="w-9 h-9 rounded-xl bg-indigo-50 border border-indigo-200 text-indigo-600 flex items-center justify-center">
                    <Warehouse className="w-4 h-4" />
                  </div>
                  <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-indigo-100 text-indigo-800">
                    ELEMENT 02
                  </span>
                </div>

                <h3 className="text-sm font-bold text-slate-900 mb-1">
                  2. Nearby Resource Hubs
                </h3>
                <div className="font-mono text-xs text-slate-700 font-semibold mb-2">
                  Multi-Depot Proximity Match
                </div>

                <div className="space-y-2 text-xs text-slate-600 mb-3">
                  <div className="p-2 rounded-lg bg-white border border-slate-200/70 flex justify-between">
                    <span>Central Depot Alpha (5.2 km)</span>
                    <span className="font-mono text-indigo-600 font-semibold">Active</span>
                  </div>
                  <div className="p-2 rounded-lg bg-white border border-slate-200/70 flex justify-between">
                    <span>Medical Base 07 (7.8 km)</span>
                    <span className="font-mono text-teal-600 font-semibold">Standby</span>
                  </div>
                </div>
              </div>

              <div className="pt-3 border-t border-slate-200/60 flex items-center justify-between text-[11px] font-mono text-slate-500">
                <span>Regional Fulfillment:</span>
                <span className="font-bold text-emerald-600">Dual Depots Synced</span>
              </div>
            </div>

            {/* 3. Example Resource Allocation */}
            <div className="p-5 rounded-2xl bg-slate-50 border border-slate-200/80 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between mb-3">
                  <div className="w-9 h-9 rounded-xl bg-amber-50 border border-amber-200 text-amber-600 flex items-center justify-center">
                    <Package className="w-4 h-4" />
                  </div>
                  <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-amber-100 text-amber-800">
                    ELEMENT 03
                  </span>
                </div>

                <h3 className="text-sm font-bold text-slate-900 mb-1">
                  3. Example Resource Allocation
                </h3>
                <div className="font-mono text-xs text-slate-700 font-semibold mb-2">
                  30-SKU Requirement Calculus
                </div>

                <div className="grid grid-cols-2 gap-2 text-xs font-mono mb-3">
                  <div className="p-2 rounded-lg bg-white border border-slate-200/70">
                    <span className="text-[10px] text-slate-400 block">Drinking Water</span>
                    <span className="font-bold text-slate-900">450 Liters</span>
                  </div>
                  <div className="p-2 rounded-lg bg-white border border-slate-200/70">
                    <span className="text-[10px] text-slate-400 block">Ready Meals</span>
                    <span className="font-bold text-slate-900">180 Packs</span>
                  </div>
                  <div className="p-2 rounded-lg bg-white border border-slate-200/70">
                    <span className="text-[10px] text-slate-400 block">Trauma Packs</span>
                    <span className="font-bold text-slate-900">12 Units</span>
                  </div>
                  <div className="p-2 rounded-lg bg-white border border-slate-200/70">
                    <span className="text-[10px] text-slate-400 block">Inflatable Rafts</span>
                    <span className="font-bold text-slate-900">2 Boats</span>
                  </div>
                </div>
              </div>

              <div className="pt-3 border-t border-slate-200/60 flex items-center justify-between text-[11px] font-mono text-slate-500">
                <span>Allocation Policy:</span>
                <span className="font-bold text-indigo-700">Demographic Weighted</span>
              </div>
            </div>

            {/* 4. Response Route Selection */}
            <div className="p-5 rounded-2xl bg-slate-50 border border-slate-200/80 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between mb-3">
                  <div className="w-9 h-9 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-600 flex items-center justify-center">
                    <Navigation className="w-4 h-4" />
                  </div>
                  <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-emerald-100 text-emerald-800">
                    ELEMENT 04
                  </span>
                </div>

                <h3 className="text-sm font-bold text-slate-900 mb-1">
                  4. Response Route
                </h3>
                <div className="font-mono text-xs text-slate-700 font-semibold mb-2">
                  Hazard-Aware Corridor Planning
                </div>

                <div className="space-y-2 text-xs mb-3">
                  <div className="p-2.5 rounded-lg bg-emerald-50/70 border border-emerald-200">
                    <div className="flex justify-between font-bold text-emerald-800 text-[11px]">
                      <span>Selected: Western Bypass</span>
                      <span>ETA 18 min</span>
                    </div>
                    <span className="text-[10px] text-emerald-700 block mt-0.5 font-mono">
                      8.4 km &bull; Elevated flyover &bull; 0 hazards
                    </span>
                  </div>

                  <div className="p-2.5 rounded-lg bg-rose-50/60 border border-rose-200">
                    <div className="flex justify-between font-bold text-rose-800 text-[11px]">
                      <span>Rejected: Central Arterial</span>
                      <span className="font-mono text-rose-600">ROAD_CLOSED</span>
                    </div>
                    <span className="text-[10px] text-rose-700 block mt-0.5 font-mono">
                      6.1 km &bull; Underpass flooded (1.4m depth)
                    </span>
                  </div>
                </div>
              </div>

              <div className="pt-3 border-t border-slate-200/60 flex items-center justify-between text-[11px] font-mono text-slate-500">
                <span>Audit Trajectory:</span>
                <span className="font-bold text-slate-700">Rejections Logged</span>
              </div>
            </div>

            {/* 5. Mission Status Tracking */}
            <div className="p-5 rounded-2xl bg-slate-50 border border-slate-200/80 flex flex-col justify-between lg:col-span-2">
              <div>
                <div className="flex items-center justify-between mb-3">
                  <div className="w-9 h-9 rounded-xl bg-indigo-50 border border-indigo-200 text-indigo-600 flex items-center justify-center">
                    <Clock className="w-4 h-4" />
                  </div>
                  <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-indigo-100 text-indigo-800">
                    ELEMENT 05
                  </span>
                </div>

                <h3 className="text-sm font-bold text-slate-900 mb-1">
                  5. Mission Status
                </h3>
                <div className="font-mono text-xs text-slate-700 font-semibold mb-2">
                  Two-Phase Tactical Dispatch Progress (Ref: MSN-2026-DEMO-04)
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs mb-3">
                  <div className="p-3 bg-white rounded-xl border border-indigo-200 shadow-2xs">
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-bold text-slate-900">Phase 1: Tactical Responders</span>
                      <span className="font-mono text-emerald-600 font-bold">DISPATCHED</span>
                    </div>
                    <p className="text-[11px] text-slate-500">
                      NDRF Swiftwater Unit 04 &bull; 4 Specialist Personnel &bull; Safe Arrival ETA 18 mins
                    </p>
                  </div>

                  <div className="p-3 bg-white rounded-xl border border-slate-200 shadow-2xs">
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-bold text-slate-900">Phase 2: Supply Cargo</span>
                      <span className="font-mono text-indigo-600 font-bold">LOADING</span>
                    </div>
                    <p className="text-[11px] text-slate-500">
                      Warehouse Alpha Convoy &bull; 30-SKU Payload &bull; Estimated Arrival in 34 mins
                    </p>
                  </div>
                </div>
              </div>

              <div className="pt-3 border-t border-slate-200/60 flex flex-wrap items-center justify-between gap-2 text-[11px] font-mono text-slate-500">
                <span>Citizen View: Live Safe Countdown</span>
                <span className="font-bold text-emerald-700">&bull; Mission Active &amp; Verified</span>
              </div>
            </div>

          </div>

        </div>

      </div>
    </section>
  );
}
