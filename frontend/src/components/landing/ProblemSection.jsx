import { motion } from 'framer-motion';
import { 
  FileWarning, 
  Clock, 
  Scale, 
  EyeOff, 
  Network, 
  MapPinOff, 
  ArrowDownRight 
} from 'lucide-react';

const PROBLEMS = [
  {
    icon: FileWarning,
    title: 'Fragmented Incident Reporting',
    description:
      'Distress calls flood in across disconnected consumer channels with unverified GPS coordinates, conflicting casualty reports, and missing critical context.',
    tag: 'INTAKE BOTTLENECK'
  },
  {
    icon: Clock,
    title: 'Delayed Incident Assessment',
    description:
      'Emergency coordinators spend precious Golden Hours manually cross-referencing disaster severities and reading scattered reports instead of dispatching life-saving aid.',
    tag: 'TRIAGE DELAY'
  },
  {
    icon: Scale,
    title: 'Inefficient Resource Allocation',
    description:
      'Relief supplies are routinely miscalculated through manual guesswork, creating severe shortages of life-critical items in high-casualty sectors while surplus accumulates elsewhere.',
    tag: 'SUPPLY MISMATCH'
  },
  {
    icon: EyeOff,
    title: 'Limited Inventory Visibility',
    description:
      'Command centers lack unified, real-time tracking across regional warehouses, leading to stockouts of pediatric medicines, clean water, and heavy rescue gear.',
    tag: 'DEPOT BLIND SPOTS'
  },
  {
    icon: Network,
    title: 'Disconnected Emergency Operations',
    description:
      'Field rescue teams, warehouse dispatchers, and state emergency operating centers work in distinct silos without a single synchronized operational truth.',
    tag: 'SILOED PROTOCOLS'
  },
  {
    icon: MapPinOff,
    title: 'Difficult Route & Responder Coordination',
    description:
      'Convoys navigate blind into flooded arterial roads and collapsed bridges due to static routing tools that fail to incorporate live hazard barriers.',
    tag: 'CORRIDOR FAILURES'
  }
];

export default function ProblemSection() {
  return (
    <section id="about" className="relative w-full py-20 sm:py-28 bg-[#F5F7FC]/60 border-t border-slate-200/60">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        
        {/* Section Header */}
        <div className="max-w-3xl mb-16">
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-mono font-semibold text-rose-700 bg-rose-50 border border-rose-200 mb-4">
            <span>OPERATIONAL REALITY</span>
          </div>
          
          <h2 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold text-slate-900 tracking-tight leading-[1.15]">
            Disaster response requires more than information.{' '}
            <span className="text-indigo-600 block sm:inline">
              It requires coordination.
            </span>
          </h2>
          
          <p className="mt-4 text-base sm:text-lg text-slate-600 leading-relaxed font-normal">
            In catastrophic scenarios, fragmented data silos and disconnected logistics delay aid when every minute decides survivability. AASHRAY solves the systemic breakdowns that paralyze crisis response.
          </p>
        </div>

        {/* 6-Card Minimal Editorial Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {PROBLEMS.map((problem, idx) => {
            const Icon = problem.icon;
            return (
              <motion.div
                key={problem.title}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: '-50px' }}
                transition={{ duration: 0.5, delay: idx * 0.08 }}
                whileHover={{ y: -4, transition: { duration: 0.2 } }}
                className="rounded-2xl p-6 sm:p-7 bg-white border border-slate-200/80 shadow-2xs hover:shadow-md transition-all flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-center justify-between mb-5">
                    <div className="w-11 h-11 rounded-xl bg-slate-50 border border-slate-200 text-slate-700 flex items-center justify-center">
                      <Icon className="w-5 h-5 text-indigo-600" />
                    </div>
                    <span className="text-[10px] font-mono tracking-wider text-slate-400 font-semibold">
                      {problem.tag}
                    </span>
                  </div>

                  <h3 className="text-lg font-bold text-slate-900 mb-2 leading-snug">
                    {problem.title}
                  </h3>

                  <p className="text-xs sm:text-sm text-slate-600 leading-relaxed font-normal">
                    {problem.description}
                  </p>
                </div>

                <div className="pt-5 mt-5 border-t border-slate-100 flex items-center justify-between text-[11px] font-mono text-slate-400">
                  <span>CHALLENGE 0{idx + 1}</span>
                  <ArrowDownRight className="w-3.5 h-3.5 text-slate-300" />
                </div>
              </motion.div>
            );
          })}
        </div>

      </div>
    </section>
  );
}
