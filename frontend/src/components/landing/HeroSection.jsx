import { motion } from 'framer-motion';
import { Link } from 'react-router-dom';
import { Sparkles, ArrowRight, Compass, ShieldCheck } from 'lucide-react';
import GeospatialMapVisual from './GeospatialMapVisual';

const FRAMEWORKS = [
  'National Disaster Frameworks',
  'State Emergency Operations',
  'District Relief Cells',
  'Multi-Warehouse Logistics',
  'Tactical Field Responders'
];

export default function HeroSection() {
  const handleScrollToSection = (e, targetId) => {
    e.preventDefault();
    const elem = document.querySelector(targetId);
    if (elem) {
      elem.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  return (
    <section className="relative w-full pt-28 sm:pt-36 pb-16 md:pb-24 overflow-hidden">
      {/* Subtle Atmospheric Light Gradients */}
      <div 
        className="absolute top-0 left-1/2 -translate-x-1/2 w-[1000px] h-[500px] pointer-events-none opacity-60"
        style={{
          background: 'radial-gradient(ellipse at 50% 20%, rgba(99, 102, 241, 0.12) 0%, rgba(20, 184, 166, 0.04) 45%, transparent 70%)'
        }}
      />
      <div 
        className="absolute -top-24 left-1/4 w-[450px] h-[450px] pointer-events-none rounded-full blur-3xl opacity-30"
        style={{ background: '#E0E7FF' }}
      />
      
      <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col items-center text-center">
        
        {/* Eyebrow Pill */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.1, ease: [0.16, 1, 0.3, 1] }}
          className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full border border-indigo-200/90 bg-indigo-50/80 backdrop-blur-md shadow-2xs mb-6"
        >
          <Sparkles className="w-3.5 h-3.5 text-indigo-600" />
          <span className="text-xs font-semibold text-indigo-900 tracking-tight">
            Next-Generation Disaster Response &amp; Relief Infrastructure
          </span>
        </motion.div>

        {/* Hero Headline */}
        <motion.h1
          initial={{ opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.2, ease: [0.16, 1, 0.3, 1] }}
          className="text-4xl sm:text-5xl md:text-6xl lg:text-7xl font-extrabold tracking-tight text-slate-900 max-w-4xl leading-[1.08]"
          style={{ letterSpacing: '-0.03em' }}
        >
          When every second matters, <br className="hidden sm:inline" />
          <span className="bg-gradient-to-r from-indigo-600 via-indigo-700 to-teal-600 bg-clip-text text-transparent">
            every response counts.
          </span>
        </motion.h1>

        {/* Supporting Subtext */}
        <motion.p
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.32, ease: [0.16, 1, 0.3, 1] }}
          className="mt-6 max-w-2xl text-base sm:text-lg text-slate-600 font-normal leading-relaxed"
        >
          Connecting incident intelligence, resource allocation, and emergency response through one coordinated platform.
        </motion.p>

        {/* Action Buttons */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.44, ease: [0.16, 1, 0.3, 1] }}
          className="flex flex-wrap items-center justify-center gap-3.5 mt-8 mb-14"
        >
          {/* Primary CTA — Explore AASHRAY */}
          <motion.a
            href="#how-it-works"
            onClick={(e) => handleScrollToSection(e, '#how-it-works')}
            whileHover={{ scale: 1.03 }}
            whileTap={{ scale: 0.97 }}
            className="px-6 py-3 rounded-full text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-700 shadow-sm hover:shadow-md transition-all flex items-center gap-2 cursor-pointer"
          >
            <span>Explore AASHRAY</span>
            <Compass className="w-4 h-4" />
          </motion.a>

          {/* Secondary CTA — Generic Login */}
          <motion.div whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}>
            <Link
              to="/login"
              className="px-6 py-3 rounded-full text-sm font-semibold text-slate-800 bg-white/90 hover:bg-white border border-slate-200/90 shadow-2xs hover:shadow-xs transition-all flex items-center gap-2"
            >
              <span>Sign In to AASHRAY</span>
              <ArrowRight className="w-4 h-4 text-indigo-600" />
            </Link>
          </motion.div>
        </motion.div>

        {/* Hero Geospatial Visualization */}
        <motion.div
          initial={{ opacity: 0, y: 28 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.55, ease: [0.16, 1, 0.3, 1] }}
          className="w-full"
        >
          <GeospatialMapVisual />
        </motion.div>

        {/* Operational Frameworks Strip */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.7, ease: [0.16, 1, 0.3, 1] }}
          className="w-full max-w-4xl mt-12 pt-8 border-t border-slate-200/70"
        >
          <p className="text-[11px] font-mono tracking-widest uppercase text-slate-400 font-semibold mb-4">
            Engineered for Multi-Agency Emergency Mobilization
          </p>
          <div className="flex flex-wrap items-center justify-center gap-6 sm:gap-10 text-xs font-semibold text-slate-500">
            {FRAMEWORKS.map((item) => (
              <span key={item} className="flex items-center gap-2 hover:text-slate-800 transition-colors">
                <ShieldCheck className="w-4 h-4 text-indigo-500" />
                <span>{item}</span>
              </span>
            ))}
          </div>
        </motion.div>

      </div>
    </section>
  );
}
