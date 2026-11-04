with open('backend/routes/entries.js', 'r', encoding='utf-8') as f:
    c = f.read()

# 1. Update timeout in callResourceEngine
t1 = "signal: AbortSignal.timeout(15000)"
r1 = "signal: AbortSignal.timeout(30000)"
assert t1 in c, "t1 not found"
c = c.replace(t1, r1, 1)

# 2. Update serializeEntryForUser
t2 = """    // Regular users: extract safe reporter-facing mission update if operational dispatch occurred
    let missionUpdate = null;
    if (entry.resourceEngineReport) {
        const rer = entry.resourceEngineReport;
        const alloc = rer.allocation?.allocated_resources || {};
        const RESOURCE_UNITS = {
            drinking_water: 'liters',
            water_purification: 'kits',
            sanitation_hygiene_kits: 'kits',
            food_dry_rations: 'packs',
            community_kitchen_cooked_food: 'meals',
            infant_child_nutrition: 'kits',
            fuel_cooking: 'units',
            livestock_fodder_veterinary: 'units',
            emergency_shelter_relief_camp: 'sq-meters',
            shelter_kits_tarpaulin: 'kits',
            clothing_blankets_warmth: 'sets',
            cash_assistance: 'units',
            search_and_rescue: 'teams',
            boat_water_rescue: 'boats',
            evacuation_transport: 'vehicles',
            missing_persons_reunification: 'cases',
            emergency_medical_care: 'kits',
            first_aid_trauma: 'kits',
            maternal_newborn_care: 'kits',
            elderly_disability_assistance: 'kits',
            psychosocial_support: 'sessions',
            medicines_medical_supplies: 'kits',
            chronic_care_medication: 'courses',
            disease_vector_control: 'kits',
            heavy_machinery_debris_clearance: 'units',
            tools_equipment: 'sets',
            power_lighting: 'units',
            communication_early_warning: 'units',
            women_child_protection: 'kits',
            dead_body_management: 'kits'
        };

        const confirmedAllocations = Object.entries(alloc)
            .filter(([_, qty]) => Number(qty) > 0)
            .map(([resId, qty]) => ({
                resource_id: resId,
                resource_name: resId.replace(/_/g, ' ').replace(/\\b\\w/g, c => c.toUpperCase()),
                quantity: Number(qty),
                unit: RESOURCE_UNITS[resId] || 'units'
            }));
        
        let etaMinutes = null;
        if (rer.routes && Array.isArray(rer.routes)) {
            const primary = rer.routes.find(r => r.primaryRoute)?.primaryRoute || rer.routes[0];
            if (primary && primary.durationSeconds) {
                etaMinutes = Math.max(1, Math.round(primary.durationSeconds / 60));
            }
        } else if (rer.route_plan?.primaryRoute?.durationSeconds) {
            etaMinutes = Math.max(1, Math.round(rer.route_plan.primaryRoute.durationSeconds / 60));
        } else if (rer.route?.route?.estimated_time_minutes) {
            etaMinutes = Math.max(1, Math.round(rer.route.route.estimated_time_minutes));
        }

        missionUpdate = {
            mission_id: rer.mission?.mission_id || rer.allocation?.allocation_id || rer.mission_id || `MSN-${String(entry._id).slice(-6).toUpperCase()}`,
            status: rer.status === 200 || rer.status === 'SUCCESS' || rer.status === 'COMPLETED' || rer.allocation ? 'RESOURCES_DISPATCHED' : 'MOBILIZING',
            confirmed_resources: confirmedAllocations,
            eta_minutes: etaMinutes,
            eta_display: etaMinutes ? `${etaMinutes} mins` : 'Calculating route ETA...',
            dispatch_time: rer.timestamp || entry.createdAt,
            affected_population: entry.intakeRecord?.affected_population || rer.mission?.affected_population || null,
            hazard_indicators: rer.mission?.risk_indicators || entry.intakeRecord?.hazard_details || []
        };
    }"""

r2 = """    // Regular users: extract safe reporter-facing mission update if operational dispatch occurred
    let missionUpdate = null;
    const RESOURCE_UNITS = {
        drinking_water: 'liters',
        water_purification: 'kits',
        sanitation_hygiene_kits: 'kits',
        food_dry_rations: 'packs',
        community_kitchen_cooked_food: 'meals',
        infant_child_nutrition: 'kits',
        fuel_cooking: 'units',
        livestock_fodder_veterinary: 'units',
        emergency_shelter_relief_camp: 'sq-meters',
        shelter_kits_tarpaulin: 'kits',
        clothing_blankets_warmth: 'sets',
        cash_assistance: 'units',
        search_and_rescue: 'teams',
        boat_water_rescue: 'boats',
        evacuation_transport: 'vehicles',
        missing_persons_reunification: 'cases',
        emergency_medical_care: 'kits',
        first_aid_trauma: 'kits',
        maternal_newborn_care: 'kits',
        elderly_disability_assistance: 'kits',
        psychosocial_support: 'sessions',
        medicines_medical_supplies: 'kits',
        chronic_care_medication: 'courses',
        disease_vector_control: 'kits',
        heavy_machinery_debris_clearance: 'units',
        tools_equipment: 'sets',
        power_lighting: 'units',
        communication_early_warning: 'units',
        women_child_protection: 'kits',
        dead_body_management: 'kits'
    };

    if (entry.resourceEngineReport) {
        const rer = entry.resourceEngineReport;
        const alloc = (rer.allocation && rer.allocation.allocated_resources)
            || (rer.mission && rer.mission.resources)
            || rer.allocated_resources
            || {};

        const confirmedAllocations = Object.entries(alloc)
            .filter(([_, qty]) => Number(qty) > 0)
            .map(([resId, qty]) => ({
                resource_id: resId,
                resource_name: resId.replace(/_/g, ' ').replace(/\\b\\w/g, c => c.toUpperCase()),
                quantity: Number(qty),
                unit: RESOURCE_UNITS[resId] || 'units'
            }));
        
        let etaMinutes = null;
        if (rer.routes && Array.isArray(rer.routes)) {
            const primary = rer.routes.find(r => r.primaryRoute)?.primaryRoute || rer.routes[0];
            if (primary && primary.durationSeconds) {
                etaMinutes = Math.max(1, Math.round(primary.durationSeconds / 60));
            }
        } else if (rer.route_plan?.primaryRoute?.durationSeconds) {
            etaMinutes = Math.max(1, Math.round(rer.route_plan.primaryRoute.durationSeconds / 60));
        } else if (rer.route?.route?.estimated_time_minutes != null) {
            etaMinutes = Math.max(1, Math.round(rer.route.route.estimated_time_minutes));
        } else if (rer.mission?.route?.estimated_time_minutes != null) {
            etaMinutes = Math.max(1, Math.round(rer.mission.route.estimated_time_minutes));
        }

        const isCompleted = rer.status === 200 || rer.status === 'SUCCESS' || rer.status === 'COMPLETED' || rer.status === 'ROUTE_ENGINE_NOT_CONNECTED';
        const isQueued = rer.status === 409 || rer.status === 'NO_RESPONDER_AVAILABLE' || rer.error?.error_code === 'NO_RESPONDER_AVAILABLE';

        let missionStatus = 'MOBILIZING';
        if (isCompleted && confirmedAllocations.length > 0) {
            missionStatus = 'RESOURCES_DISPATCHED';
        } else if (isQueued) {
            missionStatus = 'QUEUED_FOR_DISPATCH';
        } else if (rer.allocation && confirmedAllocations.length > 0) {
            missionStatus = 'RESOURCES_ALLOCATED';
        }

        let allocationStatus = 'PENDING';
        if (rer.allocation?.allocation_status) {
            allocationStatus = rer.allocation.allocation_status;
        } else if (rer.fulfilment_status) {
            allocationStatus = rer.fulfilment_status;
        } else if (confirmedAllocations.length > 0) {
            allocationStatus = 'ALLOCATED';
        } else if (rer.status === 500 || rer.error) {
            allocationStatus = 'FAILED';
        } else if (rer.allocation && confirmedAllocations.length === 0) {
            allocationStatus = 'NO_STOCK_AVAILABLE';
        }

        let etaDisplay = 'Calculating route ETA...';
        if (etaMinutes != null && etaMinutes > 0) {
            etaDisplay = `${etaMinutes} mins`;
        } else if (isQueued) {
            etaDisplay = 'Awaiting next available responder unit';
        }

        missionUpdate = {
            mission_id: rer.mission?.mission_id || rer.allocation?.allocation_id || rer.orchestration_id || rer.mission_id || `MSN-${String(entry._id).slice(-6).toUpperCase()}`,
            status: missionStatus,
            allocation_status: allocationStatus,
            fulfilment_status: rer.fulfilment_status || rer.allocation?.allocation_status || null,
            confirmed_resources: confirmedAllocations,
            total_allocated_types: confirmedAllocations.length,
            eta_minutes: etaMinutes,
            eta_display: etaDisplay,
            dispatch_time: rer.timestamp || entry.createdAt,
            affected_population: entry.intakeRecord?.affected_population || rer.mission?.affected_population || null,
            hazard_indicators: rer.mission?.risk_indicators || entry.intakeRecord?.hazard_details || []
        };
    } else if (entry.status === 'ORCHESTRATING') {
        missionUpdate = {
            mission_id: `MSN-${String(entry._id).slice(-6).toUpperCase()}`,
            status: 'MOBILIZING',
            allocation_status: 'PENDING',
            fulfilment_status: null,
            confirmed_resources: [],
            total_allocated_types: 0,
            eta_minutes: null,
            eta_display: 'Calculating route ETA...',
            dispatch_time: entry.createdAt,
            affected_population: entry.intakeRecord?.affected_population || null,
            hazard_indicators: entry.intakeRecord?.hazard_details || []
        };
    }"""

assert t2 in c, "t2 not found"
c = c.replace(t2, r2, 1)

with open('backend/routes/entries.js', 'w', encoding='utf-8') as f:
    f.write(c)

print('Successfully updated backend/routes/entries.js')
