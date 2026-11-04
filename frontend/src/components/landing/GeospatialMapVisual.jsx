import { motion } from 'framer-motion';
import { 
  AlertTriangle, 
  CheckCircle2, 
  MapPin, 
  Truck, 
  ShieldAlert, 
  Compass, 
  Layers, 
  Activity, 
  Zap,
  Navigation
} from 'lucide-react';

export default function GeospatialMapVisual() {
  return (
    <div className="relative w-full max-w-5xl mx-auto rounded-3xl border border-slate-200/80 bg-gradient-to-b from-slate-50/90 to-[#FAFBFF] p-4 sm:p-6 shadow-[0_20px_60px_-15px_rgba(15,23,42,0.07)] overflow-hidden">
      
      {/* Top Map Status Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-4 mb-4 border-b border-slate-200/70 text-xs">
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
          <span className="font-mono text-[11px] font-semibold text-slate-700 tracking-tight">
            LIVE GEOSPATIAL EMERGENCY TELEMETRY
          </span>
          <span className="hidden sm:inline-block px-2 py-0.5 rounded-full text-[10px] font-mono bg-indigo-50 text-indigo-700 border border-indigo-200 font-medium">
            ZONE: DELTA-NCR
          </span>
        </div>

        <div className="flex items-center gap-3 font-mono text-[10px] text-slate-500">
          <span>LAT: 28.6139° N</span>
          <span>LNG: 77.2090° E</span>
          <span className="hidden md:inline px-1.5 py-0.5 rounded bg-slate-100 text-slate-600">
            WGS84 CORRIDOR
          </span>
        </div>
      </div>

      {/* Interactive Map Visual Area */}
      <div className="relative w-full h-[320px] sm:h-[400px] md:h-[440px] rounded-2xl bg-white/80 border border-slate-200/60 overflow-hidden shadow-inner">
        
        {/* Subtle Map Vector Grid & Contours */}
        <svg 
          className="absolute inset-0 w-full h-full opacity-35" 
          xmlns="http://www.w3.org/2000/svg"
        >
          <defs>
            <pattern id="tactical-grid" width="40" height="40" patternUnits="userSpaceOnUse">
              <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#CBD5E1" strokeWidth="0.75" strokeDasharray="2,2" />
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill="url(#tactical-grid)" />
          
          {/* Subtle regional topography contours */}
          <path 
            d="M -50,160 Q 200,80 400,200 T 900,120 T 1200,240" 
            fill="none" 
            stroke="#94A3B8" 
            strokeWidth="1.2" 
            strokeOpacity="0.4"
          />
          <path 
            d="M -50,240 Q 250,180 500,280 T 1000,200 T 1300,320" 
            fill="none" 
            stroke="#94A3B8" 
            strokeWidth="1" 
            strokeOpacity="0.3" 
            strokeDasharray="4,4"
          />
          <path 
            d="M 100,-20 Q 350,100 650,40 T 1100,150" 
            fill="none" 
            stroke="#64748B" 
            strokeWidth="0.8" 
            strokeOpacity="0.35"
          />
        </svg>

        {/* Route Corridors SVG Layer */}
        <svg className="absolute inset-0 w-full h-full pointer-events-none" xmlns="http://www.w3.org/2000/svg">
          {/* Rejected / Flooded Hazard Route (Amber / Red Dashed) */}
          <path
            d="M 160,330 C 260,280 340,310 490,210"
            fill="none"
            stroke="#FCA5A5"
            strokeWidth="3"
            strokeDasharray="6,6"
            className="opacity-70"
          />
          
          {/* Optimal Selected Response Route (Emerald / Indigo Animated Line) */}
          <path
            id="primary-mission-route"
            d="M 160,330 C 220,190 340,150 490,210"
            fill="none"
            stroke="#6366F1"
            strokeWidth="3.5"
            strokeLinecap="round"
          />
          
          {/* Secondary Feasible Corridor */}
          <path
            d="M 780,140 C 660,110 560,160 490,210"
            fill="none"
            stroke="#0D9488"
            strokeWidth="2.5"
            strokeDasharray="4,4"
            className="opacity-60"
          />

          {/* Animated flow pulse along primary route */}
          <motion.circle
            r="5"
            fill="#4F46E5"
            stroke="#FFFFFF"
            strokeWidth="2"
            animate={{
              offsetDistance: ['0%', '100%']
            }}
            transition={{
              duration: 4,
              repeat: Infinity,
              ease: 'linear'
            }}
            style={{
              offsetPath: 'path("M 160,330 C 220,190 340,150 490,210")'
            }}
          />
        </svg>

        {/* Hazard Warning Node on Bypassed Route */}
        <div className="absolute top-[68%] left-[45%] -translate-x-1/2 -translate-y-1/2 group cursor-pointer z-10">
          <div className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-rose-50 border border-rose-300 text-rose-700 text-[10px] font-mono shadow-xs">
            <AlertTriangle className="w-3 h-3 text-rose-600 shrink-0" />
            <span className="font-semibold">Flooded Arterial Bypassed</span>
          </div>
        </div>

        {/* Warehouse Alpha Node (Origin 1) */}
        <div className="absolute top-[75%] left-[16%] -translate-x-1/2 -translate-y-1/2 z-20">
          <motion.div 
            whileHover={{ scale: 1.05 }}
            className="flex items-center gap-2 bg-white/95 backdrop-blur-md px-3 py-2 rounded-xl border border-indigo-200 shadow-sm"
          >
            <div className="w-7 h-7 rounded-lg bg-indigo-50 border border-indigo-200 text-indigo-600 flex items-center justify-center shrink-0">
              <Truck className="w-3.5 h-3.5" />
            </div>
            <div>
              <div className="text-[11px] font-bold text-slate-900 leading-tight">Central Depot Alpha</div>
              <div className="text-[9px] font-mono text-indigo-600">30 SKUs Ready • En Route</div>
            </div>
          </motion.div>
        </div>

        {/* Medical Reserve Hub (Origin 2) */}
        <div className="absolute top-[28%] right-[12%] -translate-x-1/2 -translate-y-1/2 z-20 hidden sm:block">
          <motion.div 
            whileHover={{ scale: 1.05 }}
            className="flex items-center gap-2 bg-white/95 backdrop-blur-md px-3 py-2 rounded-xl border border-teal-200 shadow-sm"
          >
            <div className="w-7 h-7 rounded-lg bg-teal-50 border border-teal-200 text-teal-600 flex items-center justify-center shrink-0">
              <ShieldAlert className="w-3.5 h-3.5" />
            </div>
            <div>
              <div className="text-[11px] font-bold text-slate-900 leading-tight">Sector 07 Medical Base</div>
              <div className="text-[9px] font-mono text-teal-600">Standby Corridor • Clear</div>
            </div>
          </motion.div>
        </div>

        {/* Emergency Incident Hotspot (Destination) */}
        <div className="absolute top-[48%] left-[50%] -translate-x-1/2 -translate-y-1/2 z-30">
          {/* Radar ripple rings */}
          <div className="absolute inset-0 -m-6 rounded-full border border-rose-500/30 animate-ping pointer-events-none" />
          <div className="absolute inset-0 -m-3 rounded-full bg-rose-500/10 pointer-events-none" />
          
          <motion.div 
            initial={{ scale: 0.95 }}
            animate={{ scale: [0.98, 1.02, 0.98] }}
            transition={{ duration: 3, repeat: Infinity, ease: 'easeInOut' }}
            className="flex items-center gap-2.5 bg-white px-3.5 py-2.5 rounded-2xl border-2 border-rose-500 shadow-md"
          >
            <div className="w-3 h-3 rounded-full bg-rose-600 animate-pulse shrink-0" />
            <div className="text-left">
              <div className="flex items-center gap-1.5">
                <span className="text-[9px] font-mono font-bold uppercase tracking-wider px-1.5 py-0.2 rounded bg-rose-100 text-rose-800">
                  Critical
                </span>
                <span className="text-xs font-bold text-slate-900 leading-tight">
                  Incident #NDRF-402
                </span>
              </div>
              <p className="text-[10px] text-slate-500 mt-0.5 leading-tight font-medium">
                Urban Flash Surge • 18 min Dispatch ETA
              </p>
            </div>
          </motion.div>
        </div>

        {/* Tactical Telemetry Badges (Floating Overlays) */}
        <div className="absolute bottom-3 left-3 right-3 flex flex-wrap items-center justify-between gap-2 pointer-events-none">
          <div className="bg-slate-900/80 backdrop-blur-md text-white px-3 py-1.5 rounded-lg text-[10px] font-mono flex items-center gap-2 border border-slate-700/60 shadow-xs">
            <Navigation className="w-3 h-3 text-emerald-400" />
            <span>Optimal Hazard-Free Corridor: 8.4 km</span>
          </div>

          <div className="bg-white/90 backdrop-blur-md px-3 py-1.5 rounded-lg text-[10px] font-mono text-slate-700 flex items-center gap-2 border border-slate-200 shadow-xs">
            <CheckCircle2 className="w-3 h-3 text-indigo-600" />
            <span>Multi-Depot Inventory: Confirmed</span>
          </div>
        </div>

      </div>

      {/* Bottom Sub-Dashboard Indicators */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-4 text-xs font-mono">
        <div className="p-3 rounded-xl bg-white border border-slate-200/80 shadow-2xs">
          <span className="text-[10px] uppercase text-slate-400 block font-sans font-medium">JEV Intake Engine</span>
          <span className="font-bold text-slate-800 text-xs sm:text-sm">Semantic Triage</span>
          <span className="text-[10px] text-emerald-600 block mt-0.5 font-sans font-medium">● Latency: 0.04s</span>
        </div>

        <div className="p-3 rounded-xl bg-white border border-slate-200/80 shadow-2xs">
          <span className="text-[10px] uppercase text-slate-400 block font-sans font-medium">Disaster RAG</span>
          <span className="font-bold text-slate-800 text-xs sm:text-sm">Knowledge Grounding</span>
          <span className="text-[10px] text-indigo-600 block mt-0.5 font-sans font-medium">● 94% Confidence</span>
        </div>

        <div className="p-3 rounded-xl bg-white border border-slate-200/80 shadow-2xs">
          <span className="text-[10px] uppercase text-slate-400 block font-sans font-medium">Resource Engine</span>
          <span className="font-bold text-slate-800 text-xs sm:text-sm">30 Category Allocator</span>
          <span className="text-[10px] text-emerald-600 block mt-0.5 font-sans font-medium">● Multi-Warehouse Synced</span>
        </div>

        <div className="p-3 rounded-xl bg-white border border-slate-200/80 shadow-2xs">
          <span className="text-[10px] uppercase text-slate-400 block font-sans font-medium">Route Engine</span>
          <span className="font-bold text-slate-800 text-xs sm:text-sm">Hazard Road Bypass</span>
          <span className="text-[10px] text-teal-600 block mt-0.5 font-sans font-medium">● Rejected Corridors Logged</span>
        </div>
      </div>

    </div>
  );
}
