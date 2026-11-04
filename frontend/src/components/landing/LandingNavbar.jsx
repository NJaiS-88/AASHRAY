import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { ShieldAlert, ArrowRight, Menu, X, ArrowUpRight } from 'lucide-react';

const NAV_LINKS = [
  { label: 'About', href: '#about' },
  { label: 'How It Works', href: '#how-it-works' },
  { label: 'Capabilities', href: '#capabilities' },
  { label: 'Technology', href: '#technology' },
];

export default function LandingNavbar() {
  const [scrolled, setScrolled] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  useEffect(() => {
    const handleScroll = () => {
      setScrolled(window.scrollY > 20);
    };
    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  const handleLinkClick = (e, href) => {
    e.preventDefault();
    setMobileMenuOpen(false);
    const target = document.querySelector(href);
    if (target) {
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  return (
    <header className="fixed top-4 sm:top-5 left-0 right-0 z-50 flex justify-center px-4 pointer-events-none">
      <motion.nav
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
        className={`pointer-events-auto w-full max-w-4xl rounded-full transition-all duration-300 ${
          scrolled
            ? 'bg-white/85 shadow-[0_12px_32px_rgba(15,23,42,0.08)] border-slate-200/90'
            : 'bg-white/70 shadow-[0_8px_24px_rgba(15,23,42,0.05)] border-slate-200/70'
        } backdrop-blur-xl border px-3 sm:px-4 py-2 sm:py-2.5 flex items-center justify-between gap-3`}
      >
        {/* Brand Logo & Wordmark */}
        <a
          href="#"
          onClick={(e) => {
            e.preventDefault();
            window.scrollTo({ top: 0, behavior: 'smooth' });
          }}
          className="flex items-center gap-2 group shrink-0 pl-1"
        >
          <div className="w-8 h-8 rounded-full bg-indigo-600 text-white flex items-center justify-center shadow-xs group-hover:bg-indigo-700 transition">
            <ShieldAlert className="w-4 h-4" />
          </div>
          <div className="flex flex-col">
            <span className="text-sm font-bold tracking-tight text-slate-900 group-hover:text-indigo-600 transition leading-none">
              AASHRAY
            </span>
            <span className="text-[9px] font-mono tracking-wider text-slate-400 uppercase mt-0.5 leading-none">
              Crisis OS
            </span>
          </div>
        </a>

        {/* Desktop Navigation Links */}
        <div className="hidden md:flex items-center gap-1 lg:gap-2">
          {NAV_LINKS.map((link) => (
            <a
              key={link.label}
              href={link.href}
              onClick={(e) => handleLinkClick(e, link.href)}
              className="text-xs font-medium text-slate-600 hover:text-indigo-600 px-3 py-1.5 rounded-full hover:bg-slate-100/70 transition-colors"
            >
              {link.label}
            </a>
          ))}
        </div>

        {/* Right CTA — Generic Login Button */}
        <div className="flex items-center gap-2">
          <Link
            to="/login"
            className="inline-flex items-center gap-1.5 text-xs font-semibold px-4 py-1.5 rounded-full text-white bg-indigo-600 hover:bg-indigo-700 shadow-xs hover:shadow transition-all duration-200"
          >
            <span>Login</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </Link>

          {/* Mobile Menu Toggle Button */}
          <button
            type="button"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="md:hidden w-8 h-8 rounded-full flex items-center justify-center text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition"
            aria-label="Toggle navigation menu"
          >
            {mobileMenuOpen ? <X className="w-4 h-4" /> : <Menu className="w-4 h-4" />}
          </button>
        </div>
      </motion.nav>

      {/* Mobile Menu Dropdown */}
      <AnimatePresence>
        {mobileMenuOpen && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: -10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: -10 }}
            transition={{ duration: 0.2 }}
            className="pointer-events-auto absolute top-16 left-4 right-4 max-w-sm mx-auto bg-white/95 backdrop-blur-xl border border-slate-200 rounded-2xl p-4 shadow-xl md:hidden"
          >
            <div className="flex flex-col gap-1">
              {NAV_LINKS.map((link) => (
                <a
                  key={link.label}
                  href={link.href}
                  onClick={(e) => handleLinkClick(e, link.href)}
                  className="px-3 py-2 text-sm font-medium text-slate-700 hover:text-indigo-600 hover:bg-slate-50 rounded-xl transition flex items-center justify-between"
                >
                  <span>{link.label}</span>
                  <ArrowUpRight className="w-3.5 h-3.5 text-slate-400" />
                </a>
              ))}
              <div className="pt-2 mt-2 border-t border-slate-100 flex flex-col gap-2">
                <Link
                  to="/login"
                  onClick={() => setMobileMenuOpen(false)}
                  className="w-full py-2.5 text-center text-xs font-semibold rounded-xl text-white bg-indigo-600 hover:bg-indigo-700 transition"
                >
                  Sign In to AASHRAY
                </Link>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </header>
  );
}
