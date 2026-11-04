import { Link } from 'react-router-dom';
import { ShieldAlert } from 'lucide-react';

export default function LandingFooter() {
  const handleScrollTo = (e, id) => {
    e.preventDefault();
    const elem = document.querySelector(id);
    if (elem) {
      elem.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  return (
    <footer className="w-full bg-white border-t border-slate-200/80 py-12 sm:py-16 text-slate-500 text-xs">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        
        <div className="flex flex-col md:flex-row items-center md:items-start justify-between gap-8 pb-10 border-b border-slate-100">
          
          {/* Brand & Wordmark */}
          <div className="flex flex-col items-center md:items-start text-center md:text-left">
            <div className="flex items-center gap-2 mb-3">
              <div className="w-7 h-7 rounded-full bg-indigo-600 text-white flex items-center justify-center shadow-xs">
                <ShieldAlert className="w-3.5 h-3.5" />
              </div>
              <span className="text-base font-bold text-slate-900 tracking-tight">
                AASHRAY
              </span>
            </div>
            <p className="max-w-sm text-slate-500 text-xs leading-relaxed font-normal">
              Unified crisis intelligence, multi-warehouse relief allocation, and hazard-verified tactical routing for modern emergency operations.
            </p>
          </div>

          {/* Quick Nav Links */}
          <div className="flex flex-wrap items-center justify-center gap-6 text-xs font-medium text-slate-600">
            <a 
              href="#about" 
              onClick={(e) => handleScrollTo(e, '#about')}
              className="hover:text-indigo-600 transition"
            >
              About
            </a>
            <a 
              href="#how-it-works" 
              onClick={(e) => handleScrollTo(e, '#how-it-works')}
              className="hover:text-indigo-600 transition"
            >
              How It Works
            </a>
            <a 
              href="#capabilities" 
              onClick={(e) => handleScrollTo(e, '#capabilities')}
              className="hover:text-indigo-600 transition"
            >
              Capabilities
            </a>
            <a 
              href="#technology" 
              onClick={(e) => handleScrollTo(e, '#technology')}
              className="hover:text-indigo-600 transition"
            >
              Technology
            </a>
            <Link 
              to="/login" 
              className="font-semibold text-indigo-600 hover:text-indigo-800 transition"
            >
              Platform Login
            </Link>
          </div>

        </div>

        {/* Bottom Metadata */}
        <div className="pt-8 flex flex-col sm:flex-row items-center justify-between gap-4 text-center sm:text-left text-[11px] text-slate-400">
          <p>
            &copy; {new Date().getFullYear()} AASHRAY Disaster Intelligence &amp; Response Platform. All rights reserved.
          </p>
          <p className="font-mono text-[10px]">
            JEV &bull; RAG &bull; RESOURCE &bull; ROUTE ENGINES
          </p>
        </div>

      </div>
    </footer>
  );
}
