import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Radio, 
  Package, 
  Clock, 
  Map, 
  CheckCircle2, 
  AlertTriangle, 
  Compass, 
  Truck, 
  ShieldAlert, 
  Activity,
  Layers,
  ChevronRight
} from 'lucide-react';

const TABS = [
  { id: 'incidents', label: 'Incident Monitoring', icon: Radio },
  { id: 'resources', label: 'Resource Allocation', icon: Package },
  { id: 'missions', label: 'Mission Tracking', icon: Clock },
  { id: 'routing', label: 'Route Optimization', icon: Map },
];

export default function PlatformPreviewSection() {
  const [activeTab, setActiveTab] = useState('incidents');

  return (
    <section id="technology" className="relative w-full py-20 sm:py-28 bg-[#FAFBFF]">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        
        {/* Section Header */}
        <div className="text-center max-w-3xl mx-auto mb-12 sm:mb-16">
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-mono font-semibold text-teal-700 bg-teal-50 border border-teal-200 mb-4">
            <span>UNIFIED PLATFORM INTERFACES</span>
          </div>

          <h2 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold text-slate-900 tracking-tight leading-[1.15]">
            Enterprise Tactical Command &amp; Field Coordination
          </h2>

          <p className="mt-4 text-base sm:text-lg text-slate-600 leading-relaxed font-normal">
            Designed for high-stress disaster response environments—combining citizen reporting clarity with real-time logistical precision.
          </p>
        </div>

        {/* Tab Switcher */}
        <div className="flex flex-wrap items-center justify-center gap-2 mb-8">
          {TABS.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => setActiveTab(tab.id)}
                className={`px-4 sm:px-5 py-2.5 rounded-full text-xs sm:text-sm font-semibold flex items-center gap-2 transition-all cursor-pointer ${
                  isActive
                    ? 'bg-indigo-600 text-white shadow-xs'
                    : 'bg-white text-slate-600 hover:text-slate-900 border border-slate-200/80 hover:bg-slate-50'
                }`}
              >
                <Icon className={`w-4 h-4 ${isActive ? 'text-white' : 'text-indigo-600'}`} />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </div>

        {/* Preview Frame Container */}
        <div className="relative w-full max-w-5xl mx-auto rounded-3xl border border-slate-200/90 bg-white shadow-md p-4 sm:p-6 lg:p-8 overflow-hidden">
          
          {/* Header Bar of the Mockup Window */}
          <div className="flex items-center justify-between pb-4 mb-6 border-b border-slate-100 text-xs">
            <div className="flex items-center gap-2">
              <span className="w-3 h-3 rounded-full bg-rose-400/80" />
              <span className="w-3 h-3 rounded-full bg-amber-400/80" />
              <span className="w-3 h-3 rounded-full bg-emerald-400/80" />
              <span className="ml-2 font-mono text-[11px] text-slate-400">
                aashray://operations-command/{activeTab}
              </span>
            </div>

            <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-mono bg-slate-100 text-slate-600 font-medium">
              <span>ILLUSTRATIVE INTERFACE PREVIEW</span>
            </div>
          </div>

          {/* Active Preview Content */}
          <AnimatePresence mode="wait">
            {activeTab === 'incidents' && (
              <motion.div
                key="incidents"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                transition={{ duration: 0.3 }}
                className="space-y-4"
              >
                <div className="p-4 sm:p-6 rounded-2xl bg-slate-50 border border-slate-200/70">
                  <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
                    <div className="flex items-center gap-2.5">
                      <span className="w-2.5 h-2.5 rounded-full bg-rose-600 animate-pulse" />
                      <h4 className="text-sm sm:text-base font-bold text-slate-900">
                        Incident #NCR-2026-0814 — Flash Flood &amp; Structural Entrapment
                      </h4>
                    </div>
                    <span className="px-2.5 py-0.5 rounded-full text-xs font-mono font-bold bg-rose-100 text-rose-800">
                      HIGH SEVERITY
                    </span>
                  </div>

                  <p className="text-xs sm:text-sm text-slate-600 mb-4 leading-relaxed">
                    &ldquo;Water levels rising rapidly on Main Road Sector 4. Multiple senior citizens stranded on second floor. Power transformer spark observed.&rdquo;
                  </p>

                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs font-mono">
                    <div className="p-3 bg-white rounded-xl border border-slate-200/80">
                      <span className="text-[10px] text-slate-400 block">JEV Classification</span>
                      <span className="font-bold text-slate-800">Flood / Rescue Priority 1</span>
                    </div>
                    <div className="p-3 bg-white rounded-xl border border-slate-200/80">
                      <span className="text-[10px] text-slate-400 block">Clarification Dialog</span>
                      <span className="font-bold text-slate-800">12 Citizens Trapped</span>
                    </div>
                    <div className="p-3 bg-white rounded-xl border border-slate-200/80">
                      <span className="text-[10px] text-slate-400 block">Disaster RAG Advisory</span>
                      <span className="font-bold text-indigo-600">Avoid Electrical Grid</span>
                    </div>
                  </div>
                </div>
              </motion.div>
            )}

            {activeTab === 'resources' && (
              <motion.div
                key="resources"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                transition={{ duration: 0.3 }}
                className="space-y-4"
              >
                <div className="p-4 sm:p-6 rounded-2xl bg-slate-50 border border-slate-200/70">
                  <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
                    <div>
                      <h4 className="text-sm sm:text-base font-bold text-slate-900">
                        Multi-Warehouse Inventory Allocation Matrix
                      </h4>
                      <p className="text-xs text-slate-500 mt-0.5">
                        Automated fulfillment calculated across 3 regional depots
                      </p>
                    </div>
                    <span className="px-2.5 py-0.5 rounded-full text-xs font-mono font-bold bg-emerald-100 text-emerald-800">
                      100% FULFILLED
                    </span>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 text-xs font-mono mb-4">
                    <div className="p-3 bg-white rounded-xl border border-slate-200/80">
                      <span className="text-[10px] text-slate-400 block">Drinking Water (L)</span>
                      <span className="text-sm font-bold text-slate-900">1,200 L Allocated</span>
                      <span className="text-[10px] text-emerald-600 block mt-0.5">Depot Alpha: 100%</span>
                    </div>
                    <div className="p-3 bg-white rounded-xl border border-slate-200/80">
                      <span className="text-[10px] text-slate-400 block">MRE Ready Meals</span>
                      <span className="text-sm font-bold text-slate-900">600 Packs</span>
                      <span className="text-[10px] text-emerald-600 block mt-0.5">Depot Alpha: 100%</span>
                    </div>
                    <div className="p-3 bg-white rounded-xl border border-slate-200/80">
                      <span className="text-[10px] text-slate-400 block">Inflatable Rafts</span>
                      <span className="text-sm font-bold text-slate-900">4 Craft</span>
                      <span className="text-[10px] text-indigo-600 block mt-0.5">Depot West: 100%</span>
                    </div>
                    <div className="p-3 bg-white rounded-xl border border-slate-200/80">
                      <span className="text-[10px] text-slate-400 block">Trauma Med Kits</span>
                      <span className="text-sm font-bold text-slate-900">24 Units</span>
                      <span className="text-[10px] text-teal-600 block mt-0.5">Medical Hub: 100%</span>
                    </div>
                  </div>
                </div>
              </motion.div>
            )}

            {activeTab === 'missions' && (
              <motion.div
                key="missions"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                transition={{ duration: 0.3 }}
                className="space-y-4"
              >
                <div className="p-4 sm:p-6 rounded-2xl bg-slate-50 border border-slate-200/70">
                  <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
                    <div>
                      <h4 className="text-sm sm:text-base font-bold text-slate-900">
                        Two-Phase Emergency Dispatch Tracking
                      </h4>
                      <p className="text-xs text-slate-500 mt-0.5">
                        Tactical unit dispatched immediately; cargo payload in transit
                      </p>
                    </div>
                    <span className="px-2.5 py-0.5 rounded-full text-xs font-mono font-bold bg-indigo-100 text-indigo-800">
                      MISSION IN PROGRESS
                    </span>
                  </div>

                  <div className="space-y-3 text-xs">
                    <div className="p-3.5 bg-white rounded-xl border border-indigo-200 flex flex-wrap items-center justify-between gap-3">
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center font-bold">
                          P1
                        </div>
                        <div>
                          <span className="font-bold text-slate-900 block">Phase 1: Rapid Responder Unit (NDRF-4)</span>
                          <span className="text-[11px] text-slate-500">Search &amp; Rescue Boat Unit &bull; 4 Personnel</span>
                        </div>
                      </div>
                      <span className="font-mono text-emerald-600 font-bold">ARRIVING IN 14 MIN</span>
                    </div>

                    <div className="p-3.5 bg-white rounded-xl border border-slate-200/80 flex flex-wrap items-center justify-between gap-3">
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-lg bg-slate-100 text-slate-600 flex items-center justify-center font-bold">
                          P2
                        </div>
                        <div>
                          <span className="font-bold text-slate-900 block">Phase 2: Logistical Relief Payload</span>
                          <span className="text-[11px] text-slate-500">Warehouse Alpha Convoys &bull; 30 SKU Package</span>
                        </div>
                      </div>
                      <span className="font-mono text-indigo-600 font-bold">EN ROUTE &bull; ETA 32 MIN</span>
                    </div>
                  </div>
                </div>
              </motion.div>
            )}

            {activeTab === 'routing' && (
              <motion.div
                key="routing"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                transition={{ duration: 0.3 }}
                className="space-y-4"
              >
                <div className="p-4 sm:p-6 rounded-2xl bg-slate-50 border border-slate-200/70">
                  <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
                    <div>
                      <h4 className="text-sm sm:text-base font-bold text-slate-900">
                        Multi-Candidate Tactical Route Selection &amp; Audit
                      </h4>
                      <p className="text-xs text-slate-500 mt-0.5">
                        Real-time hazard scoring with explicit corridor rejection rules
                      </p>
                    </div>
                    <span className="px-2.5 py-0.5 rounded-full text-xs font-mono font-bold bg-teal-100 text-teal-800">
                      HAZARDS BYPASSED
                    </span>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
                    <div className="p-4 bg-white rounded-xl border-2 border-emerald-500 shadow-2xs">
                      <div className="flex items-center justify-between mb-2">
                        <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-emerald-50 text-emerald-700">
                          SELECTED PRIMARY ROUTE
                        </span>
                        <span className="font-mono font-bold text-slate-800">ETA 18 min</span>
                      </div>
                      <div className="text-xs font-bold text-slate-900 mb-1">Via Outer Western Bypass (8.4 km)</div>
                      <p className="text-[11px] text-slate-500">
                        Elevated highway corridor &bull; Zero flood hazards detected &bull; Open access confirmed
                      </p>
                    </div>

                    <div className="p-4 bg-white rounded-xl border border-rose-200 bg-rose-50/20 shadow-2xs">
                      <div className="flex items-center justify-between mb-2">
                        <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-rose-50 text-rose-700">
                          REJECTED ROUTE CANDIDATE
                        </span>
                        <span className="font-mono text-rose-600 font-bold">ROAD_CLOSED</span>
                      </div>
                      <div className="text-xs font-bold text-slate-900 mb-1">Via Central Arterial Link (6.1 km)</div>
                      <p className="text-[11px] text-rose-700 font-medium">
                        Rejected: Underpass submerged under 1.4m water &bull; Risk threshold 0.88 exceeded
                      </p>
                    </div>
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

        </div>

      </div>
    </section>
  );
}
