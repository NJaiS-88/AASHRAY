import LandingNavbar from '../components/landing/LandingNavbar';
import HeroSection from '../components/landing/HeroSection';
import ProblemSection from '../components/landing/ProblemSection';
import WorkflowSection from '../components/landing/WorkflowSection';
import CompactScenarioVisualization from '../components/landing/CompactScenarioVisualization';
import CapabilitiesSection from '../components/landing/CapabilitiesSection';
import PlatformPreviewSection from '../components/landing/PlatformPreviewSection';
import ClosingBrandSection from '../components/landing/ClosingBrandSection';
import LandingFooter from '../components/landing/LandingFooter';

export default function LandingPage() {
  return (
    <div className="min-h-screen flex flex-col bg-[#FAFBFF] text-slate-800 antialiased selection:bg-indigo-100 selection:text-indigo-800">
      {/* Monsoon-style Floating Frosted Pill Navbar */}
      <LandingNavbar />

      {/* Main Content Sections */}
      <main className="flex-1 w-full flex flex-col">
        {/* Section 1: Hero */}
        <HeroSection />

        {/* Section 2: The Problem */}
        <ProblemSection />

        {/* Section 3: How It Works */}
        <WorkflowSection />

        {/* Section 4: Compact End-to-End Scenario Visualization */}
        <CompactScenarioVisualization />

        {/* Section 5: Core Capabilities */}
        <CapabilitiesSection />

        {/* Section 6: Platform Visualization */}
        <PlatformPreviewSection />

        {/* Section 7: Closing Brand Section */}
        <ClosingBrandSection />
      </main>

      {/* Footer */}
      <LandingFooter />
    </div>
  );
}
