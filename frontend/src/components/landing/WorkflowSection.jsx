import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  MessageSquarePlus, 
  Cpu, 
  BookOpenCheck, 
  PackageCheck, 
  Users, 
  Navigation, 
  ChevronDown,
  ArrowRight,
  Layers,
  Sparkles,
  ArrowDown
} from 'lucide-react';

const WORKFLOW_STEPS = [
  {
    step: '01',
    title: 'Citizen Incident Reporting',
    subtitle: 'Multimodal Intake & Geolocation',
    badge: 'INTAKE',
    icon: MessageSquarePlus,
    description:
      'Affected citizens submit distress signals with automatic GPS coordinates, voice notes, and damage photos, followed by interactive clarification dialogues.',
    responsibility: 'Captures initial ground-truth distress signals directly from impacted populations without latency.',
    input: 'Geotagged text, voice recordings, casualty estimates, and ground damage photos.',
    processing: 'Mobile-first report ingestion with dynamic clarification dialogues to quantify headcount and severity.',
    output: 'Validated distress signal with GPS coordinates, urgency category, and affected headcount.',
    handoff: 'Streamed into JEV Incident Processing & Dispatch for automated classification.'
  },
  {
    step: '02',
    title: 'JEV Incident Processing & Dispatch',
    subtitle: 'Semantic Triage & Categorization',
    badge: 'TRIAGE',
    icon: Cpu,
    description:
      'The JEV engine analyzes report syntax, extracts disaster entities, classifies severity, and escalates critical missions with sub-second latency.',
    responsibility: 'High-throughput incident parsing, deduplication, and automated emergency prioritization.',
    input: 'Raw citizen distress streams and cross-channel incident signals.',
    processing: 'NLP entity extraction, deduplication against existing incidents, and taxonomy classification.',
    output: 'Structured incident ticket with taxonomy classification and severity ranking (Critical/High/Med/Low).',
    handoff: 'Context forwarded to Disaster RAG for protocols and to Resource Engine for supply calculation.'
  },
  {
    step: '03',
    title: 'Disaster RAG Knowledge Assessment',
    subtitle: 'Grounded Crisis Intelligence',
    badge: 'KNOWLEDGE',
    icon: BookOpenCheck,
    description:
      'Retrieval-Augmented Generation grounds incident triage in verified crisis protocols, generating immediate life-safety advisories for citizens and dispatchers.',
    responsibility: 'Domain-specialized knowledge retrieval to ground emergency response in verified medical doctrines.',
    input: 'Classified disaster type, environmental context, and citizen casualty descriptions.',
    processing: 'Vector similarity retrieval matching national disaster operating procedures and medical protocols.',
    output: 'Grounded life-safety guidelines, first-aid checklists, and on-scene casualty protocols without hallucination.',
    handoff: 'Returned to citizens as real-time advisory and attached to field responder brief.'
  },
  {
    step: '04',
    title: 'Resource Engine',
    subtitle: '30-SKU Multi-Warehouse Balance',
    badge: 'ALLOCATION',
    icon: PackageCheck,
    description:
      'Demographic requirement models calculate exact food, water, medical, and rescue gear needs, solving supply constraints across regional warehouses.',
    responsibility: 'Algorithmic calculation of relief supplies and optimal multi-depot stock matching.',
    input: 'Incident severity level, population headcount, and real-time regional warehouse inventory counts.',
    processing: 'Demographic-weighted requirement models across 30 supply categories; balances stock across depots.',
    output: 'Detailed allocation manifest (water, MREs, medical packs, rescue boats) reserved at specific warehouses.',
    handoff: 'Transmitted to Mission Creation to trigger tactical unit dispatch and cargo bundling.'
  },
  {
    step: '05',
    title: 'Mission Creation & Responder Assignment',
    subtitle: 'Two-Phase Tactical Deployment',
    badge: 'DISPATCH',
    icon: Users,
    description:
      'Immediate missions pair field responders with allocated inventory payloads, generating live tracking references and arrival countdowns.',
    responsibility: 'Automated pairing of emergency response units with dedicated relief payloads.',
    input: 'Approved resource allocation manifests, incident coordinates, and responder registry.',
    processing: 'Executes two-phase dispatch: Phase 1 (rapid rescue units) and Phase 2 (warehouse logistics convoys).',
    output: 'Confirmed mission record with tracking reference ID, assigned tactical unit, and safe arrival ETA.',
    handoff: 'Dispatched mission coordinates forwarded to Route Engine for corridor optimization.'
  },
  {
    step: '06',
    title: 'Route Engine',
    subtitle: 'Hazard Bypass & Verifiable Scoring',
    badge: 'ROUTING',
    icon: Navigation,
    description:
      'Dynamic routing evaluates multiple road corridors, bypassing waterlogged highways and closures with clear audit trails for rejected paths.',
    responsibility: 'Tactical navigation computing safest routes and actively bypassing road hazards.',
    input: 'Origin warehouse locations, destination incident coordinates, and road condition evidence.',
    processing: 'Multi-criteria routing evaluating distance, ETA, and hazard barriers; generates candidate paths.',
    output: 'Selected primary corridor, viable backup alternatives, and logged rejected routes with explicit reasons.',
    handoff: 'Live navigation telemetry delivered to responder convoys and citizen tracking interfaces.'
  }
];

export default function WorkflowSection() {
  const [expandedIndex, setExpandedIndex] = useState(null);

  const toggleExpand = (idx) => {
    setExpandedIndex(expandedIndex === idx ? null : idx);
  };

  return (
    <section id="how-it-works" className="relative w-full py-20 sm:py-28 bg-[#FAFBFF]">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        
        {/* Section Header */}
        <div className="text-center max-w-3xl mx-auto mb-16 sm:mb-20">
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-mono font-semibold text-indigo-700 bg-indigo-50 border border-indigo-200 mb-4">
            <span>OPERATIONAL SEQUENCE</span>
          </div>

          <h2 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold text-slate-900 tracking-tight leading-[1.15]">
            How AASHRAY Coordinates Emergency Response
          </h2>

          <p className="mt-4 text-base sm:text-lg text-slate-600 leading-relaxed font-normal">
            From the initial distress signal to on-scene relief delivery: a verified, end-to-end operational pipeline linking citizens, algorithms, and tactical units.
          </p>
        </div>

        {/* Desktop Connected Grid (6 Steps in 2 Rows of 3) with Visual Progression */}
        <div className="hidden lg:grid grid-cols-3 gap-8 relative">
          
          {/* Subtle connecting connector line across Row 1 */}
          <div className="absolute top-[28px] left-[15%] right-[15%] h-0.5 border-t-2 border-dashed border-indigo-200/80 -z-0 pointer-events-none" />

          {WORKFLOW_STEPS.map((item, idx) => {
            const Icon = item.icon;
            const isExpanded = expandedIndex === idx;

            return (
              <motion.div
                key={item.title}
                initial={{ opacity: 0, y: 24 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: '-40px' }}
                transition={{ duration: 0.5, delay: idx * 0.08 }}
                className={`relative rounded-3xl p-7 bg-white border transition-all duration-300 flex flex-col justify-between ${
                  isExpanded 
                    ? 'border-indigo-400 shadow-md ring-1 ring-indigo-200' 
                    : 'border-slate-200/80 shadow-2xs hover:shadow-md hover:border-slate-300'
                }`}
              >
                <div>
                  {/* Top Bar: Icon + Large Number (No redundant STAGE label) */}
                  <div className="flex items-center justify-between mb-5 relative z-10">
                    <div className="w-12 h-12 rounded-2xl bg-indigo-50 border border-indigo-200/70 text-indigo-600 flex items-center justify-center shadow-xs">
                      <Icon className="w-6 h-6" />
                    </div>
                    
                    {/* Retained large numbered indicator */}
                    <span className="font-mono text-3xl font-black text-slate-200 selection:bg-transparent">
                      {item.step}
                    </span>
                  </div>

                  <span className="inline-block px-2 py-0.5 rounded text-[10px] font-mono font-bold tracking-wider text-indigo-700 bg-indigo-50/70 border border-indigo-100 mb-2">
                    {item.badge}
                  </span>

                  <h3 className="text-lg font-bold text-slate-900 leading-snug">
                    {item.title}
                  </h3>

                  <div className="text-xs font-medium text-slate-400 mb-3">
                    {item.subtitle}
                  </div>

                  <p className="text-xs sm:text-sm text-slate-600 leading-relaxed font-normal">
                    {item.description}
                  </p>

                  {/* Expandable Component Details Drawer */}
                  <AnimatePresence>
                    {isExpanded && (
                      <motion.div
                        initial={{ opacity: 0, height: 0 }}
                        animate={{ opacity: 1, height: 'auto' }}
                        exit={{ opacity: 0, height: 0 }}
                        transition={{ duration: 0.3 }}
                        className="overflow-hidden pt-4 mt-4 border-t border-indigo-100 text-xs text-slate-600 space-y-2.5 bg-indigo-50/30 p-3.5 rounded-2xl"
                      >
                        <div>
                          <span className="font-mono text-[10px] font-bold text-indigo-900 uppercase block">Responsibility</span>
                          <span className="text-[11px] text-slate-700">{item.responsibility}</span>
                        </div>
                        <div>
                          <span className="font-mono text-[10px] font-bold text-indigo-900 uppercase block">Input Received</span>
                          <span className="text-[11px] text-slate-700">{item.input}</span>
                        </div>
                        <div>
                          <span className="font-mono text-[10px] font-bold text-indigo-900 uppercase block">Processing</span>
                          <span className="text-[11px] text-slate-700">{item.processing}</span>
                        </div>
                        <div>
                          <span className="font-mono text-[10px] font-bold text-indigo-900 uppercase block">Output Produced</span>
                          <span className="text-[11px] text-slate-700">{item.output}</span>
                        </div>
                        <div>
                          <span className="font-mono text-[10px] font-bold text-emerald-800 uppercase block">Handoff to Next</span>
                          <span className="text-[11px] text-emerald-900 font-medium">{item.handoff}</span>
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>

                {/* Footer: Meaningful contextual action replacing redundant STAGE label */}
                <div className="pt-4 mt-6 border-t border-slate-100 flex items-center justify-between text-xs font-mono">
                  <button
                    type="button"
                    onClick={() => toggleExpand(idx)}
                    className="flex items-center gap-1.5 text-indigo-600 hover:text-indigo-800 font-semibold cursor-pointer transition py-1"
                  >
                    <span>{isExpanded ? 'Collapse details' : 'Explore component'}</span>
                    <ChevronDown className={`w-3.5 h-3.5 transition-transform duration-200 ${isExpanded ? 'rotate-180 text-indigo-800' : 'text-indigo-500'}`} />
                  </button>

                  {/* Flow arrow to next step if applicable */}
                  {idx < WORKFLOW_STEPS.length - 1 && (
                    <span className="text-slate-300 flex items-center" title={`Connects to step 0${idx + 2}`}>
                      <ArrowRight className="w-4 h-4 text-slate-400" />
                    </span>
                  )}
                </div>
              </motion.div>
            );
          })}
        </div>

        {/* Mobile / Tablet Vertical Timeline (< lg screens) */}
        <div className="lg:hidden relative pl-6 sm:pl-8 border-l-2 border-indigo-200/80 space-y-8">
          {WORKFLOW_STEPS.map((item, idx) => {
            const Icon = item.icon;
            const isExpanded = expandedIndex === idx;

            return (
              <motion.div
                key={item.title}
                initial={{ opacity: 0, x: -16 }}
                whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true, margin: '-30px' }}
                transition={{ duration: 0.4, delay: idx * 0.05 }}
                className={`relative bg-white rounded-2xl p-5 sm:p-6 border transition-all ${
                  isExpanded ? 'border-indigo-400 shadow-md ring-1 ring-indigo-200' : 'border-slate-200/80 shadow-2xs'
                }`}
              >
                {/* Timeline Node Marker */}
                <div className="absolute -left-[35px] sm:-left-[43px] top-6 w-7 h-7 rounded-full bg-white border-2 border-indigo-600 flex items-center justify-center shadow-xs text-indigo-600 font-mono text-[10px] font-bold">
                  {item.step}
                </div>

                <div className="flex items-center justify-between mb-3">
                  <div className="w-9 h-9 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center">
                    <Icon className="w-4 h-4" />
                  </div>
                  <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-indigo-50 text-indigo-700">
                    {item.badge}
                  </span>
                </div>

                <h3 className="text-base font-bold text-slate-900">
                  {item.title}
                </h3>
                <p className="text-xs font-medium text-slate-400 mb-2">
                  {item.subtitle}
                </p>
                <p className="text-xs text-slate-600 leading-relaxed font-normal mb-3">
                  {item.description}
                </p>

                {/* Mobile Expandable Component Details */}
                <AnimatePresence>
                  {isExpanded && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: 'auto' }}
                      exit={{ opacity: 0, height: 0 }}
                      transition={{ duration: 0.25 }}
                      className="overflow-hidden pt-3 mt-3 border-t border-indigo-100 text-xs text-slate-600 space-y-2 bg-indigo-50/40 p-3 rounded-xl mb-3"
                    >
                      <div>
                        <span className="font-mono text-[10px] font-bold text-indigo-900 uppercase block">Responsibility</span>
                        <span className="text-[11px] text-slate-700">{item.responsibility}</span>
                      </div>
                      <div>
                        <span className="font-mono text-[10px] font-bold text-indigo-900 uppercase block">Input Received</span>
                        <span className="text-[11px] text-slate-700">{item.input}</span>
                      </div>
                      <div>
                        <span className="font-mono text-[10px] font-bold text-indigo-900 uppercase block">Processing</span>
                        <span className="text-[11px] text-slate-700">{item.processing}</span>
                      </div>
                      <div>
                        <span className="font-mono text-[10px] font-bold text-indigo-900 uppercase block">Output Produced</span>
                        <span className="text-[11px] text-slate-700">{item.output}</span>
                      </div>
                      <div>
                        <span className="font-mono text-[10px] font-bold text-emerald-800 uppercase block">Handoff to Next</span>
                        <span className="text-[11px] text-emerald-900 font-medium">{item.handoff}</span>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>

                {/* Footer Action */}
                <div className="pt-3 border-t border-slate-100 flex items-center justify-between text-xs font-mono">
                  <button
                    type="button"
                    onClick={() => toggleExpand(idx)}
                    className="flex items-center gap-1 text-indigo-600 hover:text-indigo-800 font-semibold cursor-pointer"
                  >
                    <span>{isExpanded ? 'Collapse' : 'Explore component'}</span>
                    <ChevronDown className={`w-3.5 h-3.5 transition-transform duration-200 ${isExpanded ? 'rotate-180' : ''}`} />
                  </button>
                  {idx < WORKFLOW_STEPS.length - 1 && (
                    <ArrowDown className="w-3.5 h-3.5 text-slate-400" />
                  )}
                </div>
              </motion.div>
            );
          })}
        </div>

      </div>
    </section>
  );
}
