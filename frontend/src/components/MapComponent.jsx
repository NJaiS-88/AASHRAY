import { useEffect, useRef, useState } from 'react';

export default function MapComponent({ lat, lng, isExpandable = true }) {
  const mapContainerRef = useRef(null);
  const mapInstanceRef = useRef(null);
  const [expanded, setExpanded] = useState(false);
  const [leafletLoaded, setLeafletLoaded] = useState(false);

  useEffect(() => {
    // Check if Leaflet is already loaded on window
    if (window.L) {
      setLeafletLoaded(true);
      return;
    }

    // Load CSS
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
    document.head.appendChild(link);

    // Load JS
    const script = document.createElement('script');
    script.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
    script.async = true;
    script.onload = () => {
      setLeafletLoaded(true);
    };
    document.body.appendChild(script);
  }, []);

  useEffect(() => {
    if (!leafletLoaded || !window.L || !mapContainerRef.current) return;

    // Clean up previous instance
    if (mapInstanceRef.current) {
      mapInstanceRef.current.remove();
      mapInstanceRef.current = null;
    }

    try {
      const L = window.L;
      
      // Setup map
      const map = L.map(mapContainerRef.current, {
        zoomControl: false,
        attributionControl: false
      }).setView([lat, lng], 14);

      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
      }).addTo(map);

      // Add a customized circle marker that looks premium
      L.circleMarker([lat, lng], {
        color: '#3b82f6',
        fillColor: '#3b82f6',
        fillOpacity: 0.5,
        radius: 8
      }).addTo(map);

      mapInstanceRef.current = map;

      // Force resize calculation
      setTimeout(() => {
        if (mapInstanceRef.current) {
          mapInstanceRef.current.invalidateSize();
        }
      }, 200);
    } catch (err) {
      console.error('Error rendering Leaflet map:', err);
    }

    return () => {
      if (mapInstanceRef.current) {
        mapInstanceRef.current.remove();
        mapInstanceRef.current = null;
      }
    };
  }, [leafletLoaded, lat, lng, expanded]);

  return (
    <div className="flex flex-col gap-1 w-full max-w-md">
      <div 
        ref={mapContainerRef} 
        style={{ height: expanded ? '280px' : '140px' }} 
        className={`relative z-0 isolate w-full rounded-xl border border-zinc-200/50 shadow-sm transition-all duration-300 overflow-hidden ${isExpandable ? 'cursor-pointer hover:border-zinc-300' : ''}`}
        onClick={() => isExpandable && setExpanded(!expanded)}
      />
      <div className="flex justify-between items-center text-[10px] text-zinc-500 px-1 font-mono">
        <span>Coordinates: {lat.toFixed(5)}, {lng.toFixed(5)}</span>
        {isExpandable && (
          <span className="text-blue-500 hover:text-blue-600 transition-colors font-medium">
            {expanded ? 'Collapse Map' : 'Expand Map'}
          </span>
        )}
      </div>
    </div>
  );
}
