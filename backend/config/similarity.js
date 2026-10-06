/**
 * Semantic Similarity utility.
 * Checks whether 2 or 3 text inputs are similar/related to each other.
 * Returns null if fewer than 2 inputs are provided (no check needed).
 */

// Common English stop words to filter noise
const STOP_WORDS = new Set([
  "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are", "as", "at",
  "be", "because", "been", "before", "being", "below", "between", "both", "but", "by",
  "cannot", "could", "did", "do", "does", "doing", "down", "during", "each",
  "few", "for", "from", "further", "had", "has", "have", "having", "he", "her", "here",
  "hers", "herself", "him", "himself", "his", "how", "i", "if", "in", "into", "is", "it",
  "its", "itself", "me", "more", "most", "my", "myself", "no", "nor", "not", "of", "off",
  "on", "once", "only", "or", "other", "our", "ours", "ourselves", "out", "over", "own",
  "same", "she", "should", "so", "some", "such", "than", "that", "the", "their", "theirs",
  "them", "themselves", "then", "there", "these", "they", "this", "those", "through", "to",
  "too", "under", "until", "up", "very", "was", "we", "were", "what", "when", "where",
  "which", "while", "who", "whom", "why", "with", "would", "you", "your", "yours",
  "yourself", "yourselves"
]);

// Tokenize text: lowercase, strip punctuation, remove stop words
function getTokens(text) {
  if (!text) return [];
  return text
    .toLowerCase()
    .replace(/[^\w\s]/g, "")
    .split(/\s+/)
    .filter(word => word && !STOP_WORDS.has(word));
}

// Compute term frequency map
function getTermFreq(tokens) {
  const map = {};
  tokens.forEach(t => {
    map[t] = (map[t] || 0) + 1;
  });
  return map;
}

// Cosine similarity between two term frequency maps
function cosineSimilarity(freq1, freq2) {
  const allTerms = new Set([...Object.keys(freq1), ...Object.keys(freq2)]);
  let dot = 0, mag1 = 0, mag2 = 0;
  for (const term of allTerms) {
    const v1 = freq1[term] || 0;
    const v2 = freq2[term] || 0;
    dot += v1 * v2;
    mag1 += v1 * v1;
    mag2 += v2 * v2;
  }
  if (mag1 === 0 || mag2 === 0) return 0.0;
  return dot / (Math.sqrt(mag1) * Math.sqrt(mag2));
}

/**
 * Check if 2 or 3 text inputs are related to each other.
 * Returns null if only 1 (or 0) inputs are given — no check needed.
 */
function validateRelatedness(parts) {
  // Filter to non-empty inputs only
  const activeParts = {};
  for (const key in parts) {
    if (parts[key] && parts[key].trim()) {
      activeParts[key] = parts[key];
    }
  }

  const nParts = Object.keys(activeParts).length;

  // 0 or 1 input — no similarity to compute
  if (nParts <= 1) return null;

  // 2+ inputs — compute pairwise cosine similarity
  const labels = Object.keys(activeParts);
  const termFreqs = labels.map(label => getTermFreq(getTokens(activeParts[label])));

  const pairwiseSimilarities = [];
  let sumSimilarity = 0;
  let count = 0;

  for (let i = 0; i < labels.length; i++) {
    for (let j = i + 1; j < labels.length; j++) {
      const sim = cosineSimilarity(termFreqs[i], termFreqs[j]);
      pairwiseSimilarities.push({
        pair: `${labels[i]} <-> ${labels[j]}`,
        similarity: sim
      });
      sumSimilarity += sim;
      count++;
    }
  }

  const avgSimilarity = count > 0 ? sumSimilarity / count : 0.0;
  const minSimilarity = Math.min(...pairwiseSimilarities.map(p => p.similarity));
  const isValid = avgSimilarity >= 0.25;

  return {
    num_inputs: nParts,
    inputs: activeParts,
    check_type: "input_similarity",
    pairwise_similarities: pairwiseSimilarities,
    avg_pairwise_similarity: avgSimilarity,
    min_pairwise_similarity: minSimilarity,
    is_valid: isValid,
    status: isValid ? "RELATED" : "UNRELATED",
    details: isValid
      ? `Average similarity of ${avgSimilarity.toFixed(3)} — inputs appear to be about the same topic.`
      : `Average similarity of ${avgSimilarity.toFixed(3)} — inputs appear to be about different topics.`
  };
}

module.exports = { validateRelatedness };
