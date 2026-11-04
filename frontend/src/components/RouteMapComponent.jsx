import React, { useEffect, useRef, useState } from 'react';
import { 
  Maximize2, 
  RotateCcw, 
  Layers, 
  ShieldAlert, 
  CheckCircle2, 
  XCircle, 
  AlertTriangle,
  Info,
  Navigation,
  Eye,
  Check,
  Ban
} from 'lucide-react';

function RouteMapInner({
  routeData,
  agentAssignment,
  incident,
  onSelectAlternative
}) {
  const mapContainerRef = useRef(null);
  const mapInstanceRef = useRef(null);
  const layersRef = useRef({ polylines: [], markers: [] });
  const [leafletLoaded, setLeafletLoaded] = useState(false);
  const [activeCandidateId, setActiveCandidateId] = useState(null);
  const [showAlternatives, setShowAlternatives] = useState(true);

  // Clear previous mission's inspection state immediately on mission/incident change
  useEffect(() => {
    setActiveCandidateId(null);
  }, [incident?.incident_id, routeData?.route_id]);

  // Dynamically load Leaflet assets if not yet available
  useEffect(() => {
    if (window.L) {
      setLeafletLoaded(true);
      return;
    }

    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
    document.head.appendChild(link);

    const script = document.createElement('script');
    script.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
    script.async = true;
    script.onload = () => {
      setLeafletLoaded(true);
    };
    document.body.appendChild(script);
  }, []);

  // Collect primary route points from actual routeData
  const primaryCoords = React.useMemo(() => {
    if (!routeData) return [];
    if (Array.isArray(routeData.coordinates) && routeData.coordinates.length > 0) {
      return routeData.coordinates
        .map(c => [Number(c.latitude ?? c[0]), Number(c.longitude ?? c[1])])
        .filter(pt => !isNaN(pt[0]) && !isNaN(pt[1]) && pt[0] !== 0 && pt[1] !== 0);
    }
    // Fallback: collect from legs
    if (Array.isArray(routeData.legs)) {
      const pts = [];
      routeData.legs.forEach(leg => {
        if (Array.isArray(leg.coordinates)) {
          leg.coordinates.forEach(c => {
            const lat = Number(c.latitude ?? c[0]);
            const lng = Number(c.longitude ?? c[1]);
            if (!isNaN(lat) && !isNaN(lng) && lat !== 0 && lng !== 0) {
              pts.push([lat, lng]);
            }
          });
        }
      });
      return pts;
    }
    return [];
  }, [routeData]);

  // Extract checkpoints
  const checkpoints = React.useMemo(() => {
    const list = [];
    if (!routeData?.legs) return list;

    routeData.legs.forEach((leg, idx) => {
      // Source checkpoint
      if (idx === 0 && leg.source_location) {
        const lat = Number(leg.source_location.latitude);
        const lng = Number(leg.source_location.longitude);
        if (!isNaN(lat) && !isNaN(lng)) {
          list.push({
            id: leg.source_id || 'Responder Base',
            type: leg.source_type || 'RESPONDER',
            lat,
            lng,
            label: leg.source_id
          });
        }
      }
      // Intermediate or destination checkpoint
      if (leg.destination_location) {
        const lat = Number(leg.destination_location.latitude);
        const lng = Number(leg.destination_location.longitude);
        if (!isNaN(lat) && !isNaN(lng)) {
          list.push({
            id: leg.destination_id || `Checkpoint ${idx + 1}`,
            type: leg.destination_type || (idx === routeData.legs.length - 1 ? 'DESTINATION' : 'WAREHOUSE'),
            lat,
            lng,
            label: leg.destination_id
          });
        }
      }
    });

    return list;
  }, [routeData]);

  // Selected Primary Candidate
  const selectedCandidate = React.useMemo(() => {
    if (!routeData) return null;
    return {
      id: routeData.route_id || 'primary-dispatched-route',
      status: 'SELECTED',
      selection_status: 'SELECTED',
      distance_km: routeData.distance_km || 0,
      estimated_time_minutes: routeData.estimated_time_minutes || 0,
      risk_score: routeData.legs?.[0]?.score ?? 'Optimal',
      rejection_reason: null,
      coords: primaryCoords,
      description: 'Verified Primary Emergency Corridor (Optimal Risk-Adjusted Score)'
    };
  }, [routeData, primaryCoords]);

  // Feasible Alternatives (genuine viable backup routes, NOT rejected)
  const feasibleCandidates = React.useMemo(() => {
    const backupList = routeData?.alternative_routes || [];
    return backupList.map((b, i) => {
      const pts = (b.coordinates || [])
        .map(c => [Number(c.latitude ?? c[0]), Number(c.longitude ?? c[1])])
        .filter(pt => !isNaN(pt[0]) && !isNaN(pt[1]) && pt[0] !== 0 && pt[1] !== 0);
      return {
        id: b.route_id || `feasible-corridor-${i + 1}`,
        status: 'FEASIBLE_ALTERNATIVE',
        selection_status: 'FEASIBLE_ALTERNATIVE',
        distance_km: b.distance_km || 0,
        estimated_time_minutes: b.estimated_time_minutes || 0,
        risk_score: b.risk_score ?? 'N/A',
        rejection_reason: null,
        coords: pts,
        description: 'Feasible secondary corridor. Retained as valid alternative candidate.'
      };
    });
  }, [routeData]);

  // Genuinely Rejected Routes (failed verified safety/blocking rules)
  const rejectedCandidates = React.useMemo(() => {
    const rejectedList = routeData?.rejected_routes || [];
    return rejectedList.map((r, i) => {
      const pts = (r.coordinates || [])
        .map(c => [Number(c.latitude ?? c[0]), Number(c.longitude ?? c[1])])
        .filter(pt => !isNaN(pt[0]) && !isNaN(pt[1]) && pt[0] !== 0 && pt[1] !== 0);
      return {
        id: r.route_id || `rejected-corridor-${i + 1}`,
        status: r.status === 'UNAVAILABLE' ? 'UNAVAILABLE' : 'REJECTED',
        selection_status: r.status === 'UNAVAILABLE' ? 'UNAVAILABLE' : 'REJECTED',
        distance_km: r.distance_km || 0,
        estimated_time_minutes: r.estimated_time_minutes || 0,
        risk_score: r.risk_score ?? 'N/A',
        rejection_reason: r.rejection_reason || 'Candidate route failed safety verification rules.',
        rule_violated: r.rule_violated || r.blocking_condition || 'SAFETY_RULE_VIOLATION',
        evidence_source: r.evidence_source || 'RoadConditionEngine',
        confidence: r.confidence,
        coords: pts,
        hasGeometry: pts.length >= 2,
        description: r.rejection_reason || 'Candidate route failed safety verification rules.'
      };
    });
  }, [routeData]);

  // All candidates combined for map rendering
  const allCandidates = React.useMemo(() => {
    const list = [];
    if (selectedCandidate) list.push(selectedCandidate);
    feasibleCandidates.forEach(c => list.push(c));
    rejectedCandidates.forEach(c => list.push(c));
    return list;
  }, [selectedCandidate, feasibleCandidates, rejectedCandidates]);

  // Fit bounds helper
  const handleFitBounds = () => {
    if (!mapInstanceRef.current || !window.L) return;
    const L = window.L;
    const allPts = [];

    primaryCoords.forEach(pt => allPts.push(pt));
    checkpoints.forEach(cp => allPts.push([cp.lat, cp.lng]));

    if (allPts.length > 0) {
      const bounds = L.latLngBounds(allPts);
      mapInstanceRef.current.fitBounds(bounds, { padding: [40, 40], maxZoom: 15 });
    }
  };

  // Initialize and update map
  useEffect(() => {
    if (!leafletLoaded || !window.L || !mapContainerRef.current) return;
    const L = window.L;

    // Destroy previous instance
    if (mapInstanceRef.current) {
      mapInstanceRef.current.remove();
      mapInstanceRef.current = null;
    }

    try {
      // Default center: first checkpoint, incident location, or Mumbai default
      const defaultCenter = checkpoints[0]
        ? [checkpoints[0].lat, checkpoints[0].lng]
        : (incident?.location ? [incident.location.latitude, incident.location.longitude] : [19.076, 72.877]);

      const map = L.map(mapContainerRef.current, {
        zoomControl: true,
        attributionControl: false
      }).setView(defaultCenter, 12);

      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
      }).addTo(map);

      mapInstanceRef.current = map;
      layersRef.current = { polylines: [], markers: [] };

      // Render Checkpoint Markers
      checkpoints.forEach(cp => {
        let badgeBg = '#4F46E5';
        let badgeIcon = '🚑';
        if (cp.type === 'WAREHOUSE') {
          badgeBg = '#D97706';
          badgeIcon = '📦';
        } else if (cp.type === 'DESTINATION') {
          badgeBg = '#DC2626';
          badgeIcon = '🚨';
        }

        const iconHtml = `
          <div style="background:${badgeBg}; color:white; padding:3px 7px; border-radius:12px; font-size:10px; font-weight:700; box-shadow:0 2px 8px rgba(0,0,0,0.3); display:flex; align-items:center; gap:4px; border:2px solid #FFFFFF; white-space:nowrap;">
            <span>${badgeIcon}</span>
            <span>${cp.label}</span>
          </div>
        `;

        const customIcon = L.divIcon({
          className: 'custom-map-checkpoint',
          html: iconHtml,
          iconSize: [85, 26],
          iconAnchor: [42, 13]
        });

        const marker = L.marker([cp.lat, cp.lng], { icon: customIcon }).addTo(map);
        marker.bindPopup(`
          <div style="font-family:sans-serif; font-size:12px; padding:2px;">
            <strong style="color:${badgeBg};">${cp.type} CHECKPOINT</strong><br/>
            <span>${cp.label}</span><br/>
            <span style="font-family:monospace; color:#64748B;">Lat: ${cp.lat.toFixed(4)}, Lng: ${cp.lng.toFixed(4)}</span>
          </div>
        `);
        layersRef.current.markers.push(marker);
      });

      // Render Candidate Polylines
      allCandidates.forEach(cand => {
        // If geometry is missing, do not draw a fake line on the map
        if (!cand.coords || cand.coords.length < 2) return;
        if (cand.status !== 'SELECTED' && !showAlternatives) return;

        let strokeColor = '#10B981'; // green for selected
        let strokeDash = null;
        let strokeWeight = 6;
        let strokeOpacity = 0.95;

        if (cand.status === 'FEASIBLE_ALTERNATIVE') {
          strokeColor = '#3B82F6'; // neutral blue for feasible alternative
          strokeDash = '6, 8';
          strokeWeight = 4;
          strokeOpacity = 0.8;
        } else if (cand.status === 'REJECTED') {
          strokeColor = '#EF4444'; // red for genuinely rejected
          strokeDash = '3, 6';
          strokeWeight = 4;
          strokeOpacity = 0.85;
        }

        // Highlight if activeCandidateId
        if (activeCandidateId && activeCandidateId === cand.id) {
          strokeWeight = 8;
          strokeOpacity = 1.0;
        }

        const poly = L.polyline(cand.coords, {
          color: strokeColor,
          weight: strokeWeight,
          opacity: strokeOpacity,
          dashArray: strokeDash
        }).addTo(map);

        poly.bindPopup(`
          <div style="font-family:sans-serif; font-size:12px; min-width:180px;">
            <div style="font-weight:bold; color:${strokeColor}; margin-bottom:4px;">
              ${cand.status === 'SELECTED' ? '✓ SELECTED ROUTE' : (cand.status === 'REJECTED' ? '✕ REJECTED ROUTE' : '⇄ FEASIBLE ALTERNATIVE')}
            </div>
            <div><strong>ID:</strong> <span style="font-family:monospace;">${cand.id}</span></div>
            <div><strong>Distance:</strong> ${cand.distance_km} km</div>
            <div><strong>Est. Time:</strong> ${cand.estimated_time_minutes} mins</div>
            <div><strong>Risk Score:</strong> ${cand.risk_score}</div>
            ${cand.rejection_reason ? `<div style="margin-top:4px; color:#DC2626; font-size:11px;">⚠️ ${cand.rejection_reason}</div>` : ''}
          </div>
        `);
        layersRef.current.polylines.push(poly);
      });

      // Fit bounds
      handleFitBounds();

      setTimeout(() => {
        if (mapInstanceRef.current) {
          mapInstanceRef.current.invalidateSize();
        }
      }, 250);

    } catch (err) {
      console.error('Failed to initialize Leaflet route map:', err);
    }

    return () => {
      if (mapInstanceRef.current) {
        mapInstanceRef.current.remove();
        mapInstanceRef.current = null;
      }
    };
  }, [leafletLoaded, routeData, checkpoints, allCandidates, showAlternatives, activeCandidateId]);

  const hasRoute = primaryCoords.length > 0;
  const isThresholdExceeded = Boolean(routeData?.emergency_threshold_exceeded);
  const thresholdMin = routeData?.emergency_threshold_minutes || 90;
  const thresholdWarning = routeData?.emergency_threshold_warning;

  return (
    <div className="flex flex-col gap-4">
      {/* Emergency ETA Threshold Warning Banner if exceeded */}
      {isThresholdExceeded && (
        <div className="p-3.5 rounded-xl border flex items-start gap-2.5 shadow-sm" style={{ background: '#FEF2F2', borderColor: '#FECACA' }}>
          <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
          <div className="flex flex-col gap-0.5">
            <span className="text-xs font-bold text-rose-900 flex items-center gap-1.5">
              EMERGENCY ETA SAFEGUARD ESCALATION: Response Time Target Exceeded
              <span className="px-1.5 py-0.2 rounded text-[10px] font-mono bg-rose-200 text-rose-800">
                Target: {thresholdMin} min
              </span>
            </span>
            <p className="text-[11px] text-rose-800 leading-relaxed">
              {thresholdWarning || `Calculated arrival time (${routeData.estimated_time_minutes} min) exceeds the operational review threshold of ${thresholdMin} min for this time-critical incident. Priority corridor escort and multi-agency review flagged.`}
            </p>
          </div>
        </div>
      )}

      {/* Map Card */}
      <div className="rounded-2xl border overflow-hidden shadow-sm flex flex-col" style={{ background: 'var(--surface-white)', borderColor: 'var(--border)' }}>
        
        {/* Map Header Toolbar */}
        <div className="p-3 px-4 border-b flex flex-wrap items-center justify-between gap-2 text-xs" style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border)' }}>
          <div className="flex items-center gap-2">
            <Navigation className="w-4 h-4" style={{ color: 'var(--brand)' }} />
            <span className="font-bold uppercase tracking-wider" style={{ color: 'var(--heading-text)' }}>
              Interactive Live Route Corridor Map
            </span>
            {hasRoute ? (
              <span className="px-2 py-0.5 rounded-full text-[10px] font-mono font-semibold border" style={{ background: '#ECFDF5', borderColor: '#A7F3D0', color: 'var(--success)' }}>
                GPS Road Network Grounded
              </span>
            ) : (
              <span className="px-2 py-0.5 rounded-full text-[10px] font-mono font-semibold border" style={{ background: '#FFFBEB', borderColor: '#FDE68A', color: 'var(--warning)' }}>
                Awaiting Route Coordinates
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowAlternatives(!showAlternatives)}
              className="flex items-center gap-1 px-2.5 py-1 rounded-lg border text-[11px] font-medium transition cursor-pointer"
              style={{
                background: showAlternatives ? 'var(--primary-soft)' : 'var(--surface-white)',
                borderColor: showAlternatives ? 'var(--brand-muted)' : 'var(--border)',
                color: showAlternatives ? 'var(--brand)' : 'var(--body-text)'
              }}
              title="Toggle alternative and rejected routes on the map"
            >
              <Layers className="w-3.5 h-3.5" />
              {showAlternatives ? 'Hide Alternatives' : 'Show Alternatives'}
            </button>

            <button
              onClick={handleFitBounds}
              className="flex items-center gap-1 px-2.5 py-1 rounded-lg border text-[11px] font-medium transition cursor-pointer"
              style={{ background: 'var(--surface-white)', borderColor: 'var(--border)', color: 'var(--heading-text)' }}
              title="Recenter and fit visible route bounds"
            >
              <Maximize2 className="w-3.5 h-3.5" />
              Fit Route
            </button>
          </div>
        </div>

        {/* Map Container View */}
        <div className="relative">
          <div
            ref={mapContainerRef}
            className="w-full h-[360px] md:h-[400px]"
            style={{ background: '#F1F5F9' }}
          />

          {!hasRoute && (
            <div className="absolute inset-0 bg-slate-50/80 backdrop-blur-xs flex flex-col items-center justify-center p-6 text-center z-10">
              <ShieldAlert className="w-8 h-8 text-slate-400 mb-2" />
              <p className="text-xs font-semibold text-slate-700">No Road Route Geometry Available Yet</p>
              <p className="text-[11px] text-slate-500 max-w-sm mt-1">
                Execute the orchestration pipeline to compute genuine road geometry, checkpoints, and risk-adjusted alternatives.
              </p>
            </div>
          )}

          {/* Map Legend Overlay */}
          <div className="absolute bottom-3 left-3 bg-white/95 backdrop-blur-xs p-2.5 rounded-xl border shadow-sm z-[1000] text-[10px] flex flex-col gap-1.5" style={{ borderColor: 'var(--border)' }}>
            <span className="font-bold uppercase tracking-wider text-slate-700">Route Map Legend</span>
            <div className="flex items-center gap-2">
              <span className="w-3 h-1 rounded-full bg-emerald-500 inline-block"></span>
              <span className="font-medium text-slate-800">Selected Primary Route</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-3 h-1 rounded-full bg-blue-500 inline-block border-b border-dashed"></span>
              <span className="font-medium text-slate-800">Feasible Alternative (Viable Backup)</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-3 h-1 rounded-full bg-rose-500 inline-block border-b border-dotted"></span>
              <span className="font-medium text-slate-800">Explicitly Rejected Candidate (Unsafe)</span>
            </div>
            <div className="border-t pt-1 flex items-center gap-2 text-slate-500">
              <span>🚑 Base</span>
              <span>•</span>
              <span>📦 Warehouse</span>
              <span>•</span>
              <span>🚨 Incident Site</span>
            </div>
          </div>
        </div>

        {/* Route Candidates Section Grouping */}
        <div className="p-4 border-t flex flex-col gap-4" style={{ borderColor: 'var(--border)', background: 'var(--bg-secondary)' }}>
          
          {/* SECTION 1: Selected Operational Corridor */}
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-bold uppercase tracking-wider flex items-center gap-1.5 text-emerald-800">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                Selected Operational Corridor
              </span>
              <span className="text-[11px] text-slate-500 font-mono">
                Provider Grounded: {routeData?.route_engine_mission_id || 'Route Engine v1'}
              </span>
            </div>

            {selectedCandidate ? (
              <div 
                className="p-3.5 rounded-xl border flex flex-col md:flex-row md:items-center justify-between gap-3 shadow-2xs"
                style={{ 
                  background: activeCandidateId === selectedCandidate.id ? '#D1FAE5' : '#ECFDF5', 
                  borderColor: activeCandidateId === selectedCandidate.id ? '#059669' : '#A7F3D0' 
                }}
              >
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-mono text-xs font-bold text-slate-800" title={selectedCandidate.id}>
                      {selectedCandidate.id}
                    </span>
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-bold font-mono border bg-emerald-100 text-emerald-800 border-emerald-300">
                      SELECTED
                    </span>
                    <span className="text-[10px] text-emerald-700 font-medium">
                      Operational Dispatch Primary
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-600">
                    {selectedCandidate.description}
                  </p>
                </div>

                <div className="flex items-center gap-4">
                  <div className="flex items-center gap-3 text-xs font-mono text-slate-700">
                    <div>
                      <span className="text-[9px] block uppercase text-slate-400">Dist</span>
                      <span className="font-bold">{selectedCandidate.distance_km} km</span>
                    </div>
                    <div>
                      <span className="text-[9px] block uppercase text-slate-400">ETA</span>
                      <span className="font-bold">{selectedCandidate.estimated_time_minutes} min</span>
                    </div>
                    <div>
                      <span className="text-[9px] block uppercase text-slate-400">Score</span>
                      <span className="font-bold text-emerald-700">{selectedCandidate.risk_score}</span>
                    </div>
                  </div>

                  <button
                    onClick={() => setActiveCandidateId(activeCandidateId === selectedCandidate.id ? null : selectedCandidate.id)}
                    className="py-1 px-2.5 rounded-lg text-[11px] font-semibold border flex items-center justify-center gap-1 bg-white hover:bg-slate-50 transition cursor-pointer text-slate-700 border-slate-300 shadow-2xs"
                  >
                    <Eye className="w-3.5 h-3.5 text-slate-500" />
                    {activeCandidateId === selectedCandidate.id ? 'Deselect' : 'Inspect'}
                  </button>
                </div>
              </div>
            ) : (
              <div className="p-3 rounded-xl border text-xs text-center text-slate-500 bg-white border-slate-200">
                Awaiting route planning execution.
              </div>
            )}
          </div>

          {/* SECTION 2: Feasible Alternative Corridors */}
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-bold uppercase tracking-wider flex items-center gap-1.5 text-blue-800">
                <Layers className="w-3.5 h-3.5 text-blue-600" />
                Feasible Alternative Corridors ({feasibleCandidates.length})
              </span>
              <span className="text-[10px] text-slate-500">
                Viable backup routes ready for dynamic promotion
              </span>
            </div>

            {feasibleCandidates.length === 0 ? (
              <div className="p-3 rounded-xl border text-xs text-center text-slate-500 bg-white border-slate-200">
                No backup alternative corridors were generated for this leg.
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
                {feasibleCandidates.map(cand => {
                  const isInspected = activeCandidateId === cand.id;
                  return (
                    <div 
                      key={cand.id}
                      className="p-3 rounded-xl border flex flex-col justify-between gap-2 transition shadow-2xs"
                      style={{ 
                        background: isInspected ? '#DBEAFE' : 'var(--surface-white)', 
                        borderColor: isInspected ? '#2563EB' : 'var(--border)' 
                      }}
                    >
                      <div>
                        <div className="flex items-center justify-between gap-1 mb-1">
                          <span className="font-mono text-xs font-bold truncate text-slate-800" title={cand.id}>
                            {cand.id}
                          </span>
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-bold font-mono border bg-blue-50 text-blue-700 border-blue-200">
                            FEASIBLE_ALTERNATIVE
                          </span>
                        </div>

                        <div className="grid grid-cols-3 gap-1 text-[11px] font-mono my-1.5 text-slate-600">
                          <div>
                            <span className="text-[9px] block uppercase text-slate-400">Dist</span>
                            <span className="font-bold">{cand.distance_km} km</span>
                          </div>
                          <div>
                            <span className="text-[9px] block uppercase text-slate-400">ETA</span>
                            <span className="font-bold">{cand.estimated_time_minutes} min</span>
                          </div>
                          <div>
                            <span className="text-[9px] block uppercase text-slate-400">Risk</span>
                            <span className="font-bold">{cand.risk_score}</span>
                          </div>
                        </div>

                        <p className="text-[10px] text-slate-600 leading-tight mt-1">
                          {cand.description}
                        </p>
                      </div>

                      <div className="flex items-center gap-1.5 pt-2 border-t border-slate-200/60 mt-1">
                        <button
                          onClick={() => setActiveCandidateId(activeCandidateId === cand.id ? null : cand.id)}
                          className="flex-1 py-1 px-2 rounded-lg text-[10px] font-semibold border flex items-center justify-center gap-1 bg-white hover:bg-slate-50 transition cursor-pointer text-slate-700 border-slate-300"
                        >
                          <Eye className="w-3 h-3 text-slate-500" />
                          {isInspected ? 'Deselect' : 'Inspect'}
                        </button>

                        {onSelectAlternative && (
                          <button
                            onClick={() => onSelectAlternative(cand)}
                            className="py-1 px-2.5 rounded-lg text-[10px] font-semibold text-white bg-indigo-600 hover:bg-indigo-700 transition cursor-pointer flex items-center gap-1 shadow-2xs"
                          >
                            <Check className="w-3 h-3" />
                            Select
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* SECTION 3: Explicitly Rejected Corridors */}
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-bold uppercase tracking-wider flex items-center gap-1.5 text-rose-800">
                <Ban className="w-3.5 h-3.5 text-rose-600" />
                Explicitly Rejected Corridors ({rejectedCandidates.length})
              </span>
              <span className="text-[10px] text-slate-500">
                Evaluated candidates failing safety or access rules
              </span>
            </div>

            {rejectedCandidates.length === 0 ? (
              <div className="p-3 rounded-xl border text-xs text-center text-slate-600 bg-white border-slate-200">
                No routes were explicitly rejected for this mission.
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
                {rejectedCandidates.map(cand => {
                  const isInspected = activeCandidateId === cand.id;
                  return (
                    <div 
                      key={cand.id}
                      className="p-3 rounded-xl border flex flex-col justify-between gap-2 transition shadow-2xs"
                      style={{ 
                        background: isInspected ? '#FEE2E2' : '#FEF2F2', 
                        borderColor: isInspected ? '#DC2626' : '#FECACA' 
                      }}
                    >
                      <div>
                        <div className="flex items-center justify-between gap-1 mb-1">
                          <span className="font-mono text-xs font-bold truncate text-slate-800" title={cand.id}>
                            {cand.id}
                          </span>
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-bold font-mono border bg-rose-100 text-rose-800 border-rose-300 flex items-center gap-1">
                            <XCircle className="w-3 h-3 text-rose-600" />
                            REJECTED
                          </span>
                        </div>

                        <div className="grid grid-cols-3 gap-1 text-[11px] font-mono my-1.5 text-slate-600">
                          <div>
                            <span className="text-[9px] block uppercase text-slate-400">Dist</span>
                            <span className="font-bold">{cand.distance_km} km</span>
                          </div>
                          <div>
                            <span className="text-[9px] block uppercase text-slate-400">ETA</span>
                            <span className="font-bold">{cand.estimated_time_minutes} min</span>
                          </div>
                          <div>
                            <span className="text-[9px] block uppercase text-slate-400">Score</span>
                            <span className="font-bold">{cand.risk_score}</span>
                          </div>
                        </div>

                        {/* Explicit Rejection Rationale and Verified Rule */}
                        <div className="p-2 rounded-lg bg-rose-100/70 border border-rose-200 text-[11px] text-rose-900 mt-2 flex flex-col gap-1">
                          <div className="font-semibold flex items-center gap-1">
                            <AlertTriangle className="w-3.5 h-3.5 text-rose-600 shrink-0" />
                            <span>Rejection Reason:</span>
                          </div>
                          <p className="leading-snug text-[10.5px]">
                            {cand.rejection_reason}
                          </p>
                          <div className="flex flex-wrap items-center gap-2 pt-1 border-t border-rose-200/60 text-[9.5px] font-mono text-rose-700">
                            <span>Rule: <strong>{cand.rule_violated}</strong></span>
                            <span>•</span>
                            <span>Source: <strong>{cand.evidence_source}</strong></span>
                            {cand.confidence !== undefined && cand.confidence !== null && (
                              <>
                                <span>•</span>
                                <span>Confidence: <strong>{Math.round(cand.confidence * 100)}%</strong></span>
                              </>
                            )}
                          </div>
                        </div>
                      </div>

                      <div className="flex items-center justify-between gap-1.5 pt-2 border-t border-rose-200 mt-1">
                        {cand.hasGeometry ? (
                          <button
                            onClick={() => setActiveCandidateId(activeCandidateId === cand.id ? null : cand.id)}
                            className="flex-1 py-1 px-2 rounded-lg text-[10px] font-semibold border flex items-center justify-center gap-1 bg-white hover:bg-rose-50 transition cursor-pointer text-rose-800 border-rose-300"
                          >
                            <Eye className="w-3 h-3 text-rose-600" />
                            {isInspected ? 'Deselect Highlight' : 'Inspect Geometry'}
                          </button>
                        ) : (
                          <span className="text-[10px] font-mono text-slate-500 italic py-1 px-2">
                            No Geometry Available (Unplottable)
                          </span>
                        )}
                        <span className="text-[10px] font-semibold text-rose-700 px-2 py-0.5 rounded bg-rose-200/60">
                          Excluded from Dispatch
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

        </div>

      </div>
    </div>
  );
}

class MapErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }
  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }
  componentDidCatch(error, errorInfo) {
    console.error('RouteMapComponent error caught by boundary:', error, errorInfo);
  }
  render() {
    if (this.state.hasError) {
      return (
        <div className="p-4 rounded-xl border flex flex-col gap-2" style={{ background: '#FFFBEB', borderColor: '#FDE68A' }}>
          <div className="flex items-center gap-2 text-amber-800 font-bold text-xs uppercase">
            <AlertTriangle className="w-4 h-4 text-amber-600" />
            Route Map Rendering Notice
          </div>
          <p className="text-xs text-amber-900">
            The interactive map preview encountered an issue while plotting geometry. Multi-leg waypoint timeline and tabular route metrics remain fully accessible below.
          </p>
        </div>
      );
    }
    return this.props.children;
  }
}

export function RouteMapWithBoundary(props) {
  return (
    <MapErrorBoundary>
      <RouteMapInner {...props} />
    </MapErrorBoundary>
  );
}

export default RouteMapWithBoundary;
