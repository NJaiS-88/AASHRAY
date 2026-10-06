const express = require('express');
const router = express.Router();
const Entry = require('../models/entry.model');
const { protect } = require('../middleware/auth');

const { validateRelatedness } = require('../config/similarity');

// ML microservice URL — can be overridden via env
const ML_SERVICE_URL = process.env.ML_SERVICE_URL || 'http://localhost:5001';

/**
 * Call the Python ML classifier service.
 * Concatenates all non-empty text inputs and sends them as one string.
 * Returns the disasterReport object, or null if the service is unreachable.
 */
async function classifyText(text1, text2, text3) {
    // Concatenate all non-empty parts
    const combined = [text1, text2, text3]
        .filter(t => t && t.trim())
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

router.post('/', protect, async (req, res) => {
    try {
        const { text, text1, text2, text3, image, audio, audioText, imageCaption: clientCaption, location, clientTimestamp } = req.body;
        
        // Use client pre-processed image caption or generate image caption via BLIP if image is attached
        const imageCaption = clientCaption || (await generateImageCaption(image));

        // Assemble parts for semantic similarity (include image caption if available)
        const parts = {
            "Input 1": text1 || text || "",
            "Input 2": text2 || "",
            "Input 3": text3 || audioText || "",
            ...(imageCaption ? { "Image Description (BLIP)": imageCaption } : {})
        };

        // Compute similarity report (semantic transformers with TF-IDF fallback)
        const similarityReport = await getSimilarityReport(parts);

        // Run ML disaster classification on all text inputs + audio + image caption combined
        const disasterReport = await classifyText(
            text1 || text || '',
            text2 || '',
            [text3, audioText, imageCaption].filter((v, i, self) => v && self.indexOf(v) === i).join(' ')
        );

        const entry = new Entry({
            user: req.user._id,
            text: text1 || text || '',
            text1: text1 || text || '',
            text2: text2 || '',
            text3: text3 || audioText || '',
            image,
            imageCaption,
            audio,
            audioText,
            location,
            similarityReport,
            disasterReport,
            clientTimestamp: clientTimestamp || new Date()
        });

        const createdEntry = await entry.save();
        res.status(201).json(createdEntry);
    } catch (error) {
        res.status(500).json({ message: error.message });
    }
});

// GET all entries for the user
router.get('/', protect, async (req, res) => {
    try {
        const entries = await Entry.find({ user: req.user._id }).sort({ createdAt: 1 });
        res.json(entries);
    } catch (error) {
        res.status(500).json({ message: error.message });
    }
});

module.exports = router;
