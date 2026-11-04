import { motion } from 'framer-motion';
import { 
  Cpu, 
  BookOpenCheck, 
  PackageCheck, 
  Navigation, 
  CheckCircle2, 
  AlertTriangle,
  Layers,
  Sparkles,
  Zap
} from 'lucide-react';

export default function CapabilitiesSection() {
  return (
    <section id="capabilities" className="relative w-full py-20 sm:py-28 bg-[#F5F7FC]/70 border-t border-slate-200/60">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        
        {/* Section Header */}
        <div className="max-w-3xl mb-16">
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-mono font-semibold text-indigo-700 bg-indigo-50 border border-indigo-200 mb-4">
            <span>CORE ARCHITECTURE</span>
          </div>

          <h2 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold text-slate-900 tracking-tight leading-[1.15]">
            Four Core Engines.{' '}
            <span className="text-indigo-600 block sm:inline">
              One Integrated Operating System.
            </span>
          </h2>

          <p className="mt-4 text-base sm:text-lg text-slate-600 leading-relaxed font-normal">
            AASHRAY replaces fragmented emergency spreadsheets and siloed radio dispatch with four purpose-built, interconnected engines operating in synchronized harmony.
          </p>
        </div>

        {/* 4 Major Capability Cards (2x2 Grid) */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          
          {/* 1. JEV — INCIDENT INTELLIGENCE & DISPATCH */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: '-40px' }}
            transition={{ duration: 0.5 }}
            className="rounded-3xl p-7 sm:p-8 bg-white border border-slate-200/90 shadow-2xs hover:shadow-md transition-all flex flex-col justify-between"
          >
            <div>
              <div className="flex items-center justify-between mb-6">
                <div className="w-13 h-13 rounded-2xl bg-indigo-50 border border-indigo-200 text-indigo-600 flex items-center justify-center shadow-xs">
                  <Cpu className="w-6 h-6" />
                </div>
                <span className="px-2.5 py-1 rounded-full text-[11px] font-mono font-bold bg-indigo-50 text-indigo-700 border border-indigo-100">
                  ENGINE 01
                </span>
              </div>

              <h3 className="text-2xl font-bold text-slate-900 mb-2">
                JEV — Incident Intelligence and Dispatch
              </h3>

              <p className="text-sm text-slate-600 leading-relaxed font-normal mb-6">
                High-throughput multimodal distress intake that extracts disaster categories, evaluates urgency, handles AI-assisted clarification dialogues, and creates operational tickets with zero human-induced bottleneck.
              </p>

              {/* Feature Checklist */}
              <ul className="space-y-2.5 text-xs text-slate-600 mb-6">
                <li className="flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-indigo-600 shrink-0" />
                  <span>Automated severity scoring &amp; disaster taxonomy classification</span>
                </li>
                <li className="flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-indigo-600 shrink-0" />
                  <span>Dynamic citizen clarification dialogues to quantify affected population</span>
                </li>
                <li className="flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-indigo-600 shrink-0" />
                  <span>Sub-second deduplication and multi-agency ticket generation</span>
                </li>
              </ul>
            </div>

            {/* Illustrative Micro-Visual */}
            <div className="p-4 rounded-2xl bg-slate-50 border border-slate-200/70 font-mono text-xs">
              <div className="flex items-center justify-between text-[11px] text-slate-400 pb-2 mb-2 border-b border-slate-200/60">
                <span className="flex items-center gap-1.5 font-sans font-semibold text-slate-700">
                  <Zap className="w-3.5 h-3.5 text-indigo-600" />
                  Live Triage Telemetry
                </span>
                <span className="text-emerald-600 font-bold">LATENCY 42ms</span>
              </div>
              <div className="space-y-1.5 text-[11px]">
                <div className="flex justify-between">
                  <span className="text-slate-500">Event Class:</span>
                  <span className="font-bold text-slate-800">Flash Flood / Structural Threat</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Urgency Level:</span>
                  <span className="font-bold text-rose-600">CRITICAL (Priority 1)</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Geotag Accuracy:</span>
                  <span className="font-bold text-indigo-600">&plusmn; 4.2m WGS84</span>
                </div>
              </div>
            </div>
          </motion.div>

          {/* 2. DISASTER RAG — CONTEXTUAL DISASTER INTELLIGENCE */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: '-40px' }}
            transition={{ duration: 0.5, delay: 0.1 }}
            className="rounded-3xl p-7 sm:p-8 bg-white border border-slate-200/90 shadow-2xs hover:shadow-md transition-all flex flex-col justify-between"
          >
            <div>
              <div className="flex items-center justify-between mb-6">
                <div className="w-13 h-13 rounded-2xl bg-teal-50 border border-teal-200 text-teal-600 flex items-center justify-center shadow-xs">
                  <BookOpenCheck className="w-6 h-6" />
                </div>
                <span className="px-2.5 py-1 rounded-full text-[11px] font-mono font-bold bg-teal-50 text-teal-700 border border-teal-100">
                  ENGINE 02
                </span>
              </div>

              <h3 className="text-2xl font-bold text-slate-900 mb-2">
                Disaster RAG — Contextual Disaster Intelligence
              </h3>

              <p className="text-sm text-slate-600 leading-relaxed font-normal mb-6">
                Domain-specialized Retrieval-Augmented Generation that grounds triage decisions in verified emergency protocols. Generates life-safety medical guidelines for trapped citizens with zero speculative hallucinations.
              </p>

              {/* Feature Checklist */}
              <ul className="space-y-2.5 text-xs text-slate-600 mb-6">
                <li className="flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-teal-600 shrink-0" />
                  <span>Grounded in validated national disaster operating doctrines</span>
                </li>
                <li className="flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-teal-600 shrink-0" />
                  <span>Immediate medical guidance tailored to injury reports and environment</span>
                </li>
                <li className="flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-teal-600 shrink-0" />
                  <span>Vector similarity gating against unverified claims</span>
                </li>
              </ul>
            </div>

            {/* Illustrative Micro-Visual */}
            <div className="p-4 rounded-2xl bg-slate-50 border border-slate-200/70 font-mono text-xs">
              <div className="flex items-center justify-between text-[11px] text-slate-400 pb-2 mb-2 border-b border-slate-200/60">
                <span className="flex items-center gap-1.5 font-sans font-semibold text-slate-700">
                  <Sparkles className="w-3.5 h-3.5 text-teal-600" />
                  Doctrine Grounding
                </span>
                <span className="text-teal-700 font-bold">CONFIDENCE 0.94</span>
              </div>
              <div className="space-y-1.5 text-[11px]">
                <div className="flex justify-between">
                  <span className="text-slate-500">Protocol Chunk:</span>
                  <span className="font-bold text-slate-800">SOP-FL-04: Hypothermia &amp; High Ground</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Citizen Advisory:</span>
                  <span className="font-bold text-indigo-700">Elevated Shelter &bull; Avoid Floodwaters</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Source Grounding:</span>
                  <span className="font-bold text-slate-800">Verified Medical Annex</span>
                </div>
              </div>
            </div>
          </motion.div>

          {/* 3. RESOURCE ENGINE — PLANNING & ALLOCATION */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: '-40px' }}
            transition={{ duration: 0.5, delay: 0.2 }}
            className="rounded-3xl p-7 sm:p-8 bg-white border border-slate-200/90 shadow-2xs hover:shadow-md transition-all flex flex-col justify-between"
          >
            <div>
              <div className="flex items-center justify-between mb-6">
                <div className="w-13 h-13 rounded-2xl bg-amber-50 border border-amber-200 text-amber-600 flex items-center justify-center shadow-xs">
                  <PackageCheck className="w-6 h-6" />
                </div>
                <span className="px-2.5 py-1 rounded-full text-[11px] font-mono font-bold bg-amber-50 text-amber-700 border border-amber-100">
                  ENGINE 03
                </span>
              </div>

              <h3 className="text-2xl font-bold text-slate-900 mb-2">
                Resource Engine — Planning and Allocation
              </h3>

              <p className="text-sm text-slate-600 leading-relaxed font-normal mb-6">
                Inventory-aware optimization engine that translates disaster severity and demographic headcounts into precise supply allocations across 30 distinct relief categories, balancing regional depots.
              </p>

              {/* Feature Checklist */}
              <ul className="space-y-2.5 text-xs text-slate-600 mb-6">
                <li className="flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-amber-600 shrink-0" />
                  <span>30 standardized relief SKUs (food, water purification, pediatric kits)</span>
                </li>
                <li className="flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-amber-600 shrink-0" />
                  <span>Multi-warehouse inventory optimization prevents regional stockouts</span>
                </li>
                <li className="flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-amber-600 shrink-0" />
                  <span>Two-phase emergency dispatch: immediate life-safety + logistical aid</span>
                </li>
              </ul>
            </div>

            {/* Illustrative Micro-Visual */}
            <div className="p-4 rounded-2xl bg-slate-50 border border-slate-200/70 font-mono text-xs">
              <div className="flex items-center justify-between text-[11px] text-slate-400 pb-2 mb-2 border-b border-slate-200/60">
                <span className="flex items-center gap-1.5 font-sans font-semibold text-slate-700">
                  <Layers className="w-3.5 h-3.5 text-amber-600" />
                  Depot Fulfillment Matrix
                </span>
                <span className="text-amber-700 font-bold">30 SKUS MATCHED</span>
              </div>
              <div className="space-y-1.5 text-[11px]">
                <div className="flex justify-between">
                  <span className="text-slate-500">Purified Water:</span>
                  <span className="font-bold text-slate-800">450 Units (Warehouse Alpha)</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Trauma Medical Packs:</span>
                  <span className="font-bold text-slate-800">120 Units (Medical Base 07)</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Emergency Inflatable Boats:</span>
                  <span className="font-bold text-slate-800">14 Units (Depot West)</span>
                </div>
              </div>
            </div>
          </motion.div>

          {/* 4. ROUTE ENGINE — EMERGENCY ROUTE OPTIMIZATION */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: '-40px' }}
            transition={{ duration: 0.5, delay: 0.3 }}
            className="rounded-3xl p-7 sm:p-8 bg-white border border-slate-200/90 shadow-2xs hover:shadow-md transition-all flex flex-col justify-between"
          >
            <div>
              <div className="flex items-center justify-between mb-6">
                <div className="w-13 h-13 rounded-2xl bg-emerald-50 border border-emerald-200 text-emerald-600 flex items-center justify-center shadow-xs">
                  <Navigation className="w-6 h-6" />
                </div>
                <span className="px-2.5 py-1 rounded-full text-[11px] font-mono font-bold bg-emerald-50 text-emerald-700 border border-emerald-100">
                  ENGINE 04
                </span>
              </div>

              <h3 className="text-2xl font-bold text-slate-900 mb-2">
                Route Engine — Emergency Route Optimization
              </h3>

              <p className="text-sm text-slate-600 leading-relaxed font-normal mb-6">
                Tactical road-network navigation designed for disaster environments. Evaluates alternative corridors, bypasses flooded roads and debris, and provides verifiable rationales for rejected routes.
              </p>

              {/* Feature Checklist */}
              <ul className="space-y-2.5 text-xs text-slate-600 mb-6">
                <li className="flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                  <span>Dynamic hazard scoring &amp; live infrastructure road-closure bypass</span>
                </li>
                <li className="flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                  <span>Verifiable rejection reasons (e.g. ROAD_CLOSED, RISK_EXCEEDED)</span>
                </li>
                <li className="flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                  <span>Real-time convoy telemetry &amp; dynamic ETA calculations</span>
                </li>
              </ul>
            </div>

            {/* Illustrative Micro-Visual */}
            <div className="p-4 rounded-2xl bg-slate-50 border border-slate-200/70 font-mono text-xs">
              <div className="flex items-center justify-between text-[11px] text-slate-400 pb-2 mb-2 border-b border-slate-200/60">
                <span className="flex items-center gap-1.5 font-sans font-semibold text-slate-700">
                  <Navigation className="w-3.5 h-3.5 text-emerald-600" />
                  Corridor Decision Audit
                </span>
                <span className="text-emerald-700 font-bold">PRIMARY SELECTED</span>
              </div>
              <div className="space-y-1.5 text-[11px]">
                <div className="flex justify-between">
                  <span className="text-slate-500">Selected Path:</span>
                  <span className="font-bold text-emerald-700">Corridor B (8.4 km &bull; ETA 18m)</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Bypassed Route:</span>
                  <span className="font-bold text-rose-600">Corridor A (ROAD_CLOSED: Flood)</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Backup Viability:</span>
                  <span className="font-bold text-indigo-600">Feasible Alternative Active</span>
                </div>
              </div>
            </div>
          </motion.div>

        </div>

      </div>
    </section>
  );
}
