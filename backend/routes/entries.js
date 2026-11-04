const express = require('express');
const router = express.Router();
const Entry = require('../models/entry.model');
const { protect, requireAdmin } = require('../middleware/auth');
const { validateRelatedness } = require('../config/similarity');

// ML microservice URL — can be overridden via env
const ML_SERVICE_URL = process.env.ML_SERVICE_URL || 'http://localhost:5001';
const RESOURCE_ENGINE_URL = process.env.RESOURCE_ENGINE_URL || 'http://localhost:8000';

/**
 * Call the Python ML classifier service.
 * Accepts all text segments as separate strings and joins non-empty ones.
 * Returns the disasterReport object, or null if the service is unreachable.
 */
async function classifyText(...segments) {
    const seen = new Set();
    const combined = segments
        .filter(t => t && t.trim())
        .filter(t => { if (seen.has(t.trim())) return false; seen.add(t.trim()); return true; })
        .join(' ');

    if (!combined.trim()) return null;

    try {
        const response = await fetch(`${ML_SERVICE_URL}/classify`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: combined }),
            signal: AbortSignal.timeout(5000),
        });

        if (!response.ok) {
            console.warn(`ML service returned ${response.status}`);
            return null;
        }

        return await response.json();
    } catch (err) {
        console.warn('ML classifier service unavailable:', err.message);
        return null;
    }
}

/**
 * Call Python ML service for semantic similarity between pairs of text.
 */
async function computeSemanticSimilarity(text1, text2) {
    try {
        const response = await fetch(`${ML_SERVICE_URL}/similarity`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text1, text2 }),
            signal: AbortSignal.timeout(5000),
        });
        if (response.ok) {
            const data = await response.json();
            if (data && typeof data.similarity === 'number') {
                return data.similarity;
            }
        } else {
            console.warn(`Semantic similarity HTTP error: ${response.status}`);
        }
    } catch (err) {
        console.warn('Semantic similarity service offline or failed:', err.message);
    }
    return null;
}

/**
 * Validate relatedness of multi-input texts. Uses Python SentenceTransformers if available,
 * falling back to local TF-IDF similarity.
 */
async function getSimilarityReport(parts) {
    const activeParts = {};
    for (const key in parts) {
        if (parts[key] && parts[key].trim()) {
            activeParts[key] = parts[key];
        }
    }
    const labels = Object.keys(activeParts);
    if (labels.length <= 1) return null;

    const pairwiseSimilarities = [];
    let sumSim = 0;
    let count = 0;
    let usedTransformer = true;

    for (let i = 0; i < labels.length; i++) {
        for (let j = i + 1; j < labels.length; j++) {
            const textA = activeParts[labels[i]];
            const textB = activeParts[labels[j]];
            let sim = await computeSemanticSimilarity(textA, textB);
            if (sim === null) {
                usedTransformer = false;
                break;
            }
            pairwiseSimilarities.push({
                pair: `${labels[i]} <-> ${labels[j]}`,
                similarity: sim
            });
            sumSim += sim;
            count++;
        }
        if (!usedTransformer) break;
    }

    if (usedTransformer && count > 0) {
        const avgSim = sumSim / count;
        const minSim = Math.min(...pairwiseSimilarities.map(p => p.similarity));
        const isValid = avgSim >= 0.40;

        return {
            num_inputs: labels.length,
            inputs: activeParts,
            check_type: "sentence_transformer_similarity",
            pairwise_similarities: pairwiseSimilarities,
            avg_pairwise_similarity: avgSim,
            min_pairwise_similarity: minSim,
            is_valid: isValid,
            status: isValid ? "RELATED" : "UNRELATED",
            details: isValid
                ? `Average semantic similarity of ${avgSim.toFixed(3)} — inputs are semantically related.`
                : `Average semantic similarity of ${avgSim.toFixed(3)} — inputs appear unrelated.`
        };
    }

    return validateRelatedness(parts);
}

/**
 * Call Python ML service to convert image (base64) to text caption using BLIP model.
 */
async function generateImageCaption(imageBase64) {
    if (!imageBase64) return '';
    try {
        const response = await fetch(`${ML_SERVICE_URL}/caption-image`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ image: imageBase64 }),
            signal: AbortSignal.timeout(10000),
        });
        if (response.ok) {
            const data = await response.json();
            return data.caption || '';
        }
    } catch (err) {
        console.warn('Image captioning service unavailable or failed:', err.message);
    }
    return '';
}

/**
 * Call Python ML service to execute TypeSafe JEV + LLM Disaster RAG Pipeline (Pipeline B).
 */
async function generateRagPlan(scenarioText, scenarioId, clarificationAnswer, coordinates, extraData) {
    if (!scenarioText || !scenarioText.trim()) return null;
    try {
        const body = { 
            scenario: scenarioText.trim(),
            scenario_id: scenarioId || `SCEN-${Date.now()}`,
            clarification_answer: clarificationAnswer || undefined,
            coordinates: coordinates || undefined,
            ...(extraData || {})
        };
        const response = await fetch(`${ML_SERVICE_URL}/rag/plan`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
            signal: AbortSignal.timeout(90000),
        });
        if (response.ok) {
            return await response.json();
        } else {
            console.warn(`RAG plan HTTP error: ${response.status}`);
        }
    } catch (err) {
        console.warn('RAG plan service offline or failed:', err.message);
    }
    return null;
}

/**
 * Call the Resource Engine /orchestrate/from-jev endpoint.
 * Maps RAG pipeline output + entry location into JevOrchestrationRequest.
 * Returns the RE response or null if unavailable / data insufficient.
 */
async function callResourceEngine(ragReport, entryLocation, options = {}) {
    if (!ragReport || !ragReport.success) return null;

    const assessment = ragReport.assessment;
    if (!assessment) return null;

    const sevNum = assessment.severity?.numeric;
    const urgNum = assessment.urgency?.numeric;
    const priLevel = assessment.priority?.level;
    if (sevNum == null || urgNum == null || !priLevel) return null;

    const lat = entryLocation?.lat;
    const lng = entryLocation?.lng;
    if (lat == null || lng == null) return null;

    const structuredFacts = ragReport.structured_facts || {};
    const censusCtx = ragReport.census_context || {};
    const wideArea = ragReport.wide_area || null;

    const intakeRec = ragReport.intake_record || {};
    const confirmedPop = options.affected_population || intakeRec.affected_population || structuredFacts.people_affected || structuredFacts.people_trapped;
    const affectedPopulation = confirmedPop && confirmedPop > 0 ? confirmedPop : Math.max(1, (sevNum ? sevNum * 12 : 25));

    const selectedResources = (ragReport.selected_resources || [])
        .map(item => ({ resource: typeof item === 'string' ? item : item.resource }))
        .filter(item => item.resource);

    const incidentType = options.incident_type ||
        ragReport.incident_type ||
        intakeRec.incident_type ||
        ragReport.plan?.incident_type ||
        ragReport.disaster_assessment?.incident_type ||
        'general_disaster';

    const hazardDetails = options.hazard_details ||
        intakeRec.hazard_details ||
        ragReport.hazard_details ||
        [];

    const body = {
        incident_id: options.incident_id || `JEV-${Date.now()}`,
        location: { latitude: lat, longitude: lng },
        locality: {
            name: censusCtx.district || censusCtx.state || 'Unknown',
            population: affectedPopulation * 10,
            population_density: 1000.0,
            affected_population: affectedPopulation,
        },
        patient_present: (structuredFacts.people_injured_reported || 0) > 0,
        estimated_duration_hours: 24.0,
        hazard_details: hazardDetails,
        jev_triage: {
            incident_type: incidentType,
            assessment: {
                severity: { numeric: sevNum },
                urgency: { numeric: urgNum },
                priority: { level: priLevel },
            },
            selected_resources: selectedResources,
            hazard_details: hazardDetails,
            ...(wideArea?.status ? { wide_area: { status: wideArea.status } } : {}),
        },
    };

    try {
        const response = await fetch(`${RESOURCE_ENGINE_URL}/orchestrate/from-jev`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
            signal: AbortSignal.timeout(30000),
        });

        const data = await response.json();
        return { status: response.status, ...data };
    } catch (err) {
        console.warn('Resource Engine unavailable:', err.message);
        return { status: 0, error: 'RESOURCE_ENGINE_UNAVAILABLE', message: err.message };
    }
}

/**
 * Server-Side Least-Privilege Response Serializer.
 * Enforces role-based visibility:
 * - Regular Users receive ONLY reporter-facing information (situation, person_message, clarifying questions).
 *   All internal operational data (resource allocations, quantities, warehouses, severity scores, telemetry, routes) are completely stripped.
 * - Administrators receive the complete operational report, internal triage, allocation and routing data.
 */
function serializeEntryForUser(entryDoc, user) {
    if (!entryDoc) return null;
    const entry = typeof entryDoc.toObject === 'function' ? entryDoc.toObject() : JSON.parse(JSON.stringify(entryDoc));
    const isAdmin = Boolean(user && user.role === 'admin');

    if (isAdmin) {
        return entry; // Full unredacted operational report for administrators
    }

    // Regular users: extract safe reporter-facing mission update if operational dispatch occurred
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
                resource_name: resId.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()),
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
            hazard_indicators: rer.mission?.risk_indicators || entry.intakeRecord?.hazard_details || [],
            emergency_threshold_minutes: rer.route?.route?.emergency_threshold_minutes || null,
            emergency_threshold_exceeded: Boolean(rer.route?.route?.emergency_threshold_exceeded),
            emergency_threshold_warning: rer.route?.route?.emergency_threshold_warning || null,
            eta_review_escalation: Boolean(rer.route?.route?.eta_review_escalation)
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
    }

    // Strip internal operational reports, resource allocations, and warehouse details
    delete entry.resourceEngineReport;
    if (missionUpdate) {
        entry.missionUpdate = missionUpdate;
    }

    if (entry.disasterReport) {
        // High-level safe detection status only; no internal classifier confidence or numerical scores
        const { disaster_detected, type } = entry.disasterReport;
        entry.disasterReport = { disaster_detected, type };
    }

    if (entry.ragReport) {
        const raw = entry.ragReport;
        const plan = raw.plan || raw;

        // Reporter-facing fields only
        if (entry.intakeRecord) {
            entry.intakeRecord = {
                incident_type: entry.intakeRecord.incident_type,
                affected_population: entry.intakeRecord.affected_population,
                has_valid_coordinates: entry.intakeRecord.has_valid_coordinates,
                missing_required_fields: entry.intakeRecord.missing_required_fields || [],
                clarifying_questions: entry.intakeRecord.clarifying_questions || [],
                clarification_status: entry.intakeRecord.clarification_status,
                is_ready_for_orchestration: Boolean(entry.intakeRecord.is_ready_for_orchestration)
            };
        }

        entry.ragReport = {
            scenario_id: raw.scenario_id,
            pipeline: raw.pipeline || 'jev_v3_rag',
            is_disaster_related: raw.is_disaster_related,
            needs_clarification: Boolean(raw.needs_clarification),
            can_proceed_to_rag: Boolean(raw.can_proceed_to_rag),
            clarifying_questions: raw.clarifying_questions || [],
            missing_info: raw.missing_info || [],
            intake_record: entry.intakeRecord,
            situation: plan.situation || raw.situation || '',
            person_message: plan.person_message || raw.person_message || '',
            success: raw.success !== false,
            status: raw.status || 'PROCESSED'
        };
    }

    return entry;
}

// GET distinct conversation threads for active user
router.get('/conversations', protect, async (req, res) => {
    try {
        const activeUser = req.user;
        if (!activeUser?._id) return res.json([]);

        const threads = await Entry.aggregate([
            { $match: { user: activeUser._id, deletedByUser: { $ne: true } } },
            { $sort: { createdAt: -1 } },
            {
                $group: {
                    _id: "$conversationId",
                    conversationId: { $first: "$conversationId" },
                    conversationTitle: { $first: "$conversationTitle" },
                    lastMessage: { $first: "$text" },
                    lastUpdated: { $first: "$createdAt" },
                    status: { $first: "$status" },
                    count: { $sum: 1 }
                }
            },
            { $sort: { lastUpdated: -1 } }
        ]);

        const formatted = threads.map(t => {
            const cId = t.conversationId || 'default';
            const cTitle = t.conversationTitle || (t.lastMessage ? (t.lastMessage.length > 32 ? t.lastMessage.substring(0, 32) + '...' : t.lastMessage) : 'Emergency Thread');
            return {
                conversationId: cId,
                conversationTitle: cTitle,
                lastMessage: t.lastMessage || '',
                lastUpdated: t.lastUpdated,
                status: t.status || 'MISSION_ACTIVE',
                messageCount: t.count
            };
        });

        res.json(formatted);
    } catch (error) {
        res.status(500).json({ message: error.message });
    }
});

// POST new disaster report
router.post('/', protect, async (req, res) => {
    try {
        const { 
            text, text1, text2, text3, 
            image, audio, audioText, 
            imageCaption: clientCaption, 
            location, clientTimestamp,
            conversationId: clientConvId,
            conversationTitle: clientConvTitle
        } = req.body;

        const imageCaption = clientCaption || (await generateImageCaption(image));

        const primaryText   = (text1 || text || '').trim();
        const contextText   = (text2 || '').trim();
        const detailText    = (text3 || '').trim();
        const audioTextVal  = (audioText || '').trim();
        const imageCaptionVal = (imageCaption || '').trim();

        const parts = {
            ...(primaryText    ? { 'Input 1 (Primary)': primaryText }           : {}),
            ...(contextText    ? { 'Input 2 (Context)': contextText }           : {}),
            ...(detailText     ? { 'Input 3 (Detail)': detailText }             : {}),
            ...(audioTextVal   ? { 'Audio Transcript (Whisper)': audioTextVal } : {}),
            ...(imageCaptionVal? { 'Image Description (BLIP)': imageCaptionVal }: {}),
        };

        const similarityReport = await getSimilarityReport(parts);

        const disasterReport = await classifyText(
            primaryText,
            contextText,
            detailText,
            audioTextVal,
            imageCaptionVal
        );

        const combinedScenario = [
            primaryText,
            contextText,
            detailText,
            audioTextVal,
            imageCaptionVal
        ]
        .filter(Boolean)
        .filter((v, i, arr) => arr.indexOf(v) === i)
        .join(' ');

        const activeUser = req.user;

        // Preserve chat history: conversations are persistent per user thread
        const conversationId = clientConvId || (`conv_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`);
        const snippet = primaryText || audioTextVal || 'Emergency Report';
        const conversationTitle = clientConvTitle || (snippet.length > 35 ? snippet.substring(0, 35) + '...' : snippet);

        let ragReport = null;
        if (combinedScenario) {
            ragReport = await generateRagPlan(combinedScenario, undefined, undefined, location);
        }

        let entryStatus = 'READY_FOR_ASSESSMENT';
        let resourceEngineReport = null;
        let intakeRecord = null;

        if (ragReport) {
            intakeRecord = ragReport.intake_record || ragReport.pre_rag_intake?.intake_record || null;
            if (ragReport.needs_clarification || !ragReport.can_proceed_to_rag) {
                // Stateful clarification workflow: pause orchestration until clarification questions are answered
                entryStatus = 'NEEDS_CLARIFICATION';
            } else {
                entryStatus = 'ORCHESTRATING';
                resourceEngineReport = await callResourceEngine(ragReport, location, {
                    affected_population: intakeRecord?.affected_population,
                    incident_type: intakeRecord?.incident_type,
                    hazard_details: intakeRecord?.hazard_details
                });
                if (resourceEngineReport && (resourceEngineReport.status === 200 || resourceEngineReport.status === 'SUCCESS' || resourceEngineReport.status === 'COMPLETED' || resourceEngineReport.allocation)) {
                    entryStatus = 'MISSION_ACTIVE';
                }
            }
        }

        const isDevTest = Boolean(
            req.body.is_test ||
            req.headers['x-dev-test'] ||
            (conversationTitle && /test/i.test(conversationTitle)) ||
            (primaryText && (/test scenario/i.test(primaryText) || /verification/i.test(primaryText)))
        );

        const entry = new Entry({
            user: activeUser?._id,
            conversationId,
            conversationTitle,
            isDevTest,
            status: entryStatus,
            text: primaryText,
            text1: primaryText,
            text2: contextText,
            text3: detailText,
            image,
            imageCaption: imageCaptionVal,
            audio,
            audioText: audioTextVal,
            location,
            similarityReport,
            disasterReport,
            ragReport,
            resourceEngineReport,
            intakeRecord,
            clientTimestamp: clientTimestamp || new Date()
        });

        const createdEntry = await entry.save();
        res.status(201).json(serializeEntryForUser(createdEntry, req.user));
    } catch (error) {
        res.status(500).json({ message: error.message });
    }
});

// GET entries for current user (least-privilege serialized with thread support)
router.get('/', protect, async (req, res) => {
    try {
        const activeUser = req.user;
        const filter = activeUser?._id ? { user: activeUser._id, deletedByUser: { $ne: true } } : { deletedByUser: { $ne: true } };
        if (req.query.conversationId) {
            if (req.query.conversationId === 'default') {
                filter.$or = [{ conversationId: 'default' }, { conversationId: null }, { conversationId: { $exists: false } }];
            } else {
                filter.conversationId = req.query.conversationId;
            }
        }
        const entries = await Entry.find(filter).sort({ createdAt: 1 });
        res.json(entries.map(e => serializeEntryForUser(e, req.user)));
    } catch (error) {
        res.status(500).json({ message: error.message });
    }
});

// GET all entries with full administrative operational details (Administrator Only)
router.get('/admin', protect, requireAdmin, async (req, res) => {
    try {
        const entries = await Entry.find({}).sort({ createdAt: -1 });
        res.json(entries); // Unredacted for admin
    } catch (error) {
        res.status(500).json({ message: error.message });
    }
});

// GET single entry with full administrative operational details (Administrator Only)
router.get('/:id/admin', protect, requireAdmin, async (req, res) => {
    try {
        const entry = await Entry.findById(req.params.id);
        if (!entry) return res.status(404).json({ message: 'Entry not found' });
        res.json(entry); // Unredacted for admin
    } catch (error) {
        res.status(500).json({ message: error.message });
    }
});

// POST generate or refresh RAG plan for a specific entry
router.post('/:id/rag', protect, async (req, res) => {
    try {
        const activeUser = req.user;
        const filter = activeUser?.role === 'admin' ? { _id: req.params.id } : { _id: req.params.id, user: activeUser._id };
        const entry = await Entry.findOne(filter);
        if (!entry) return res.status(404).json({ message: 'Entry not found' });

        const sources = [
            (entry.text1 || entry.text || '').trim(),
            (entry.text2 || '').trim(),
            (entry.text3 || '').trim(),
            (entry.audioText || '').trim(),
            (entry.imageCaption || '').trim()
        ];

        const combinedScenario = sources
            .filter(Boolean)
            .filter((v, i, arr) => arr.indexOf(v) === i)
            .join(' ');

        if (!combinedScenario.trim()) {
            return res.status(400).json({ message: 'Entry contains no text scenario for RAG analysis' });
        }

        const ragReport = await generateRagPlan(combinedScenario, `ENTRY-${entry._id}`);
        if (!ragReport) {
            return res.status(502).json({ message: 'Could not generate RAG plan at this time' });
        }

        entry.ragReport = ragReport;
        entry.markModified('ragReport');

        if (!ragReport.needs_clarification) {
            entry.status = 'ORCHESTRATING';
            const resourceEngineReport = await callResourceEngine(ragReport, entry.location, {
                affected_population: entry.intakeRecord?.affected_population,
                incident_type: entry.intakeRecord?.incident_type,
                hazard_details: entry.intakeRecord?.hazard_details
            });
            if (resourceEngineReport) {
                entry.resourceEngineReport = resourceEngineReport;
                entry.markModified('resourceEngineReport');
                if (resourceEngineReport.status === 200 || resourceEngineReport.status === 'SUCCESS' || resourceEngineReport.status === 'COMPLETED' || resourceEngineReport.allocation) {
                    entry.status = 'MISSION_ACTIVE';
                }
            }
        } else {
            entry.status = 'NEEDS_CLARIFICATION';
        }

        await entry.save();
        res.json(serializeEntryForUser(entry, req.user));
    } catch (error) {
        res.status(500).json({ message: error.message });
    }
});

// POST user clarification answer for an entry
router.post('/:id/clarify', protect, async (req, res) => {
    try {
        const { clarification, affected_population, incident_type, hazard_details } = req.body;

        let parsedPopulation = null;
        if (affected_population !== undefined && affected_population !== null && affected_population !== '') {
            parsedPopulation = parseInt(affected_population, 10);
            if (isNaN(parsedPopulation) || parsedPopulation <= 0) {
                return res.status(400).json({ message: 'affected_population must be a positive integer greater than zero' });
            }
        }

        const hasClarificationText = clarification && clarification.trim();
        if (!hasClarificationText && parsedPopulation == null && !incident_type) {
            return res.status(400).json({ message: 'Missing clarification or intake data' });
        }

        const activeUser = req.user;
        const filter = activeUser?.role === 'admin' ? { _id: req.params.id } : { _id: req.params.id, user: activeUser._id };
        const entry = await Entry.findOne(filter);
        if (!entry) return res.status(404).json({ message: 'Entry not found' });

        // Idempotency check: avoid duplicate missions if already active
        if (entry.status === 'MISSION_ACTIVE' && entry.resourceEngineReport) {
            return res.json(serializeEntryForUser(entry, req.user));
        }

        const sources = [
            (entry.text1 || entry.text || '').trim(),
            (entry.text2 || '').trim(),
            (entry.text3 || '').trim(),
            (entry.audioText || '').trim(),
            (entry.imageCaption || '').trim()
        ];

        const combinedScenario = sources
            .filter(Boolean)
            .filter((v, i, arr) => arr.indexOf(v) === i)
            .join(' ');

        const clarificationParts = [];
        if (hasClarificationText) clarificationParts.push(clarification.trim());
        if (incident_type) clarificationParts.push(`Hazard type: ${incident_type}`);
        if (parsedPopulation != null) clarificationParts.push(`Affected population: ${parsedPopulation} people`);
        if (Array.isArray(hazard_details) && hazard_details.length > 0) {
            clarificationParts.push(`Hazard details: ${hazard_details.join(', ')}`);
        }
        const effectiveClarification = clarificationParts.join('. ');

        const extraData = {
            affected_population: parsedPopulation,
            incident_type: incident_type,
            hazard_details: hazard_details
        };

        const ragReport = await generateRagPlan(
            combinedScenario,
            `ENTRY-${entry._id}`,
            effectiveClarification,
            entry.location,
            extraData
        );
        if (!ragReport) {
            return res.status(502).json({ message: 'Could not re-evaluate plan with clarification at this time' });
        }

        entry.ragReport = ragReport;
        entry.intakeRecord = ragReport.intake_record || ragReport.pre_rag_intake?.intake_record || entry.intakeRecord || null;
        if (parsedPopulation != null && entry.intakeRecord) {
            entry.intakeRecord.affected_population = parsedPopulation;
        }
        if (incident_type && entry.intakeRecord) {
            entry.intakeRecord.incident_type = incident_type;
        }
        entry.markModified('ragReport');
        entry.markModified('intakeRecord');

        if (!ragReport.needs_clarification && ragReport.can_proceed_to_rag) {
            entry.status = 'ORCHESTRATING';
            const resourceEngineReport = await callResourceEngine(ragReport, entry.location, {
                affected_population: parsedPopulation || entry.intakeRecord?.affected_population,
                incident_type: incident_type || entry.intakeRecord?.incident_type,
                hazard_details: hazard_details || entry.intakeRecord?.hazard_details
            });
            if (resourceEngineReport) {
                entry.resourceEngineReport = resourceEngineReport;
                entry.markModified('resourceEngineReport');
                if (resourceEngineReport.status === 200 || resourceEngineReport.status === 'SUCCESS' || resourceEngineReport.status === 'COMPLETED' || resourceEngineReport.allocation) {
                    entry.status = 'MISSION_ACTIVE';
                }
            }
        } else {
            entry.status = 'NEEDS_CLARIFICATION';
        }

        await entry.save();
        res.json(serializeEntryForUser(entry, req.user));
    } catch (error) {
        res.status(500).json({ message: error.message });
    }
});

// DELETE all entries/chats for user (user-scoped soft-delete preserving operational dispatches)
router.delete('/', protect, async (req, res) => {
    try {
        const activeUser = req.user;
        if (!activeUser?._id) return res.status(401).json({ message: 'Unauthorized' });
        const result = await Entry.updateMany(
            { user: activeUser._id, deletedByUser: { $ne: true } },
            { $set: { deletedByUser: true } }
        );
        res.json({
            status: 'success',
            message: 'All conversations and chat history cleared for user',
            clearedCount: result.modifiedCount
        });
    } catch (error) {
        res.status(500).json({ message: error.message });
    }
});

// DELETE single conversation thread for user
router.delete('/conversation/:conversationId', protect, async (req, res) => {
    try {
        const activeUser = req.user;
        if (!activeUser?._id) return res.status(401).json({ message: 'Unauthorized' });
        const cId = req.params.conversationId;
        const query = { user: activeUser._id, deletedByUser: { $ne: true } };
        if (cId === 'default') {
            query.$or = [{ conversationId: 'default' }, { conversationId: null }, { conversationId: { $exists: false } }];
        } else {
            query.conversationId = cId;
        }
        const result = await Entry.updateMany(
            query,
            { $set: { deletedByUser: true } }
        );
        res.json({
            status: 'success',
            message: `Conversation ${cId} cleared for user`,
            clearedCount: result.modifiedCount
        });
    } catch (error) {
        res.status(500).json({ message: error.message });
    }
});

// POST development-only reset for disposable test data
router.post('/dev-reset', async (req, res) => {
    if (process.env.NODE_ENV === 'production') {
        return res.status(403).json({ message: 'Reset strictly prohibited in production environment' });
    }
    try {
        const filter = {
            $or: [
                { isDevTest: true },
                { conversationTitle: /test/i },
                { 'ragReport.scenario_id': /^TEST-/i },
                { 'ragReport.scenario_id': /^SCEN-/i }
            ]
        };
        const result = await Entry.deleteMany(filter);

        let reMsg = null;
        try {
            const reRes = await fetch(`${RESOURCE_ENGINE_URL}/orchestrate/reset-test-data`, { method: 'POST' });
            if (reRes.ok) {
                const reData = await reRes.json();
                reMsg = reData.message;
            }
        } catch (e) {
            reMsg = `Resource Engine unreachable: ${e.message}`;
        }

        res.json({
            status: 'success',
            deletedTestEntriesCount: result.deletedCount,
            resourceEngine: reMsg,
            message: 'Development test data reset successfully. Exactly 5 default scenarios active.'
        });
    } catch (err) {
        res.status(500).json({ message: err.message });
    }
});

module.exports = router;
