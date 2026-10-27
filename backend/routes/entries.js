const express = require('express');
const router = express.Router();
const Entry = require('../models/entry.model');
const { protect, getOrCreateFallbackUser } = require('../middleware/auth');

const { validateRelatedness } = require('../config/similarity');

// ML microservice URL — can be overridden via env
const ML_SERVICE_URL = process.env.ML_SERVICE_URL || 'http://localhost:5001';

/**
 * Call the Python ML classifier service.
 * Accepts all text segments as separate strings and joins non-empty ones.
 * Returns the disasterReport object, or null if the service is unreachable.
 */
async function classifyText(...segments) {
    // Deduplicate and join all non-empty text segments
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
            signal: AbortSignal.timeout(5000), // 5s timeout — don't hold up the save
        });

        if (!response.ok) {
            console.warn(`ML service returned ${response.status}`);
            return null;
        }

        return await response.json();
    } catch (err) {
        // Service offline / timed out — log and continue without blocking
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

    // Try computing using python sentence-transformers first
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
        const isValid = avgSim >= 0.40; // Or custom threshold for semantic similarity

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

    // Fallback to existing JS TF-IDF implementation
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
            signal: AbortSignal.timeout(10000), // 10s timeout for image processing
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
async function generateRagPlan(scenarioText, scenarioId, clarificationAnswer) {
    if (!scenarioText || !scenarioText.trim()) return null;
    try {
        const response = await fetch(`${ML_SERVICE_URL}/rag/plan`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                scenario: scenarioText.trim(),
                scenario_id: scenarioId || `SCEN-${Date.now()}`,
                clarification_answer: clarificationAnswer || undefined
            }),
            signal: AbortSignal.timeout(90000), // 90s timeout for retrieval + generation
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

router.post('/', protect, async (req, res) => {
    try {
        const { text, text1, text2, text3, image, audio, audioText, imageCaption: clientCaption, location, clientTimestamp } = req.body;

        // Use client pre-processed image caption or generate image caption via BLIP if image is attached
        const imageCaption = clientCaption || (await generateImageCaption(image));

        // Resolve each named text source independently (no || short-circuiting across sources)
        const primaryText   = (text1 || text || '').trim();   // text input 1 (primary)
        const contextText   = (text2 || '').trim();           // text input 2 (context)
        const detailText    = (text3 || '').trim();           // text input 3 (detail / manual)
        const audioTextVal  = (audioText || '').trim();       // audio transcript (Whisper)
        const imageCaptionVal = (imageCaption || '').trim();  // image description (BLIP)

        // Assemble parts for semantic similarity (include all non-empty sources)
        const parts = {
            ...(primaryText    ? { 'Input 1 (Primary)': primaryText }           : {}),
            ...(contextText    ? { 'Input 2 (Context)': contextText }           : {}),
            ...(detailText     ? { 'Input 3 (Detail)': detailText }             : {}),
            ...(audioTextVal   ? { 'Audio Transcript (Whisper)': audioTextVal } : {}),
            ...(imageCaptionVal? { 'Image Description (BLIP)': imageCaptionVal }: {}),
        };

        // Compute similarity report (semantic transformers with TF-IDF fallback)
        const similarityReport = await getSimilarityReport(parts);

        // Run ML disaster classification — pass every text source as a separate segment
        const disasterReport = await classifyText(
            primaryText,
            contextText,
            detailText,
            audioTextVal,
            imageCaptionVal
        );

        // Build the full combined scenario string for RAG retrieval
        const combinedScenario = [
            primaryText,
            contextText,
            detailText,
            audioTextVal,
            imageCaptionVal
        ]
        .filter(Boolean)
        .filter((v, i, arr) => arr.indexOf(v) === i)  // deduplicate
        .join(' ');

        const activeUser = req.user || (await getOrCreateFallbackUser());

        // Fresh mind for each query: clear any past chat history from backend database
        if (activeUser?._id) {
            await Entry.deleteMany({ user: activeUser._id });
        }

        // Evaluate query completely standalone with a fresh mind (no historical context)
        let ragReport = null;
        if (combinedScenario) {
            ragReport = await generateRagPlan(combinedScenario);
        }

        const entry = new Entry({
            user: activeUser?._id,
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
            clientTimestamp: clientTimestamp || new Date()
        });

        const createdEntry = await entry.save();
        res.status(201).json(createdEntry);
    } catch (error) {
        res.status(500).json({ message: error.message });
    }
});

// POST generate or refresh RAG plan for a specific entry
router.post('/:id/rag', protect, async (req, res) => {
    try {
        const activeUser = req.user || (await getOrCreateFallbackUser());
        const filter = activeUser?._id ? { _id: req.params.id, user: activeUser._id } : { _id: req.params.id };
        const entry = await Entry.findOne(filter);
        if (!entry) return res.status(404).json({ message: 'Entry not found' });

        // Collect every text source independently — no || short-circuiting between sources
        const sources = [
            (entry.text1 || entry.text || '').trim(),  // primary text
            (entry.text2 || '').trim(),                 // context text
            (entry.text3 || '').trim(),                 // detail text
            (entry.audioText || '').trim(),             // audio transcript (Whisper)
            (entry.imageCaption || '').trim()           // image description (BLIP)
        ];

        // Deduplicate and join
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
        await entry.save();
        res.json(entry);
    } catch (error) {
        res.status(500).json({ message: error.message });
    }
});

// POST user clarification answer for an entry (re-evaluates severity and escalates to RAG or routes to low-tier)
router.post('/:id/clarify', protect, async (req, res) => {
    try {
        const { clarification } = req.body;
        if (!clarification || !clarification.trim()) {
            return res.status(400).json({ message: 'Missing clarification text' });
        }

        const activeUser = req.user || (await getOrCreateFallbackUser());
        const filter = activeUser?._id ? { _id: req.params.id, user: activeUser._id } : { _id: req.params.id };
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

        const ragReport = await generateRagPlan(combinedScenario, `ENTRY-${entry._id}`, clarification.trim());
        if (!ragReport) {
            return res.status(502).json({ message: 'Could not re-evaluate plan with clarification at this time' });
        }

        entry.ragReport = ragReport;
        entry.markModified('ragReport');
        await entry.save();
        res.json(entry);
    } catch (error) {
        res.status(500).json({ message: error.message });
    }
});

// GET all entries for the user
router.get('/', protect, async (req, res) => {
    try {
        const activeUser = req.user || (await getOrCreateFallbackUser());
        const filter = activeUser?._id ? { user: activeUser._id } : {};
        const entries = await Entry.find(filter).sort({ createdAt: 1 });
        res.json(entries);
    } catch (error) {
        res.status(500).json({ message: error.message });
    }
});

// DELETE all entries/chats for user — ensure fresh mind
router.delete('/', protect, async (req, res) => {
    try {
        const activeUser = req.user || (await getOrCreateFallbackUser());
        const filter = activeUser?._id ? { user: activeUser._id } : {};
        await Entry.deleteMany(filter);
        res.json({ message: 'All chat history cleared from backend' });
    } catch (error) {
        res.status(500).json({ message: error.message });
    }
});

module.exports = router;
