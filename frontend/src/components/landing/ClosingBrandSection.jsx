import { motion } from 'framer-motion';
import { Link } from 'react-router-dom';
import { ShieldAlert, ArrowRight, Compass } from 'lucide-react';

export default function ClosingBrandSection() {
  return (
    <section className="relative w-full py-24 sm:py-32 bg-gradient-to-b from-[#FAFBFF] to-[#F1F4F9] overflow-hidden border-t border-slate-200/60">
      
      {/* Subtle Ambient Radial Backlight */}
      <div 
        className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[400px] pointer-events-none opacity-50"
        style={{
          background: 'radial-gradient(ellipse at center, rgba(79, 70, 229, 0.12) 0%, rgba(13, 148, 136, 0.04) 50%, transparent 70%)'
        }}
      />

      <div className="relative max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 text-center flex flex-col items-center">
        
        {/* Emblem */}
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          whileInView={{ opacity: 1, scale: 1 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5 }}
          className="w-16 h-16 rounded-3xl bg-indigo-600 text-white flex items-center justify-center shadow-lg shadow-indigo-600/20 mb-8"
        >
          <ShieldAlert className="w-8 h-8" />
        </motion.div>

        {/* Brand Headline */}
        <motion.h2
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6, delay: 0.1 }}
          className="text-4xl sm:text-5xl md:text-6xl font-extrabold text-slate-900 tracking-tight leading-tight"
          style={{ letterSpacing: '-0.03em' }}
        >
          Intelligence. Allocation. Response.
        </motion.h2>

        {/* Supporting Message */}
        <motion.p
          initial={{ opacity: 0, y: 14 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6, delay: 0.2 }}
          className="mt-6 max-w-2xl text-base sm:text-xl text-slate-600 font-normal leading-relaxed"
        >
          One coordinated platform for a faster, more informed emergency response.
        </motion.p>

        {/* Generic Login CTA */}
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6, delay: 0.3 }}
          className="mt-10"
        >
          <Link
            to="/login"
            className="inline-flex items-center gap-2.5 px-8 py-3.5 rounded-full text-sm sm:text-base font-semibold text-white bg-indigo-600 hover:bg-indigo-700 shadow-md hover:shadow-lg transition-all"
          >
            <span>Sign In to AASHRAY</span>
            <ArrowRight className="w-4 h-4" />
          </Link>
          <p className="text-xs text-slate-400 mt-3 font-medium">
            Unified access for both community citizens and authorized coordinators
          </p>
        </motion.div>

      </div>
    </section>
  );
}
