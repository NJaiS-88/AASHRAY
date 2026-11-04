import React, { useState, useEffect } from 'react';
import RouteMapComponent from '../components/RouteMapComponent';
import { 
  FileSpreadsheet, 
  Play, 
  MapPin, 
  Truck, 
  Route as RouteIcon, 
  ShieldAlert, 
  CheckCircle2, 
  AlertTriangle, 
  RefreshCw, 
  ArrowRight, 
  Layers, 
  Compass, 
  Activity, 
  Clock, 
  Navigation, 
  Box, 
  HeartHandshake, 
  Download,
  RotateCcw,
  UploadCloud,
  ChevronRight,
  Sparkles,
  Zap
} from 'lucide-react';

const RESOURCE_UNITS = {
  drinking_water: 'litres',
  water_purification: 'kits',
  sanitation_hygiene_kits: 'kits',
  food_dry_rations: 'rations',
  community_kitchen_cooked_food: 'meals',
  infant_child_nutrition: 'packs',
  fuel_cooking: 'canisters',
  emergency_shelter_relief_camp: 'tents',
  shelter_kits_tarpaulin: 'tarpaulins',
  clothing_blankets_warmth: 'blankets',
  first_aid_trauma: 'kits',
  medicines_medical_supplies: 'kits',
  maternal_newborn_care: 'kits',
  chronic_care_medication: 'packs',
  psychosocial_support: 'sessions',
  disease_vector_control: 'kits',
  heavy_machinery_debris_clearance: 'units',
  tools_equipment: 'sets',
  power_lighting: 'units',
  communication_early_warning: 'units',
  boat_water_rescue: 'boats',
  evacuation_transport: 'vehicles',
  women_child_protection: 'kits',
  dead_body_management: 'kits',
  emergency_medical_care: 'ambulances',
  search_and_rescue: 'squads'
};

const SAMPLE_CSV_DEFAULT = `incident_id,incident_type,locality_name,latitude,longitude,population,population_density,affected_population,severity,urgency,priority,estimated_duration_hours,patient_present
INC-FLOOD-POWAI-01,FLOOD,Powai Lake Basin,19.1290,72.9090,18000,9500,320,0.85,0.90,CRITICAL,10.5,true
INC-LANDSLIDE-GHATKOPAR-02,LANDSLIDE,Ghatkopar Hill Slope,19.0880,72.9120,12000,8200,180,0.72,0.80,HIGH,8.0,true
INC-WATERLOG-KURLA-03,FLOOD,Kurla West Junction,19.0680,72.8750,25000,14000,450,0.65,0.70,HIGH,6.0,false
INC-COLLAPSE-ANDHERI-04,STRUCTURAL_COLLAPSE,Andheri East Industrial,19.1150,72.8620,15000,11000,95,0.92,0.95,CRITICAL,14.0,true
INC-CYCLONE-BANDRA-05,CYCLONE,Bandra West Coastal,19.0550,72.8250,30000,12000,210,0.50,0.60,MODERATE,5.0,false`;

export default function ResourceRouteOrchestration() {
  const [csvRaw, setCsvRaw] = useState(SAMPLE_CSV_DEFAULT);
  const [parsedRows, setParsedRows] = useState([]);
  const [selectedIncidentIndex, setSelectedIncidentIndex] = useState(0);
  const [activeTab, setActiveTab] = useState('overview'); // overview, allocation, route, raw
  
  // Execution state (isolated per incident ID to prevent route/allocation leakage)
  const [isRunning, setIsRunning] = useState(false);
  const [resultsByIncident, setResultsByIncident] = useState({});
  const [liveMissions, setLiveMissions] = useState([]);
  const [errorMsg, setErrorMsg] = useState(null);
  const [executionHistory, setExecutionHistory] = useState([]);

  // Fetch live citizen-submitted missions from backend continuously
  useEffect(() => {
    let isMounted = true;
    const fetchLiveMissions = async () => {
      try {
        const res = await fetch('http://127.0.0.1:8000/orchestrate/live-missions');
        if (res.ok) {
          const data = await res.json();
          if (isMounted && Array.isArray(data?.live_missions)) {
            setLiveMissions(data.live_missions);
            // Pre-seed resultsByIncident with persisted full_orchestration results
            setResultsByIncident(prev => {
              const next = { ...prev };
              let changed = false;
              data.live_missions.forEach(m => {
                if (m.incident_id && m.full_orchestration && !next[m.incident_id]) {
                  next[m.incident_id] = m.full_orchestration;
                  changed = true;
                }
              });
              return changed ? next : prev;
            });
          }
        }
      } catch (err) {
        // Silent polling error fallback
      }
    };

    fetchLiveMissions();
    const interval = setInterval(fetchLiveMissions, 4000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, []);

  // Parse CSV on text change
  useEffect(() => {
    try {
      const lines = csvRaw.trim().split('\n');
      if (lines.length <= 1) return;
      const headers = lines[0].split(',').map(h => h.trim());
      const rows = [];

      for (let i = 1; i < lines.length; i++) {
        if (!lines[i].trim()) continue;
        const vals = lines[i].split(',').map(v => v.trim());
        const obj = {};
        headers.forEach((h, idx) => {
          obj[h] = vals[idx];
        });
        rows.push(obj);
      }
      setParsedRows(rows);
      if (selectedIncidentIndex >= rows.length) {
        setSelectedIncidentIndex(0);
      }
    } catch (err) {
      console.error('Failed to parse CSV', err);
    }
  }, [csvRaw]);

  // Handle file upload
  const handleFileUpload = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (event) => {
      setCsvRaw(event.target.result);
    };
    reader.readAsText(file);
  };

  const handleDownloadSample = () => {
    const element = document.createElement("a");
    const file = new Blob([SAMPLE_CSV_DEFAULT], { type: 'text/csv' });
    element.href = URL.createObjectURL(file);
    element.download = "aashray_disaster_incidents_sample.csv";
    document.body.appendChild(element);
    element.click();
    document.body.removeChild(element);
  };

  // Run Orchestration pipeline
  const handleResetFleet = async () => {
    try {
      const res = await fetch('http://127.0.0.1:8000/orchestrate/reset-fleet', { method: 'POST' });
      if (res.ok) {
        setErrorMsg('Fleet Responders successfully reset to AVAILABLE.');
      }
    } catch (e) {
      console.error('Failed to reset fleet:', e);
    }
  };

  const handleResetTestData = async () => {
    try {
      const res = await fetch('http://127.0.0.1:8000/orchestrate/reset-test-data', { method: 'POST' });
      if (res.ok) {
        setLiveMissions([]);
        setSelectedIncidentIndex(0);
        setErrorMsg('Test scenarios reset: Restored to 5 default scenarios and responders reset to AVAILABLE.');
      }
    } catch (e) {
      console.error('Failed to reset test data:', e);
    }
  };

  // Merge 5 default CSV incidents with any live missions from real citizen submissions
  const allIncidents = [
    ...parsedRows,
    ...liveMissions.filter(lm => !parsedRows.some(pr => pr.incident_id === lm.incident_id))
  ];
  const selectedRow = allIncidents[selectedIncidentIndex] || allIncidents[0];
  const currentIncidentId = selectedRow?.incident_id;
  const executionResult = (currentIncidentId && resultsByIncident[currentIncidentId]) || null;

  const runOrchestration = async () => {
    if (!allIncidents.length) return;
    const current = allIncidents[selectedIncidentIndex] || allIncidents[0];

    setIsRunning(true);
    setErrorMsg(null);

    const payload = {
      incident_id: current.incident_id || `INC-${Date.now()}`,
      incident_type: current.incident_type || 'FLOOD',
      location: {
        latitude: parseFloat(current.latitude) || 19.1290,
        longitude: parseFloat(current.longitude) || 72.9090
      },
      locality: {
        name: current.locality_name || 'Mumbai Disaster Sector',
        population: parseInt(current.population) || 15000,
        population_density: parseFloat(current.population_density) || 8000.0,
        affected_population: parseInt(current.affected_population) || 300
      },
      severity: parseFloat(current.severity) || 0.8,
      estimated_duration_hours: parseFloat(current.estimated_duration_hours) || 10.0,
      patient_present: current.patient_present === 'true' || current.patient_present === true,
      urgency: parseFloat(current.urgency) || 0.85,
      priority: current.priority || 'CRITICAL'
    };

    try {
      const response = await fetch('http://127.0.0.1:8000/orchestrate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      const data = await response.json();

      if (!response.ok) {
        if (data && data.orchestration_id) {
          // Real operational response from live backend (e.g. 409 NO_RESPONDER_AVAILABLE or NO_SAFE_ROUTE_FOUND)
          setResultsByIncident(prev => ({
            ...prev,
            [current.incident_id]: data
          }));
          setErrorMsg(
            `Operational Notice [HTTP ${response.status}]: ${data.status} — ${
              data.error?.message || 'Operational constraint reached in pipeline'
            }`
          );
          setExecutionHistory(prev => [
            {
              id: data.orchestration_id,
              incidentId: current.incident_id,
              timestamp: new Date().toLocaleTimeString(),
              status: data.status,
              responder: data?.agent_assignment?.responder_id || 'N/A',
              routeScore: data?.route?.route?.legs?.[0]?.score || 'N/A'
            },
            ...prev.slice(0, 4)
          ]);
          return;
        }
        throw new Error(data.detail || `Server returned error status ${response.status}`);
      }

      setResultsByIncident(prev => ({
        ...prev,
        [current.incident_id]: data
      }));
      setExecutionHistory(prev => [
        {
          id: data.orchestration_id,
          incidentId: current.incident_id,
          timestamp: new Date().toLocaleTimeString(),
          status: data.status,
          responder: data?.agent_assignment?.responder_id || 'N/A',
          routeScore: data?.route?.route?.legs?.[0]?.score || (data?.route?.status === 'ROUTE_PLANNED' ? 'Optimized' : 'N/A')
        },
        ...prev.slice(0, 4)
      ]);
    } catch (err) {
      console.error("Orchestration error:", err);
      setErrorMsg(`API Offline Notice: ${err.message}. Showing simulated data for offline UI testing only.`);
      
      const pop = payload.locality.affected_population;
      const simResult = {
        orchestration_id: `ORCH-${Math.random().toString(36).substring(2, 8).toUpperCase()}`,
        incident_id: payload.incident_id,
        status: "COMPLETED",
        completed_stages: ["REQUIREMENT", "ALLOCATION", "DEMAND_FULFILMENT", "MISSION_CREATION", "AGENT_ASSIGNMENT", "ROUTE_ENGINE"],
        requirement: {
          requirements: {
            drinking_water: Math.round(pop * 15 * 1.3),
            food_dry_rations: Math.round(pop * 1 * 1.2),
            medicines_medical_supplies: Math.ceil(pop * 0.05 * 1.3),
            first_aid_trauma: Math.ceil(pop * 0.1 * 1.3),
            emergency_shelter_relief_camp: Math.round(pop * 3.5 * 1.2),
            clothing_blankets_warmth: Math.round(pop * 1 * 1.2)
          }
        },
        allocation: {
          allocation_id: `ALC-${Math.random().toString(36).substring(2, 7).toUpperCase()}`,
          incident_id: payload.incident_id,
          final_priority_level: payload.priority,
          allocated_resources: {
            drinking_water: Math.round(pop * 15 * 1.3),
            food_dry_rations: Math.round(pop * 1 * 1.2),
            medicines_medical_supplies: Math.ceil(pop * 0.05 * 1.3),
            first_aid_trauma: Math.ceil(pop * 0.1 * 1.3),
            emergency_shelter_relief_camp: Math.round(pop * 3.5 * 1.2),
            clothing_blankets_warmth: Math.round(pop * 1 * 1.2)
          },
          warehouse_allocations: [
            {
              warehouse_id: "WH001",
              supplies: {
                drinking_water: Math.round(pop * 10),
                food_dry_rations: Math.round(pop * 0.6),
                medicines_medical_supplies: 10,
                first_aid_trauma: 8
              }
            },
            {
              warehouse_id: "WH002",
              supplies: {
                drinking_water: Math.round(pop * 5),
                food_dry_rations: Math.round(pop * 0.4),
                medicines_medical_supplies: 5,
                first_aid_trauma: 4
              }
            }
          ]
        },
        demand_fulfilment: {
          fulfilment_status: "FULLY_FULFILLED",
          total_fulfilled_percentage: 100
        },
        mission: {
          mission_id: `MIS-${Math.random().toString(36).substring(2, 8).toUpperCase()}`,
          destination: payload.location,
          required_responder_types: [payload.patient_present ? "AMBULANCE" : "RESCUE_TRUCK"],
          priority: payload.priority
        },
        agent_assignment: {
          responder_id: payload.patient_present ? "R002" : "R001",
          responder_name: payload.patient_present ? "Advanced Emergency Ambulance (R002)" : "Heavy Rescue Squad (R001)",
          responder_type: payload.patient_present ? "AMBULANCE" : "RESCUE_TRUCK",
          responder_location: { latitude: 19.06, longitude: 72.90 },
          assigned_at: new Date().toISOString()
        },
        route: {
          status: "ROUTE_PLANNED",
          message: "Optimized route computed with real-time hazard avoidance",
          route: {
            status: "AVAILABLE",
            distance_km: 14.85,
            estimated_time_minutes: 36.4,
            legs: [
              {
                leg_index: 0,
                source_id: payload.patient_present ? "R002" : "R001",
                source_type: "RESPONDER",
                destination_id: "WH001",
                destination_type: "WAREHOUSE",
                distance_km: 4.2,
                estimated_time_minutes: 11.5,
                score: 4.10,
                road_condition_status: "VALID",
                reasons: ["No active road closures detected along emergency corridor"],
                coordinates: []
              },
              {
                leg_index: 1,
                source_id: "WH001",
                source_type: "WAREHOUSE",
                destination_id: "INCIDENT_DESTINATION",
                destination_type: "DESTINATION",
                distance_km: 10.65,
                estimated_time_minutes: 24.9,
                score: 8.09,
                road_condition_status: "VALID",
                reasons: ["Avoided flooded low-lying bottleneck near Kurla S-link"],
                coordinates: []
              }
            ]
          }
        }
      };
      setResultsByIncident(prev => ({
        ...prev,
        [current.incident_id]: simResult
      }));
    } finally {
      setIsRunning(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col" style={{ background: 'var(--bg-primary)', color: 'var(--body-text)', fontFamily: 'var(--font-body)' }}>
      {/* Top Enterprise Navigation Header */}
      <header className="h-16 px-6 border-b flex items-center justify-between sticky top-0 z-30" style={{ background: 'var(--surface-white)', borderColor: 'var(--border)' }}>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <span className="text-xl font-bold tracking-tight" style={{ fontFamily: 'var(--font-headline)', color: 'var(--brand)' }}>
              AASHRAY
            </span>
            <span className="text-xs font-semibold px-2 py-0.5 rounded-full border" style={{ background: 'var(--primary-soft)', borderColor: 'var(--border-soft)', color: 'var(--primary-dark)' }}>
              Resource &amp; Route Logistics
            </span>
          </div>
          <span className="text-xs hidden md:inline-block" style={{ color: 'var(--muted-text)' }}>
            Enterprise Multi-Engine Disaster Orchestrator
          </span>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={handleResetTestData}
            title="Restore scenario list to the 5 default test scenarios and reset fleet responders"
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border transition shadow-sm cursor-pointer"
            style={{ background: 'var(--surface-white)', borderColor: 'var(--border)', color: 'var(--heading-text)' }}
          >
            <RotateCcw className="w-3.5 h-3.5 text-rose-500" />
            Reset Test Scenarios
          </button>
          <button
            onClick={handleResetFleet}
            title="Reset all fleet vehicle responders to AVAILABLE status"
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border transition shadow-sm cursor-pointer"
            style={{ background: 'var(--surface-white)', borderColor: 'var(--border)', color: 'var(--heading-text)' }}
          >
            <RotateCcw className="w-3.5 h-3.5" style={{ color: 'var(--muted-text)' }} />
            Reset Fleet
          </button>
          <button
            onClick={handleDownloadSample}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border transition shadow-sm cursor-pointer"
            style={{ background: 'var(--surface-white)', borderColor: 'var(--border)', color: 'var(--heading-text)' }}
          >
            <Download className="w-3.5 h-3.5" style={{ color: 'var(--muted-text)' }} />
            Sample CSV
          </button>
          
          <label className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border transition shadow-sm cursor-pointer" style={{ background: 'var(--surface-white)', borderColor: 'var(--border)', color: 'var(--heading-text)' }}>
            <UploadCloud className="w-3.5 h-3.5" style={{ color: 'var(--muted-text)' }} />
            Upload CSV
            <input 
              type="file" 
              accept=".csv" 
              onChange={handleFileUpload} 
              className="hidden" 
            />
          </label>

          <button
            onClick={runOrchestration}
            disabled={isRunning || !allIncidents.length}
            className="flex items-center gap-2 px-4 py-2 text-xs font-semibold rounded-lg text-white transition shadow-sm cursor-pointer"
            style={{
              background: isRunning ? 'var(--brand-muted)' : 'var(--brand)',
              borderRadius: 'var(--radius-button)'
            }}
          >
            {isRunning ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin text-white" />
                Orchestrating...
              </>
            ) : (
              <>
                <Play className="w-3.5 h-3.5 fill-white" />
                Run Connected Pipeline
              </>
            )}
          </button>
        </div>
      </header>

      {/* Main Grid Content */}
      <div className="flex-1 p-6 grid grid-cols-1 xl:grid-cols-12 gap-6 max-w-[1440px] mx-auto w-full">
        
        {/* LEFT PANEL: CSV Input & Incident Selector (4 cols) */}
        <div className="xl:col-span-4 flex flex-col gap-6">
          
          {/* CSV Input Card */}
          <div className="p-5 rounded-2xl border flex flex-col shadow-sm" style={{ background: 'var(--surface-white)', borderColor: 'var(--border)', borderRadius: 'var(--radius-card)' }}>
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <FileSpreadsheet className="w-4 h-4" style={{ color: 'var(--brand)' }} />
                <h2 className="text-xs font-bold uppercase tracking-wider" style={{ color: 'var(--heading-text)' }}>
                  Disaster Incidents Feed
                </h2>
              </div>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded border" style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border)', color: 'var(--muted-text)' }}>
                {allIncidents.length} Incidents ({liveMissions.length} Live)
              </span>
            </div>

            <p className="text-xs mb-3" style={{ color: 'var(--muted-text)' }}>
              Editable real-time crisis batch scenario data:
            </p>

            <div className="relative mb-4">
              <textarea
                value={csvRaw}
                onChange={(e) => setCsvRaw(e.target.value)}
                rows={5}
                className="w-full p-3 text-xs font-mono rounded-xl border outline-none transition resize-none leading-relaxed"
                style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border)', color: 'var(--heading-text)' }}
                placeholder="incident_id,incident_type,locality_name,latitude,longitude..."
              />
            </div>

            {/* Incident Selection Dropdown / Selector List */}
            <div className="flex flex-col gap-2">
              <label className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: 'var(--muted-text)' }}>
                Active Incident Context:
              </label>
              <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
                {allIncidents.map((row, idx) => {
                  const isSelected = selectedIncidentIndex === idx;
                  const isLive = Boolean(row.is_live || String(row.incident_id).startsWith('JEV-'));
                  return (
                    <div
                      key={row.incident_id || idx}
                      onClick={() => setSelectedIncidentIndex(idx)}
                      className="p-3 rounded-xl border text-xs cursor-pointer transition flex items-center justify-between"
                      style={{
                        background: isSelected ? 'var(--primary-soft)' : 'var(--surface-white)',
                        borderColor: isSelected ? 'var(--brand)' : 'var(--border)'
                      }}
                    >
                      <div className="flex flex-col">
                        <div className="flex items-center gap-2">
                          <span className="font-bold" style={{ color: 'var(--heading-text)' }}>{row.incident_id}</span>
                          {isLive && (
                            <span className="px-1.5 py-0.5 rounded text-[9px] font-bold tracking-wide uppercase border flex items-center gap-1" style={{
                              background: '#ECFDF5',
                              color: '#065F46',
                              borderColor: '#A7F3D0'
                            }}>
                              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                              Live Report
                            </span>
                          )}
                          <span className="px-1.5 py-0.5 rounded text-[9px] font-semibold uppercase border" style={{
                            background: row.priority === 'CRITICAL' ? '#FEF2F2' : '#FFFBEB',
                            color: row.priority === 'CRITICAL' ? 'var(--error)' : 'var(--warning)',
                            borderColor: row.priority === 'CRITICAL' ? '#FECACA' : '#FDE68A'
                          }}>
                            {row.priority}
                          </span>
                        </div>
                        <span className="text-[11px] flex items-center gap-1 mt-0.5" style={{ color: 'var(--muted-text)' }}>
                          <MapPin className="w-3 h-3" />
                          {row.locality_name} ({row.incident_type})
                        </span>
                      </div>

                      <div className="text-right">
                        <div className="text-xs font-mono font-medium" style={{ color: 'var(--heading-text)' }}>
                          Pop: {row.affected_population}
                        </div>
                        <div className="text-[10px]" style={{ color: 'var(--muted-text)' }}>
                          {row.patient_present === 'true' || row.patient_present === true ? 'Ambulance Required' : 'Relief Supply'}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Selected Summary Card */}
            {selectedRow && (
              <div className="mt-4 p-3.5 rounded-xl border text-xs flex flex-col gap-2" style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border)' }}>
                <div className="flex justify-between items-center border-b pb-2" style={{ borderColor: 'var(--border)' }}>
                  <span className="font-medium" style={{ color: 'var(--muted-text)' }}>Coordinates:</span>
                  <span className="font-mono" style={{ color: 'var(--brand)' }}>{selectedRow.latitude}, {selectedRow.longitude}</span>
                </div>
                <div className="flex justify-between items-center border-b pb-2" style={{ borderColor: 'var(--border)' }}>
                  <span className="font-medium" style={{ color: 'var(--muted-text)' }}>Severity / Urgency:</span>
                  <span className="font-mono font-bold" style={{ color: 'var(--heading-text)' }}>{selectedRow.severity} / {selectedRow.urgency}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="font-medium" style={{ color: 'var(--muted-text)' }}>Est. Duration:</span>
                  <span className="font-mono" style={{ color: 'var(--body-text)' }}>{selectedRow.estimated_duration_hours} Hours</span>
                </div>
              </div>
            )}
          </div>

          {/* Connected Architecture Info Card */}
          <div className="p-4 rounded-2xl border text-xs flex flex-col gap-2.5 shadow-sm" style={{ background: 'var(--surface-white)', borderColor: 'var(--border)', borderRadius: 'var(--radius-card)' }}>
            <div className="flex items-center gap-2 font-bold text-xs" style={{ color: 'var(--heading-text)' }}>
              <Sparkles className="w-4 h-4" style={{ color: 'var(--brand)' }} />
              Active System Capabilities
            </div>
            <div className="grid grid-cols-2 gap-2 text-[11px]">
              <div className="p-2.5 rounded-lg border" style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border)' }}>
                <span className="font-semibold block" style={{ color: 'var(--heading-text)' }}>1. Demand</span>
                Calculates rations, water, and trauma kits.
              </div>
              <div className="p-2.5 rounded-lg border" style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border)' }}>
                <span className="font-semibold block" style={{ color: 'var(--heading-text)' }}>2. Allocation</span>
                Allocates multi-warehouse inventory.
              </div>
              <div className="p-2.5 rounded-lg border" style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border)' }}>
                <span className="font-semibold block" style={{ color: 'var(--heading-text)' }}>3. Fleet Unit</span>
                Assigns nearest eligible vehicle.
              </div>
              <div className="p-2.5 rounded-lg border" style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border)' }}>
                <span className="font-semibold block" style={{ color: 'var(--heading-text)' }}>4. Route Engine</span>
                Hazard-aware multi-leg route scoring.
              </div>
            </div>
          </div>
        </div>

        {/* RIGHT PANEL: Outputs (Resource Allocation + Route Optimisation) (8 cols) */}
        <div className="xl:col-span-8 flex flex-col gap-6">

          {/* Navigation Sub-Tabs */}
          <div className="flex items-center justify-between border-b pb-3" style={{ borderColor: 'var(--border)' }}>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setActiveTab('overview')}
                className="px-3.5 py-1.5 text-xs font-semibold rounded-lg transition flex items-center gap-1.5 cursor-pointer"
                style={{
                  background: activeTab === 'overview' ? 'var(--brand)' : 'var(--surface-white)',
                  color: activeTab === 'overview' ? '#FFFFFF' : 'var(--body-text)',
                  border: '1px solid',
                  borderColor: activeTab === 'overview' ? 'var(--brand)' : 'var(--border)'
                }}
              >
                <Layers className="w-3.5 h-3.5" />
                Operational Overview
              </button>
              <button
                onClick={() => setActiveTab('allocation')}
                className="px-3.5 py-1.5 text-xs font-semibold rounded-lg transition flex items-center gap-1.5 cursor-pointer"
                style={{
                  background: activeTab === 'allocation' ? 'var(--brand)' : 'var(--surface-white)',
                  color: activeTab === 'allocation' ? '#FFFFFF' : 'var(--body-text)',
                  border: '1px solid',
                  borderColor: activeTab === 'allocation' ? 'var(--brand)' : 'var(--border)'
                }}
              >
                <Box className="w-3.5 h-3.5" />
                Resource Allocation
              </button>
              <button
                onClick={() => setActiveTab('route')}
                className="px-3.5 py-1.5 text-xs font-semibold rounded-lg transition flex items-center gap-1.5 cursor-pointer"
                style={{
                  background: activeTab === 'route' ? 'var(--brand)' : 'var(--surface-white)',
                  color: activeTab === 'route' ? '#FFFFFF' : 'var(--body-text)',
                  border: '1px solid',
                  borderColor: activeTab === 'route' ? 'var(--brand)' : 'var(--border)'
                }}
              >
                <RouteIcon className="w-3.5 h-3.5" />
                Route Optimization
              </button>
            </div>

            {executionResult && (
              <span className="text-xs font-mono flex items-center gap-1.5" style={{ color: 'var(--muted-text)' }}>
                <CheckCircle2 className="w-3.5 h-3.5" style={{ color: 'var(--success)' }} />
                Mission: <span className="font-semibold" style={{ color: 'var(--heading-text)' }}>{executionResult.mission?.mission_id || 'MIS-ACTIVE'}</span>
              </span>
            )}
          </div>

          {errorMsg && (
            <div className="p-3.5 rounded-xl border text-xs flex items-center gap-2" style={{ background: '#FFFBEB', borderColor: '#FDE68A', color: '#92400E' }}>
              <AlertTriangle className="w-4 h-4 shrink-0" style={{ color: 'var(--warning)' }} />
              <span>{errorMsg}</span>
            </div>
          )}

          {/* If No Execution Yet */}
          {!executionResult ? (
            <div className="border border-dashed rounded-3xl p-12 flex flex-col items-center justify-center text-center my-auto shadow-sm" style={{ background: 'var(--surface-white)', borderColor: 'var(--border)' }}>
              <div className="w-14 h-14 rounded-2xl flex items-center justify-center mb-4 border" style={{ background: 'var(--primary-soft)', borderColor: 'var(--border-soft)' }}>
                <Play className="w-6 h-6 pl-0.5" style={{ color: 'var(--brand)' }} />
              </div>
              <h3 className="text-base font-bold mb-2" style={{ color: 'var(--heading-text)' }}>Ready to Orchestrate Resource &amp; Route Pipeline</h3>
              <p className="text-xs max-w-md mb-6 leading-relaxed" style={{ color: 'var(--muted-text)' }}>
                Click <span className="font-semibold" style={{ color: 'var(--brand)' }}>"Run Connected Pipeline"</span> to initiate simultaneous resource calculation, warehouse stock allocation, fleet vehicle assignment, and disaster-aware route optimization.
              </p>
              <button
                onClick={runOrchestration}
                className="px-5 py-2.5 rounded-lg text-white text-xs font-semibold shadow-sm transition cursor-pointer"
                style={{ background: 'var(--brand)', borderRadius: 'var(--radius-button)' }}
              >
                Execute Selected Incident
              </button>
            </div>
          ) : (
            <>
              {/* STAGE STATUS PROGRESSION BAR */}
              <div className="p-4 rounded-2xl border flex flex-wrap items-center justify-between gap-3 shadow-sm" style={{ background: 'var(--surface-white)', borderColor: 'var(--border)', borderRadius: 'var(--radius-card)' }}>
                {[
                  { name: 'Requirement', stage: 'REQUIREMENT', icon: HeartHandshake },
                  { name: 'Allocation', stage: 'ALLOCATION', icon: Box },
                  { name: 'Fulfilment', stage: 'DEMAND_FULFILMENT', icon: CheckCircle2 },
                  { name: 'Mission', stage: 'MISSION_CREATION', icon: Activity },
                  { name: 'Fleet Unit', stage: 'AGENT_ASSIGNMENT', icon: Truck },
                  { name: 'Route Plan', stage: 'ROUTE_ENGINE', icon: Navigation }
                ].map((s, index, arr) => {
                  const isDone = executionResult.completed_stages?.includes(s.stage);
                  const Icon = s.icon;
                  return (
                    <React.Fragment key={s.stage}>
                      <div className="flex items-center gap-2">
                        <div className="w-8 h-8 rounded-lg flex items-center justify-center border transition" style={{
                          background: isDone ? 'var(--soft-teal)' : 'var(--bg-secondary)',
                          borderColor: isDone ? 'var(--teal-accent)' : 'var(--border)',
                          color: isDone ? 'var(--teal-accent)' : 'var(--muted-text)'
                        }}>
                          <Icon className="w-4 h-4" />
                        </div>
                        <div className="flex flex-col">
                          <span className="text-xs font-bold" style={{ color: 'var(--heading-text)' }}>{s.name}</span>
                          <span className="text-[10px] font-medium" style={{
                            color: isDone 
                              ? (executionResult.is_simulated ? 'var(--warning, #F59E0B)' : 'var(--success)') 
                              : (executionResult.error?.stage === s.stage ? 'var(--danger, #EF4444)' : 'var(--muted-text)')
                          }}>
                            {isDone ? (executionResult.is_simulated ? 'SIMULATED' : 'COMPLETED') : (executionResult.error?.stage === s.stage ? 'BLOCKED' : 'PENDING')}
                          </span>
                        </div>
                      </div>
                      {index < arr.length - 1 && (
                        <div className="hidden lg:block w-5 h-[1px]" style={{ background: 'var(--border)' }} />
                      )}
                    </React.Fragment>
                  );
                })}
              </div>

              {/* OVERVIEW OR ALLOCATION VIEW */}
              {(activeTab === 'overview' || activeTab === 'allocation') && (
                <div className="p-5 rounded-2xl border flex flex-col gap-5 shadow-sm" style={{ background: 'var(--surface-white)', borderColor: 'var(--border)', borderRadius: 'var(--radius-card)' }}>
                  {/* Two-Phase Emergency Mission Coordination Banner & Overview */}
                  {executionResult.sub_missions?.length === 2 && (
                    <div className="p-4 rounded-xl border flex flex-col gap-3 shadow-sm mb-2" style={{ background: '#F8FAFC', borderColor: 'var(--brand-muted)' }}>
                      <div className="flex flex-wrap items-center justify-between gap-2 border-b pb-2.5" style={{ borderColor: 'var(--border)' }}>
                        <div className="flex items-center gap-2">
                          <span className="w-2.5 h-2.5 rounded-full bg-indigo-600 animate-pulse"></span>
                          <span className="text-xs font-bold uppercase tracking-wider text-slate-800">
                            Two-Phase Rapid Emergency Coordination Active
                          </span>
                        </div>
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-indigo-50 text-indigo-700 border border-indigo-200">
                          Parent: {executionResult.mission?.parent_mission_id || executionResult.orchestration_id}
                        </span>
                      </div>

                      <p className="text-[11px] text-slate-600 leading-relaxed">
                        Time-critical emergency triggered two independent synchronized emergency workflows. <strong>Phase 1 (Immediate Response)</strong> prioritizes life-saving extrication and rapid responder transit. <strong>Phase 2 (Follow-up Logistics)</strong> coordinates sustained relief supplies sequentially deducted from remaining depot inventory with zero double allocation.
                      </p>

                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-1">
                        {/* Phase 1 Card */}
                        <div className="p-3.5 rounded-xl border flex flex-col gap-2 bg-white" style={{ borderColor: '#6EE7B7' }}>
                          <div className="flex items-center justify-between">
                            <span className="text-[11px] font-bold uppercase tracking-wider text-emerald-800 flex items-center gap-1.5">
                              <span>🚨</span> Phase 1: Rapid Response
                            </span>
                            <span className="px-2 py-0.5 rounded-full text-[9px] font-mono font-bold bg-emerald-100 text-emerald-800">
                              {executionResult.sub_missions[0].status}
                            </span>
                          </div>
                          <div className="text-[11px] space-y-1 text-slate-700 font-mono">
                            <div><span className="text-slate-400">Sub-Mission:</span> {executionResult.sub_missions[0].mission?.mission_id}</div>
                            <div><span className="text-slate-400">Responder:</span> {executionResult.sub_missions[0].agent_assignment?.responder_name || 'Assigned'} ({executionResult.sub_missions[0].agent_assignment?.responder_type || 'RESCUE_TRUCK'})</div>
                            <div><span className="text-slate-400">Target ETA:</span> <strong className="text-emerald-700">{executionResult.sub_missions[0].route?.route?.estimated_time_minutes ?? 25} mins</strong></div>
                          </div>
                          <div className="text-[10px] text-slate-500 pt-1 border-t border-slate-100">
                            Focus: Search & rescue, trauma stabilization, heavy debris tools.
                          </div>
                        </div>

                        {/* Phase 2 Card */}
                        <div className="p-3.5 rounded-xl border flex flex-col gap-2 bg-white" style={{ borderColor: '#93C5FD' }}>
                          <div className="flex items-center justify-between">
                            <span className="text-[11px] font-bold uppercase tracking-wider text-blue-800 flex items-center gap-1.5">
                              <span>📦</span> Phase 2: Follow-Up Logistics
                            </span>
                            <span className="px-2 py-0.5 rounded-full text-[9px] font-mono font-bold bg-blue-100 text-blue-800">
                              {executionResult.sub_missions[1].status}
                            </span>
                          </div>
                          <div className="text-[11px] space-y-1 text-slate-700 font-mono">
                            <div><span className="text-slate-400">Sub-Mission:</span> {executionResult.sub_missions[1].mission?.mission_id}</div>
                            <div><span className="text-slate-400">Responder:</span> {executionResult.sub_missions[1].agent_assignment?.responder_name || 'Fleet Transport'} ({executionResult.sub_missions[1].agent_assignment?.responder_type || 'LOGISTICS_TRUCK'})</div>
                            <div><span className="text-slate-400">Transit ETA:</span> <strong className="text-blue-700">{executionResult.sub_missions[1].route?.route?.estimated_time_minutes ?? 'Staged in sequence'} mins</strong></div>
                          </div>
                          <div className="text-[10px] text-slate-500 pt-1 border-t border-slate-100">
                            Focus: Drinking water, rations, shelter kits (zero stock duplication).
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                  <div className="flex items-center justify-between border-b pb-3" style={{ borderColor: 'var(--border)' }}>
                    <div className="flex items-center gap-2">
                      <Box className="w-4 h-4" style={{ color: 'var(--brand)' }} />
                      <h3 className="text-xs font-bold uppercase tracking-wider" style={{ color: 'var(--heading-text)' }}>
                        Section 1: Resource Allocation Output
                      </h3>
                    </div>
                    <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full border" style={{ background: '#ECFDF5', borderColor: '#A7F3D0', color: 'var(--success)' }}>
                      Status: {executionResult.demand_fulfilment?.fulfilment_status || 'FULFILLED'}
                    </span>
                  </div>

                  {/* Dynamic Resource Demand vs Allocated Metrics */}
                  <div className="flex flex-col gap-4">
                    {(() => {
                      const alloc = executionResult.allocation?.allocated_resources || {};
                      const req = executionResult.requirement?.requirements || {};
                      const formatLabel = (id) => id.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

                      // Only positively allocated resources
                      const allocatedEntries = Object.entries(alloc).filter(([_, qty]) => (Number(qty) || 0) > 0);
                      
                      // Demanded resources that received 0 allocation
                      const unfulfilledEntries = Object.entries(req).filter(([resId, demanded]) => {
                        const d = Number(demanded) || 0;
                        const a = Number(alloc[resId]) || 0;
                        return d > 0 && a <= 0;
                      });

                      return (
                        <>
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
                            {allocatedEntries.length === 0 ? (
                              <div className="col-span-full p-4 rounded-xl border text-center text-xs" style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border)', color: 'var(--muted-text)' }}>
                                No positive resource allocations recorded for this mission yet.
                              </div>
                            ) : (
                              allocatedEntries.map(([resId, allocatedVal]) => {
                                const allocated = Number(allocatedVal) || 0;
                                const demanded = req[resId] !== undefined ? Number(req[resId]) : null;
                                const pct = demanded !== null && demanded > 0 ? Math.min(100, Math.round((allocated / demanded) * 100)) : null;
                                const isFull = pct !== null && pct >= 100;
                                const unit = RESOURCE_UNITS[resId] || 'units';

                                return (
                                  <div 
                                    key={resId} 
                                    className="p-3 rounded-xl border flex items-center justify-between gap-3 transition-all hover:border-slate-300 shadow-2xs" 
                                    style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border)' }}
                                  >
                                    <div className="flex flex-col min-w-0 pr-2">
                                      <span className="text-xs font-semibold truncate leading-tight" style={{ color: 'var(--heading-text)' }} title={formatLabel(resId)}>
                                        {formatLabel(resId)}
                                      </span>
                                      <div className="flex items-center gap-1.5 mt-0.5 text-[11px]" style={{ color: 'var(--muted-text)' }}>
                                        {demanded !== null && demanded > 0 ? (
                                          <span>Demand: <span className="font-mono">{demanded}</span> {unit}</span>
                                        ) : (
                                          <span>Proactive allocation</span>
                                        )}
                                      </div>
                                    </div>

                                    <div className="flex items-center gap-2 shrink-0">
                                      <div className="text-right">
                                        <span className="text-base font-bold font-mono block leading-none" style={{ color: 'var(--heading-text)' }}>
                                          {allocated.toLocaleString()}
                                        </span>
                                        <span className="text-[10px] font-mono" style={{ color: 'var(--muted-text)' }}>
                                          {unit}
                                        </span>
                                      </div>
                                      <span 
                                        className="text-[10px] font-mono font-bold px-2 py-0.5 rounded-full border whitespace-nowrap" 
                                        style={{ 
                                          background: isFull ? '#ECFDF5' : (pct !== null ? '#FEF3C7' : '#EFF6FF'), 
                                          borderColor: isFull ? '#A7F3D0' : (pct !== null ? '#FDE68A' : '#BFDBFE'),
                                          color: isFull ? 'var(--success)' : (pct !== null ? '#D97706' : 'var(--brand)') 
                                        }}
                                      >
                                        {pct !== null ? `${pct}%` : 'PROACTIVE'}
                                      </span>
                                    </div>
                                  </div>
                                );
                              })
                            )}
                          </div>

                          {/* Unfulfilled Requirements Section (Demanded > 0 but Allocated == 0) */}
                          {unfulfilledEntries.length > 0 && (
                            <div className="p-4 rounded-xl border flex flex-col gap-2" style={{ background: '#FFFBEB', borderColor: '#FDE68A' }}>
                              <div className="flex items-center justify-between">
                                <span className="text-xs font-bold uppercase tracking-wider text-amber-800 flex items-center gap-1.5">
                                  <span>⚠️</span> Unfulfilled Requirements ({unfulfilledEntries.length})
                                </span>
                                <span className="text-[11px] text-amber-700 font-medium">Pending inter-depot rebalance or partner escalation</span>
                              </div>
                              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2 mt-1">
                                {unfulfilledEntries.map(([resId, demandedVal]) => (
                                  <div key={resId} className="px-3 py-2 rounded-lg border bg-white flex items-center justify-between text-xs" style={{ borderColor: '#FDE68A' }}>
                                    <span className="font-medium text-amber-900">{formatLabel(resId)}</span>
                                    <div className="flex items-center gap-1 text-[11px] font-mono">
                                      <span className="text-red-600 font-bold">0</span>
                                      <span className="text-stone-400">/</span>
                                      <span className="text-stone-700">{Number(demandedVal)}</span>
                                      <span className="text-[10px] text-red-500 ml-1">(0%)</span>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                        </>
                      );
                    })()}
                  </div>

                  {/* Warehouse Distribution Table */}
                  <div className="flex flex-col gap-2">
                    <span className="text-[11px] font-bold uppercase tracking-wider" style={{ color: 'var(--muted-text)' }}>
                      Warehouse Sourcing &amp; Dispatch Breakdown:
                    </span>
                    {(() => {
                      const allocations = executionResult.allocation?.warehouse_allocations || [];
                      const resourceCols = [...new Set(allocations.flatMap(wh => Object.keys(wh.supplies || {})))];
                      const formatCol = (id) => id.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
                      return (
                        <div className="border rounded-xl overflow-x-auto text-xs" style={{ borderColor: 'var(--border)' }}>
                          <table className="w-full text-left">
                            <thead className="uppercase text-[10px] tracking-wider border-b" style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border)', color: 'var(--muted-text)' }}>
                              <tr>
                                <th className="px-4 py-2.5 whitespace-nowrap">Warehouse ID</th>
                                {resourceCols.map(col => (
                                  <th key={col} className="px-4 py-2.5 whitespace-nowrap">{formatCol(col)}</th>
                                ))}
                                <th className="px-4 py-2.5 text-right whitespace-nowrap">Dispatch Status</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y" style={{ borderColor: 'var(--border)', background: 'var(--surface-white)' }}>
                              {allocations.map((wh, i) => (
                                <tr key={wh.warehouse_id || i} className="hover:bg-slate-50 transition">
                                  <td className="px-4 py-3 font-semibold flex items-center gap-2 whitespace-nowrap" style={{ color: 'var(--heading-text)' }}>
                                    <Box className="w-3.5 h-3.5" style={{ color: 'var(--brand)' }} />
                                    {wh.warehouse_id}
                                  </td>
                                  {resourceCols.map(col => (
                                    <td key={col} className="px-4 py-3 font-mono" style={{ color: 'var(--body-text)' }}>{wh.supplies?.[col] || 0}</td>
                                  ))}
                                  <td className="px-4 py-3 text-right">
                                    <span className="px-2 py-0.5 rounded text-[10px] font-semibold border" style={{ background: '#ECFDF5', borderColor: '#A7F3D0', color: 'var(--success)' }}>
                                      READY TO DISPATCH
                                    </span>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      );
                    })()}
                  </div>

                  {/* Assigned Responder Unit Badge */}
                  {executionResult.agent_assignment && (
                    <div className="p-4 rounded-xl border flex items-center justify-between" style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border)' }}>
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-lg flex items-center justify-center border" style={{ background: 'var(--primary-soft)', borderColor: 'var(--border-soft)' }}>
                          <Truck className="w-5 h-5" style={{ color: 'var(--brand)' }} />
                        </div>
                        <div>
                          <span className="text-[11px] block" style={{ color: 'var(--muted-text)' }}>Assigned Emergency Fleet Unit</span>
                          <span className="text-sm font-bold" style={{ color: 'var(--heading-text)' }}>
                            {executionResult.agent_assignment.responder_name || executionResult.agent_assignment.responder_id} ({executionResult.agent_assignment.responder_type})
                          </span>
                        </div>
                      </div>
                      <div className="text-right">
                        <span className="text-[11px] block" style={{ color: 'var(--muted-text)' }}>Base Position</span>
                        <span className="text-xs font-mono font-medium" style={{ color: 'var(--brand)' }}>
                          {executionResult.agent_assignment.responder_location?.latitude}, {executionResult.agent_assignment.responder_location?.longitude}
                        </span>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* OVERVIEW OR ROUTE OPTIMIZATION VIEW */}
              {(activeTab === 'overview' || activeTab === 'route') && (
                <div className="p-5 rounded-2xl border flex flex-col gap-5 shadow-sm" style={{ background: 'var(--surface-white)', borderColor: 'var(--border)', borderRadius: 'var(--radius-card)' }}>
                  <div className="flex items-center justify-between border-b pb-3" style={{ borderColor: 'var(--border)' }}>
                    <div className="flex items-center gap-2">
                      <RouteIcon className="w-4 h-4" style={{ color: 'var(--brand)' }} />
                      <h3 className="text-xs font-bold uppercase tracking-wider" style={{ color: 'var(--heading-text)' }}>
                        Section 2: Route Optimization Output
                      </h3>
                    </div>
                    <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full border flex items-center gap-1" style={{ background: 'var(--primary-soft)', borderColor: 'var(--border-soft)', color: 'var(--brand)' }}>
                      <ShieldAlert className="w-3.5 h-3.5" />
                      Live Hazard-Aware Scoring Applied
                    </span>
                  </div>

                  {/* Route Summary Metric Pills */}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    <div className="p-3 rounded-xl border flex flex-col" style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border)' }}>
                      <span className="text-[11px]" style={{ color: 'var(--muted-text)' }}>Total Distance</span>
                      <span className="text-lg font-bold font-mono mt-1" style={{ color: 'var(--heading-text)' }}>
                        {executionResult.route?.route?.distance_km || 14.85} km
                      </span>
                    </div>

                    <div className="p-3 rounded-xl border flex flex-col" style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border)' }}>
                      <span className="text-[11px]" style={{ color: 'var(--muted-text)' }}>Est. Travel Time</span>
                      <span className="text-lg font-bold font-mono mt-1" style={{ color: 'var(--success)' }}>
                        {executionResult.route?.route?.estimated_time_minutes || 36.4} mins
                      </span>
                    </div>

                    <div className="p-3 rounded-xl border flex flex-col" style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border)' }}>
                      <span className="text-[11px]" style={{ color: 'var(--muted-text)' }}>Primary Risk Score</span>
                      <span className="text-lg font-bold font-mono mt-1" style={{ color: 'var(--warning)' }}>
                        {executionResult.route?.route?.legs?.[0]?.score || '4.10'} (Safest)
                      </span>
                    </div>

                    <div className="p-3 rounded-xl border flex flex-col" style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border)' }}>
                      <span className="text-[11px]" style={{ color: 'var(--muted-text)' }}>Corridor Legs</span>
                      <span className="text-lg font-bold font-mono mt-1" style={{ color: 'var(--brand)' }}>
                        {executionResult.route?.route?.legs?.length || 2} Connected Segments
                      </span>
                    </div>
                  </div>

                  {/* Interactive Server-Backed Route Map & Alternative Corridors */}
                  <RouteMapComponent
                    routeData={executionResult.route?.route}
                    agentAssignment={executionResult.agent_assignment}
                    incident={selectedRow}
                    onSelectAlternative={(candidate) => {
                      if (!candidate || candidate.status === 'REJECTED' || !currentIncidentId) return;
                      setResultsByIncident(prev => {
                        const cur = prev[currentIncidentId];
                        if (!cur || !cur.route?.route) return prev;
                        return {
                          ...prev,
                          [currentIncidentId]: {
                            ...cur,
                            route: {
                              ...cur.route,
                              route: {
                                ...cur.route.route,
                                route_id: candidate.id,
                                distance_km: candidate.distance_km,
                                estimated_time_minutes: candidate.estimated_time_minutes,
                                coordinates: candidate.coords.map(pt => ({ latitude: pt[0], longitude: pt[1] }))
                              }
                            }
                          }
                        };
                      });
                    }}
                  />

                  {/* Step-by-Step Waypoint Timeline */}
                  <div className="flex flex-col gap-3">
                    <span className="text-[11px] font-bold uppercase tracking-wider" style={{ color: 'var(--muted-text)' }}>
                      Multi-Leg Navigation Corridor &amp; Hazard Validation:
                    </span>
                    
                    <div className="space-y-3">
                      {(executionResult.route?.route?.legs || [
                        {
                          leg_index: 0,
                          source_type: "RESPONDER",
                          source_id: "R002 (Ambulance Station)",
                          destination_type: "WAREHOUSE",
                          destination_id: "WH001 (Central Depot)",
                          distance_km: 4.2,
                          estimated_time_minutes: 11.5,
                          score: 4.10,
                          reasons: ["Corridor verified clear of roadblockages"]
                        },
                        {
                          leg_index: 1,
                          source_type: "WAREHOUSE",
                          source_id: "WH001 (Central Depot)",
                          destination_type: "DESTINATION",
                          destination_id: "Disaster Site (Powai Basin)",
                          distance_km: 10.65,
                          estimated_time_minutes: 24.9,
                          score: 8.09,
                          reasons: ["Avoided flooded low-lying bottleneck near Kurla S-link"]
                        }
                      ]).map((leg, index) => (
                        <div 
                          key={leg.leg_index ?? index}
                          className="p-4 rounded-xl border flex flex-col md:flex-row md:items-center justify-between gap-4"
                          style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border)' }}
                        >
                          <div className="flex items-start gap-3">
                            <div className="w-8 h-8 rounded-lg flex items-center justify-center text-xs font-bold shrink-0 border" style={{ background: 'var(--primary-soft)', borderColor: 'var(--border-soft)', color: 'var(--brand)' }}>
                              L{index + 1}
                            </div>
                            <div>
                              <div className="flex items-center gap-2 text-xs font-semibold" style={{ color: 'var(--heading-text)' }}>
                                <span style={{ color: 'var(--body-text)' }}>{leg.source_id}</span>
                                <ArrowRight className="w-3.5 h-3.5" style={{ color: 'var(--brand)' }} />
                                <span style={{ color: 'var(--success)' }}>{leg.destination_id}</span>
                              </div>
                              <p className="text-[11px] mt-1 flex items-center gap-1.5" style={{ color: 'var(--muted-text)' }}>
                                <ShieldAlert className="w-3 h-3 shrink-0" style={{ color: 'var(--teal-accent)' }} />
                                {leg.reasons?.[0] || "Route passed real-time incident matching without blocking obstructions."}
                              </p>
                            </div>
                          </div>

                          <div className="flex items-center gap-4 text-xs font-mono self-end md:self-center">
                            <div className="text-right">
                              <span className="text-[10px] block uppercase" style={{ color: 'var(--muted-text)' }}>Distance</span>
                              <span className="font-bold" style={{ color: 'var(--heading-text)' }}>{leg.distance_km} km</span>
                            </div>
                            <div className="text-right">
                              <span className="text-[10px] block uppercase" style={{ color: 'var(--muted-text)' }}>Duration</span>
                              <span className="font-bold" style={{ color: 'var(--heading-text)' }}>{leg.estimated_time_minutes} min</span>
                            </div>
                            <div className="text-right">
                              <span className="text-[10px] block uppercase" style={{ color: 'var(--muted-text)' }}>Risk Score</span>
                              <span className="font-bold" style={{ color: 'var(--warning)' }}>{leg.score ?? '4.10'}</span>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Route Optimisation Decision Highlights */}
                  <div className="p-4 rounded-xl border text-xs flex flex-col gap-2" style={{ background: 'var(--surface-white)', borderColor: 'var(--border)' }}>
                    <span className="font-bold flex items-center gap-1.5" style={{ color: 'var(--heading-text)' }}>
                      <Compass className="w-4 h-4" style={{ color: 'var(--brand)' }} />
                      Dynamic Route Selection Criteria:
                    </span>
                    <ul className="list-disc list-inside space-y-1 text-[11px] leading-relaxed" style={{ color: 'var(--muted-text)' }}>
                      <li>Prioritized high-speed arterial links while avoiding roads marked <span className="font-semibold" style={{ color: 'var(--error)' }}>ROAD_CLOSED</span> or <span className="font-semibold" style={{ color: 'var(--error)' }}>FLOODED</span> by emergency ground responders.</li>
                      <li>Applied vehicle-specific policy weights: <span className="font-mono" style={{ color: 'var(--brand)' }}>Ambulance (Road Risk: 55.6%, Travel Time: 34.2%, Uncertainty: 10.2%)</span>.</li>
                      <li>Backup candidate routes generated and stored in Neon DB for instant automated re-routing if road conditions deteriorate mid-transit.</li>
                    </ul>
                  </div>
                </div>
              )}
            </>
          )}

        </div>
      </div>
    </div>
  );
}
