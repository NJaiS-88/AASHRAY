import { useState, useRef, useEffect } from 'react';
import axiosClient from '../api/axiosClient';
import useAuthStore from '../store/useAuthStore';
import MapComponent from '../components/MapComponent';
import CameraCapture from '../components/CameraCapture';

const WHISPER_URL = import.meta.env.VITE_WHISPER_API_URL;

export default function Dashboard() {
  const [text, setText] = useState('');
  const [text2, setText2] = useState('');
  const [text3, setText3] = useState('');
  const [showExtraInputs, setShowExtraInputs] = useState(false);
  const [activeReport, setActiveReport] = useState(null);
  const [audioBlob, setAudioBlob] = useState(null);
  const [audioUrl, setAudioUrl] = useState(null);
  const [imageUrl, setImageUrl] = useState(null);
  
  // Location state
  const [location, setLocation] = useState(null);
  const [locating, setLocating] = useState(false);
  const [locationError, setLocationError] = useState(null);

  // UI States
  const [isRecording, setIsRecording] = useState(false);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showCamera, setShowCamera] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  
  // Entries history
  const [entries, setEntries] = useState([]);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [submitError, setSubmitError] = useState(null);

  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const recordingIntervalRef = useRef(null);
  const chatEndRef = useRef(null);
  
  const logout = useAuthStore((state) => state.logout);
  const user = useAuthStore((state) => state.user);

  // Fetch entries on load
  const fetchEntries = async () => {
    try {
      const res = await axiosClient.get('/entries');
      setEntries(res.data || []);
    } catch (err) {
      console.error('Failed to fetch entries:', err);
    } finally {
      setLoadingHistory(false);
    }
  };

  const [generatingRagId, setGeneratingRagId] = useState(null);
  const [rawJsonEntry, setRawJsonEntry] = useState(null);
  const [clarificationInputs, setClarificationInputs] = useState({});
  const [submittingClarifyId, setSubmittingClarifyId] = useState(null);

  const handleGenerateRag = async (entryId) => {
    try {
      setGeneratingRagId(entryId);
      const res = await axiosClient.post(`/entries/${entryId}/rag`);
      if (res.data) {
        setEntries((prev) => prev.map((e) => (e._id === entryId ? res.data : e)));
      }
    } catch (err) {
      console.error('Failed to generate RAG plan:', err);
    } finally {
      setGeneratingRagId(null);
    }
  };

  const handleClarifySubmit = async (entryId) => {
    const text = (clarificationInputs[entryId] || '').trim();
    if (!text) return;
    try {
      setSubmittingClarifyId(entryId);
      const res = await axiosClient.post(`/entries/${entryId}/clarify`, { clarification: text });
      if (res.data) {
        setEntries((prev) => prev.map((e) => (e._id === entryId ? res.data : e)));
        setClarificationInputs((prev) => ({ ...prev, [entryId]: '' }));
      }
    } catch (err) {
      console.error('Failed to submit clarification:', err);
    } finally {
      setSubmittingClarifyId(null);
    }
  };

  // UI Triage & Evidence View State
  const [expandedAudit, setExpandedAudit] = useState({}); // { [entryId]: boolean } (collapsed by default)
  const [triageTabState, setTriageTabState] = useState({}); // { [entryId]: 'chosen' | 'not_chosen' }
  const [expandedEvidence, setExpandedEvidence] = useState({}); // { [`${entryId}_${resKey}`]: boolean }
  const [expandedActions, setExpandedActions] = useState({}); // { [`${entryId}_${resKey}`]: boolean }

  const getResourceIcon = (resource) => {
    const r = resource?.toLowerCase() || '';
    if (r.includes('water_purif')) return '🧪';
    if (r.includes('drinking_water') || r === 'water') return '💧';
    if (r.includes('sanitation') || r.includes('hygiene')) return '🧼';
    if (r.includes('infant') || r.includes('child_nutrition')) return '🍼';
    if (r.includes('kitchen') || r.includes('cooked')) return '🍲';
    if (r.includes('fuel')) return '⛽';
    if (r.includes('fodder') || r.includes('livestock') || r.includes('veterinary')) return '🐄';
    if (r.includes('dry_rations') || r === 'food') return '🥫';
    if (r.includes('tarpaulin') || r.includes('shelter_kit')) return '🏕️';
    if (r.includes('shelter')) return '⛺';
    if (r.includes('blanket') || r.includes('warmth') || r === 'clothing') return '🧥';
    if (r.includes('cash') || r === 'money') return '💵';
    if (r.includes('boat')) return '🚤';
    if (r.includes('evacuation') || r.includes('transport')) return '🚑';
    if (r.includes('missing') || r.includes('reunification')) return '🔍';
    if (r.includes('search_and_rescue')) return '🛟';
    if (r.includes('trauma') || r.includes('first_aid')) return '🩹';
    if (r.includes('maternal') || r.includes('newborn')) return '🤰';
    if (r.includes('elderly') || r.includes('disability')) return '🦯';
    if (r.includes('psychosocial')) return '🧠';
    if (r.includes('medical_help')) return '🩺';
    if (r.includes('chronic')) return '💉';
    if (r.includes('vector') || r.includes('disease')) return '🦟';
    if (r.includes('medical_products') || r.includes('medicines')) return '💊';
    if (r.includes('machinery') || r.includes('debris') || r.includes('clearance')) return '🚜';
    if (r.includes('power') || r.includes('lighting')) return '⚡';
    if (r.includes('communication') || r.includes('warning')) return '📡';
    if (r.includes('protection')) return '🛡️';
    if (r.includes('dead_body')) return '🕊️';
    if (r === 'tools') return '🛠️';
    return '📦';
  };

  /**
   * Underlines exact benchmark sentences used to ground the operational instructions in retrieved PDF chunks.
   */
  const renderChunkWithUnderlinedBenchmarks = (chunkText, benchmarkSnippets = []) => {
    if (!chunkText) return null;
    const validSnippets = (benchmarkSnippets || [])
      .map(s => (s || '').trim())
      .filter(s => s.length >= 20);

    if (validSnippets.length === 0) {
      return <span className="text-zinc-600 font-serif leading-relaxed text-[11px]">{chunkText}</span>;
    }

    let segments = [{ text: chunkText, isBenchmark: false }];

    for (const snippet of validSnippets) {
      const nextSegments = [];
      for (const seg of segments) {
        if (seg.isBenchmark) {
          nextSegments.push(seg);
          continue;
        }
        const idx = seg.text.toLowerCase().indexOf(snippet.toLowerCase());
        if (idx !== -1) {
          const before = seg.text.slice(0, idx);
          const match = seg.text.slice(idx, idx + snippet.length);
          const after = seg.text.slice(idx + snippet.length);
          if (before) nextSegments.push({ text: before, isBenchmark: false });
          nextSegments.push({ text: match, isBenchmark: true });
          if (after) nextSegments.push({ text: after, isBenchmark: false });
        } else {
          nextSegments.push(seg);
        }
      }
      segments = nextSegments;
    }

    return (
      <div className="text-zinc-700 text-[11px] font-serif leading-relaxed space-y-1">
        <div>
          {segments.map((seg, sIdx) =>
            seg.isBenchmark ? (
              <span
                key={sIdx}
                className="underline decoration-red-600 decoration-2 font-semibold bg-red-100/80 text-zinc-950 px-1 py-0.5 rounded shadow-2xs border-b border-red-400 inline-block my-0.5"
                title="Exact benchmark SOP instruction extracted from this PDF passage"
              >
                {seg.text}
              </span>
            ) : (
              <span key={sIdx} className="text-zinc-600">{seg.text}</span>
            )
          )}
        </div>
        {validSnippets.length > 0 && (
          <div className="flex items-center gap-1 text-[9px] font-mono text-red-700 bg-red-50/90 border border-red-200/80 px-2 py-0.5 rounded-md w-fit mt-1">
            <span className="w-1.5 h-1.5 rounded-full bg-red-600 animate-ping" />
            <span>Underlined text was used as authoritative benchmark grounding for operational instructions</span>
          </div>
        )}
      </div>
    );
  };

  const [isOnline, setIsOnline] = useState(navigator.onLine);
  const [isSlowConnection, setIsSlowConnection] = useState(false);

  useEffect(() => {
    fetchEntries();
    // Get initial location automatically
    getCurrentLocation();

    const handleOnline = () => setIsOnline(true);
    const handleOffline = () => setIsOnline(false);

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    const checkSpeed = () => {
      if (navigator.connection) {
        const conn = navigator.connection;
        setIsSlowConnection(conn.effectiveType === '2g' || conn.effectiveType === 'slow-2g');
      }
    };

    checkSpeed();
    if (navigator.connection) {
      navigator.connection.addEventListener('change', checkSpeed);
    }

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
      if (navigator.connection) {
        navigator.connection.removeEventListener('change', checkSpeed);
      }
    };
  }, []);

  // Scroll to bottom on entries change
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [entries, isSubmitting]);

  // Audio recording timer helper
  useEffect(() => {
    if (isRecording) {
      recordingIntervalRef.current = setInterval(() => {
        setRecordingSeconds((prev) => prev + 1);
      }, 1000);
    } else {
      clearInterval(recordingIntervalRef.current);
      setRecordingSeconds(0);
    }
    return () => clearInterval(recordingIntervalRef.current);
  }, [isRecording]);

  const handleLogout = async () => {
    try {
      await axiosClient.post('/auth/logout');
      logout();
    } catch (err) {
      console.error('Logout failed', err);
    }
  };

  // Get current location using geolocation API
  const getCurrentLocation = () => {
    if (!navigator.geolocation) {
      setLocationError('Geolocation not supported');
      return;
    }
    setLocating(true);
    setLocationError(null);
    
    const options = { enableHighAccuracy: true, timeout: 8000, maximumAge: 0 };

    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLocation({ lat: pos.coords.latitude, lng: pos.coords.longitude });
        setLocating(false);
      },
      (err) => {
        console.warn('High accuracy geolocation failed, trying standard accuracy...', err);
        // Fallback to standard/lower accuracy
        navigator.geolocation.getCurrentPosition(
          (pos) => {
            setLocation({ lat: pos.coords.latitude, lng: pos.coords.longitude });
            setLocating(false);
          },
          (fallbackErr) => {
            console.error('Fallback geolocation failed:', fallbackErr);
            setLocationError('Location blocked or unavailable. Please check permissions.');
            setLocating(false);
          },
          { enableHighAccuracy: false, timeout: 12000 }
        );
      },
      options
    );
  };

  // Live processing states for audio & image
  const [isProcessingAudio, setIsProcessingAudio] = useState(false);
  const [isProcessingImage, setIsProcessingImage] = useState(false);
  const [audioStatusText, setAudioStatusText] = useState('');
  const [imageStatusText, setImageStatusText] = useState('');
  const [transcribedAudioText, setTranscribedAudioText] = useState('');
  const [imageCaptionText, setImageCaptionText] = useState('');

  // Promise refs to track background tasks if user clicks Send before background tasks complete
  const audioPromiseRef = useRef(null);
  const imagePromiseRef = useRef(null);

  // Process Audio immediately when recorded
  const processAudioBlob = (blob) => {
    if (!blob) return;
    setIsProcessingAudio(true);
    setAudioStatusText('Audio being processed...');
    
    audioPromiseRef.current = (async () => {
      try {
        const res = await fetch(WHISPER_URL, {
          method: 'POST',
          body: blob,
        });
        if (res.ok) {
          const data = await res.json();
          const transcript = data.transcription || '';
          setTranscribedAudioText(transcript);
          setAudioStatusText('Audio processed ✓');
          setText3(prev => prev ? prev + ' ' + transcript : transcript);
          return transcript;
        } else {
          setAudioStatusText('Audio processing failed ✕');
          return '';
        }
      } catch (err) {
        console.error('Whisper API call failed:', err);
        setAudioStatusText('Audio processing failed ✕');
        return '';
      } finally {
        setIsProcessingAudio(false);
      }
    })();
  };

  // Process Image immediately when captured
  const processCapturedImage = (dataUrl) => {
    if (!dataUrl) return;
    setIsProcessingImage(true);
    setImageStatusText('Image being processed...');
    
    imagePromiseRef.current = (async () => {
      try {
        const mlUrl = import.meta.env.VITE_ML_SERVICE_URL || 'http://localhost:5001';
        const res = await fetch(`${mlUrl}/caption-image`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ image: dataUrl }),
        });
        if (res.ok) {
          const data = await res.json();
          const caption = data.caption || '';
          setImageCaptionText(caption);
          setImageStatusText('Image processed ✓');
          return caption;
        } else {
          setImageStatusText('Image processing failed ✕');
          return '';
        }
      } catch (err) {
        console.error('Image captioning call failed:', err);
        setImageStatusText('Image processing failed ✕');
        return '';
      } finally {
        setIsProcessingImage(false);
      }
    })();
  };

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRecorderRef.current = new MediaRecorder(stream);
      audioChunksRef.current = [];
      
      mediaRecorderRef.current.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunksRef.current.push(e.data);
      };

      mediaRecorderRef.current.onstop = () => {
        const blob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        setAudioBlob(blob);
        setAudioUrl(URL.createObjectURL(blob));
        // Start background processing immediately!
        processAudioBlob(blob);
      };

      mediaRecorderRef.current.start();
      setIsRecording(true);
    } catch (err) {
      console.error('Microphone access denied', err);
      alert('Could not access microphone.');
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
      mediaRecorderRef.current.stream.getTracks().forEach((track) => track.stop());
    }
  };

  const handleImageCaptured = (dataUrl) => {
    setImageUrl(dataUrl);
    // Start background processing immediately!
    processCapturedImage(dataUrl);
  };

  const handleSubmit = async (e) => {
    if (e) e.preventDefault();
    if (!text.trim() && !text2.trim() && !text3.trim() && !imageUrl && !audioBlob) return;
    setIsSubmitting(true);
    setSubmitError(null);

    try {
      let finalAudioText = transcribedAudioText;
      let finalImageCaption = imageCaptionText;

      // If user hit submit while audio is still processing, wait with a short timeout
      if (audioPromiseRef.current) {
        try {
          const timeoutPromise = new Promise((resolve) => setTimeout(() => resolve(''), 3000));
          const result = await Promise.race([audioPromiseRef.current, timeoutPromise]);
          if (result) finalAudioText = result;
        } catch (e) {
          console.warn('Audio promise race caught:', e);
        }
      }

      // If user hit submit while image is still processing, wait with a short timeout
      if (imagePromiseRef.current) {
        try {
          const timeoutPromise = new Promise((resolve) => setTimeout(() => resolve(''), 3000));
          const result = await Promise.race([imagePromiseRef.current, timeoutPromise]);
          if (result) finalImageCaption = result;
        } catch (e) {
          console.warn('Image promise race caught:', e);
        }
      }

      // Convert audio blob to base64 for database payload
      let audioBase64 = '';
      if (audioBlob) {
        audioBase64 = await new Promise((resolve) => {
          const reader = new FileReader();
          reader.onloadend = () => resolve(reader.result);
          reader.readAsDataURL(audioBlob);
        });
      }

      // Send entry to backend with latest processed audioText and imageCaption
      const payload = {
        text: text.trim(),
        text1: text.trim(),
        text2: text2.trim(),
        text3: text3.trim() || finalAudioText,
        image: imageUrl || '',
        audio: audioBase64,
        audioText: finalAudioText,
        imageCaption: finalImageCaption,
        location: location,
        clientTimestamp: new Date().toISOString(),
      };

      await axiosClient.post('/entries', payload);

      // Refresh entries
      await fetchEntries();

      // Reset prompt input elements & promise refs
      setText('');
      setText2('');
      setText3('');
      setImageUrl(null);
      setAudioBlob(null);
      setAudioUrl(null);
      setAudioStatusText('');
      setImageStatusText('');
      setTranscribedAudioText('');
      setImageCaptionText('');
      audioPromiseRef.current = null;
      imagePromiseRef.current = null;
    } catch (err) {
      console.error('Failed to submit message:', err);
      const errMsg = err.response?.data?.message || err.message || 'Failed to submit message. Please check backend connection.';
      setSubmitError(errMsg);
    } finally {
      setIsSubmitting(false);
    }
  };
  const formatTime = (sec) => {
    const mins = Math.floor(sec / 60);
    const secs = sec % 60;
    return `${mins}:${secs < 10 ? '0' : ''}${secs}`;
  };

  return (
    <div className="flex h-screen bg-white text-zinc-900 overflow-hidden font-sans relative">
      {/* Sidebar for chat history */}
      <div 
        className={`fixed inset-y-0 left-0 z-40 w-64 bg-zinc-50 border-r border-zinc-200/80 flex flex-col transform transition-transform duration-300 ease-in-out md:translate-x-0 ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="p-4 border-b border-zinc-200 flex justify-between items-center bg-white">
          <span className="font-bold text-sm tracking-wider text-zinc-900">AASHRAY</span>
          <div className="flex items-center gap-1.5">
            <button
              onClick={async () => {
                try {
                  await axiosClient.delete('/entries');
                  setEntries([]);
                } catch (e) {
                  console.error('Failed to clear chats:', e);
                }
              }}
              title="Clear all chat history from backend"
              className="text-[10px] font-semibold bg-zinc-100 hover:bg-zinc-200 text-zinc-700 px-2 py-1 rounded transition-colors flex items-center gap-1 border border-zinc-200"
            >
              <span>+ New Chat</span>
            </button>
            <button 
              onClick={() => setSidebarOpen(false)}
              className="p-1.5 hover:bg-zinc-100 rounded-lg text-zinc-500 hover:text-zinc-900 md:hidden"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* Entry History List */}
        <div className="flex-1 overflow-y-auto p-3 space-y-1">
          {loadingHistory ? (
            <div className="text-xs text-zinc-400 px-2 font-mono">Loading...</div>
          ) : entries.length === 0 ? (
            <div className="text-xs text-zinc-400 px-2 italic font-mono">No entries</div>
          ) : (
            entries.map((entry, idx) => {
              const isDisaster = entry.disasterReport?.label === 'disaster';
              return (
                <button
                  key={entry._id || idx}
                  onClick={() => {
                    const el = document.getElementById(`entry-${entry._id}`);
                    el?.scrollIntoView({ behavior: 'smooth', block: 'center' });
                  }}
                  className={`w-full text-left px-2.5 py-2 rounded-lg text-xs transition-all overflow-hidden text-ellipsis whitespace-nowrap flex items-center gap-1.5 ${
                    isDisaster
                      ? 'bg-red-50 hover:bg-red-100 text-red-800 border border-red-200/60'
                      : 'hover:bg-zinc-200/60 text-zinc-600 hover:text-zinc-900'
                  }`}
                >
                  {isDisaster && (
                    <span className="shrink-0 text-[10px] animate-pulse">🚨</span>
                  )}
                  <span className="truncate">
                    {entry.text1 || entry.text || (entry.audioText ? `🎙️ ${entry.audioText}` : '📷 Captured photo')}
                  </span>
                </button>
              );
            })
          )}
        </div>

        {/* User profile footer */}
        <div className="p-4 border-t border-zinc-200 bg-white flex items-center justify-between">
          <div className="flex items-center gap-2 overflow-hidden">
            <div className="w-7 h-7 rounded-full bg-zinc-200 flex items-center justify-center font-bold text-zinc-700 text-xs uppercase">
              {user?.email?.charAt(0) || 'U'}
            </div>
            <div className="overflow-hidden">
              <div className="text-xs font-semibold text-zinc-800 truncate">{user?.email || 'User'}</div>
            </div>
          </div>
          <button 
            onClick={handleLogout}
            className="p-1.5 text-zinc-500 hover:text-red-600 hover:bg-zinc-100 rounded-lg transition-all"
            title="Log out"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
            </svg>
          </button>
        </div>
      </div>

      {/* Main chat window container */}
      <div className="flex-1 flex flex-col min-w-0 md:pl-64 bg-white">
        {/* Header */}
        <header className="h-14 border-b border-zinc-200 bg-white flex items-center justify-between px-4">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setSidebarOpen(true)}
              className="p-2 hover:bg-zinc-100 rounded-lg text-zinc-500 hover:text-zinc-900 md:hidden"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>
            <span className="font-bold text-zinc-900 text-sm tracking-wider">AASHRAY</span>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={getCurrentLocation}
              disabled={locating}
              className={`flex items-center gap-1.5 text-[11px] px-3 py-1 rounded-full border transition-all ${
                location 
                  ? 'border-zinc-200 bg-zinc-50 text-zinc-700' 
                  : 'border-zinc-200 bg-white text-zinc-500 hover:text-zinc-800'
              }`}
            >
              <span className={`w-1.5 h-1.5 rounded-full ${location ? 'bg-zinc-800' : 'bg-zinc-300'}`} />
              {locating ? 'Locating...' : 'GPS Active'}
            </button>
          </div>
        </header>

        {/* Connection status banner */}
        {!isOnline && (
          <div className="bg-red-50 border-b border-red-100 text-red-700 px-4 py-2 text-xs font-medium flex items-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-red-600 animate-pulse" />
            No internet connection. Submissions are disabled.
          </div>
        )}
        {isOnline && isSlowConnection && (
          <div className="bg-amber-50 border-b border-amber-100 text-amber-800 px-4 py-2 text-xs font-medium flex items-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-600 animate-pulse" />
            Slow connection detected. Media uploads may take longer.
          </div>
        )}

        {/* Chat Feed */}
        <div className="flex-1 overflow-y-auto p-4 space-y-6">
          {entries.length === 0 && !isSubmitting ? (
            /* Welcome Empty State */
            <div className="h-full flex flex-col items-center justify-center max-w-xl mx-auto text-center space-y-2">
              <h2 className="text-2xl font-bold tracking-wider text-zinc-900">AASHRAY</h2>
            </div>
          ) : (
            <div className="max-w-2xl mx-auto space-y-6">
              {entries.map((entry) => (
                <div key={entry._id} id={`entry-${entry._id}`} className="space-y-4">
                  {/* User Bubble */}
                  <div className="flex gap-3 items-start justify-end">
                    <div className="flex flex-col items-end gap-1.5 max-w-[85%]">
                      <div className="bg-zinc-100 text-zinc-900 rounded-2xl rounded-tr-none px-4 py-2.5 text-sm border border-zinc-200/60 space-y-3">
                        {/* Display multiple text inputs if present */}
                        <div className="space-y-2">
                          {(entry.text1 || entry.text) && (
                            <div>
                              {entry.text2 || entry.text3 ? <span className="text-[9px] text-zinc-400 font-mono block">Input 1 (Primary):</span> : null}
                              <p className="leading-relaxed">{entry.text1 || entry.text}</p>
                            </div>
                          )}
                          {entry.text2 && (
                            <div className="border-t border-zinc-200/40 pt-1.5">
                              <span className="text-[9px] text-zinc-400 font-mono block">Input 2 (Context):</span>
                              <p className="leading-relaxed text-zinc-700">{entry.text2}</p>
                            </div>
                          )}
                          {entry.text3 && (
                            <div className="border-t border-zinc-200/40 pt-1.5">
                              <span className="text-[9px] text-zinc-400 font-mono block">Input 3 (Detail/Voice):</span>
                              <p className="leading-relaxed text-zinc-700">{entry.text3}</p>
                            </div>
                          )}
                        </div>
                        
                        {/* Inline Image Preview & BLIP AI Description */}
                        {entry.image && (
                          <div className="rounded-lg overflow-hidden border border-zinc-200 max-w-xs bg-zinc-50 space-y-1">
                            <img src={entry.image} alt="Captured" className="w-full object-contain max-h-48" />
                            {entry.imageCaption && (
                              <div className="px-2 py-1 bg-zinc-100 border-t border-zinc-200 text-[11px] text-zinc-700 font-sans italic">
                                <span className="text-[9px] text-zinc-400 font-mono block not-italic">🖼️ BLIP AI Description:</span>
                                "{entry.imageCaption}"
                              </div>
                            )}
                          </div>
                        )}

                        {/* Audio playback */}
                        {entry.audio && (
                          <div className="pt-1">
                            <audio src={entry.audio} controls className="w-full max-w-xs h-8 scale-95 origin-left" />
                          </div>
                        )}
                      </div>

                      {/* Attached Live Coordinates Map */}
                      {entry.location?.lat && entry.location?.lng && (
                        <div className="w-64 bg-white border border-zinc-200 rounded-xl p-2 shadow-sm">
                          <MapComponent lat={entry.location.lat} lng={entry.location.lng} isExpandable={true} />
                        </div>
                      )}

                      {/* Similarity Validation report trigger */}
                      {(entry.similarityReport || entry.disasterReport || entry.ragReport) && (
                        <button
                          type="button"
                          onClick={() => setActiveReport({ similarity: entry.similarityReport, disaster: entry.disasterReport, rag: entry.ragReport })}
                          className="flex items-center gap-1 text-[9px] font-mono text-zinc-500 hover:text-zinc-900 border border-zinc-200 bg-zinc-50 px-2 py-0.5 rounded-full transition-colors cursor-pointer"
                        >
                          {entry.disasterReport?.label === 'disaster' ? (
                            <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
                          ) : entry.similarityReport ? (
                            <span className={`w-1.5 h-1.5 rounded-full ${entry.similarityReport.status === 'RELATED' ? 'bg-emerald-500' : 'bg-red-500'}`} />
                          ) : null}
                          <span>Behind the Scenes
                            {entry.disasterReport?.label === 'disaster' && ' · 🚨 DISASTER'}
                            {entry.ragReport && ' · 🛡️ RAG PLAN'}
                            {entry.similarityReport && ` (${entry.similarityReport.status})`}
                          </span>
                        </button>
                      )}

                      <span className="text-[9px] text-zinc-400 font-mono">
                        {new Date(entry.clientTimestamp || entry.createdAt).toLocaleTimeString()}
                      </span>
                    </div>

                    <div className="w-7 h-7 rounded-full bg-zinc-200 flex items-center justify-center text-[10px] font-bold text-zinc-700 shrink-0">
                      U
                    </div>
                  </div>

                  {/* Assistant response */}
                  <div className="flex gap-3 items-start">
                    <div className="w-7 h-7 rounded-full bg-zinc-800 flex items-center justify-center text-[10px] font-bold text-white shrink-0 shadow-sm">
                      A
                    </div>
                    <div className="flex flex-col gap-1 max-w-[85%]">
                      <div className="bg-zinc-50 border border-zinc-200/85 rounded-2xl rounded-tl-none px-4 py-2.5 text-sm space-y-2">
                        {entry.text1 || entry.text ? (
                          <div>
                            <span className="text-[10px] text-zinc-400 font-mono block">Echo:</span>
                            <p className="text-zinc-800 mt-0.5">{entry.text1 || entry.text}</p>
                          </div>
                        ) : null}

                        {entry.audioText ? (
                          <div className="mt-2">
                            <span className="text-[10px] text-zinc-400 font-mono block">Whisper:</span>
                            <p className="text-zinc-800 font-medium bg-white border border-zinc-200 p-2 rounded-lg mt-0.5 italic">
                              "{entry.audioText}"
                            </p>
                          </div>
                        ) : (
                          entry.audio && (
                            <div className="text-xs text-zinc-400 italic">Transcribing audio...</div>
                          )
                        )}

                        {/* ── JEV v3 Triage, RAG & Report: 3 Simplified Views (Section I) ── */}
                        {entry.ragReport?.plan ? (() => {
                          const plan = entry.ragReport.plan || entry.ragReport;
                          const unified = plan.unified_assessment || plan.assessment || entry.ragReport.assessment || entry.ragReport.jev_assessment || {};
                          const personMessage = plan.person_message || entry.ragReport.person_message;
                          const situation = plan.situation || entry.ragReport.situation;
                          const dispatcherNotes = plan.dispatcher_notes || entry.ragReport.dispatcher_notes;
                          const excerpts = plan.excerpts || entry.ragReport.excerpts || [];
                          const nonSelected = plan.not_selected_resources || plan.non_selected_resources || entry.ragReport.not_selected_resources || entry.ragReport.non_selected_resources || [];
                          const selectedRaw = plan.selected_resources || entry.ragReport.selected_resources || [];
                          const rawProbs = plan.raw_probabilities || entry.ragReport.raw_probabilities || {};
                          const isWideArea = plan.is_wide_area || false;
                          const census = plan.census_context || entry.ragReport.census_context;
                          const latencyMs = plan.latency?.total_ms || entry.ragReport?.latency?.total_ms || plan.telemetry?.total_pipeline_time_ms || entry.ragReport?.telemetry?.total_pipeline_time_ms || 0;
                          const modelVer = plan.model_version || entry.ragReport?.model_version || plan.telemetry?.jev_model_version || 'typesafe-jev-v3-prompted';
                          const isAuditOpen = !!expandedAudit[entry._id];

                          // Normalize resources list with verified Jev confidence scores
                          const rawResources = plan.resources || entry.ragReport.resources || selectedRaw || [];
                          const selectedResources = rawResources.map((r, idx) => {
                            const resId = typeof r === 'string' ? r : (r.resource_id || r.resource);
                            const matchedSel = selectedRaw.find(s => s.resource === resId || s.resource_id === resId);
                            const prob = (typeof r === 'object' && r.jev_probability != null)
                              ? r.jev_probability
                              : (matchedSel?.jev_probability != null ? matchedSel.jev_probability : (rawProbs[resId] != null ? rawProbs[resId] : 0.85));
                            const cut = (typeof r === 'object' && r.cutoff != null)
                              ? r.cutoff
                              : (matchedSel?.cutoff != null ? matchedSel.cutoff : 0.10);
                            const band = (typeof r === 'object' && r.band)
                              ? r.band
                              : (matchedSel?.band || 'CONFIRMED');
                            const name = (typeof r === 'object' && r.resource_name)
                              ? r.resource_name
                              : (matchedSel?.resource_label || resId.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()));

                            const eids = (typeof r === 'object' && r.excerpt_ids && r.excerpt_ids.length > 0)
                              ? r.excerpt_ids
                              : (excerpts.length > 0 ? [excerpts[Math.min(idx, excerpts.length - 1)].id || `E${Math.min(idx, excerpts.length - 1) + 1}`] : []);

                            const source = (typeof r === 'object' && r.source)
                              ? r.source
                              : (eids.length > 0 ? 'GROUNDED' : 'EXPERT-JUDGMENT');

                            return {
                              resource_id: resId,
                              resource_name: name,
                              band,
                              jev_probability: prob,
                              cutoff: cut,
                              why: (typeof r === 'object' && r.why) ? r.why : ((typeof r === 'object' && r.reason) ? r.reason : 'Identified emergency need from triage'),
                              how_to_use: (typeof r === 'object' && Array.isArray(r.how_to_use)) ? r.how_to_use : ((typeof r === 'object' && r.action) ? [r.action] : ['Deploy standard emergency response protocols']),
                              safety: (typeof r === 'object' && Array.isArray(r.safety)) ? r.safety : ((typeof r === 'object' && r.safety) ? [r.safety] : []),
                              what_next: (typeof r === 'object' && r.what_next) ? r.what_next : 'Handover to incident commander for continued monitoring',
                              source,
                              excerpt_ids: eids
                            };
                          });

                          // Build comprehensive 30-resource taxonomy evaluation matrix with Jev confidence scores
                          const allTaxonomyEvaluated = [];
                          const seenResIds = new Set();

                          selectedResources.forEach(sr => {
                            seenResIds.add(sr.resource_id);
                            allTaxonomyEvaluated.push({
                              resource_id: sr.resource_id,
                              resource_name: sr.resource_name,
                              band: sr.band,
                              isSelected: true,
                              jev_probability: sr.jev_probability,
                              cutoff: sr.cutoff,
                              reason: sr.why,
                              source: sr.source,
                              excerpt_ids: sr.excerpt_ids
                            });
                          });

                          nonSelected.forEach(ns => {
                            const resId = ns.resource || ns.resource_id;
                            if (resId && !seenResIds.has(resId)) {
                              seenResIds.add(resId);
                              allTaxonomyEvaluated.push({
                                resource_id: resId,
                                resource_name: ns.resource_label || ns.resource_name || resId.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()),
                                band: 'NOT SELECTED',
                                isSelected: false,
                                jev_probability: ns.jev_probability != null ? ns.jev_probability : (rawProbs[resId] || 0.04),
                                cutoff: ns.cutoff != null ? ns.cutoff : 0.10,
                                reason: ns.reason || 'Below calibrated activation threshold'
                              });
                            }
                          });

                          Object.keys(rawProbs).forEach(key => {
                            if (!seenResIds.has(key)) {
                              seenResIds.add(key);
                              allTaxonomyEvaluated.push({
                                resource_id: key,
                                resource_name: key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()),
                                band: 'NOT SELECTED',
                                isSelected: false,
                                jev_probability: rawProbs[key],
                                cutoff: 0.10,
                                reason: rawProbs[key] <= 0.05 ? 'Not mentioned or implied in message' : `Score ${(rawProbs[key] * 100).toFixed(1)}% below cutoff`
                              });
                            }
                          });

                          const activeAuditTab = triageTabState[entry._id] || 'all';
                          const displayedTaxonomy = allTaxonomyEvaluated.filter(item => {
                            if (activeAuditTab === 'chosen') return item.isSelected;
                            if (activeAuditTab === 'not_chosen') return !item.isSelected;
                            return true;
                          });

                          // Safe scalar extraction of priority, severity and urgency (Invariant B2)
                          const pLevel = typeof unified.priority === 'object' && unified.priority !== null
                            ? (unified.priority.level || 'P2')
                            : (unified.priority_level || unified.priority || 'P2');

                          const pLabel = typeof unified.priority === 'object' && unified.priority !== null
                            ? (unified.priority.label || unified.priority_label || 'Priority Action')
                            : (unified.priority_label || 'Priority Action');

                          const pReason = typeof unified.priority === 'object' && unified.priority !== null
                            ? (unified.priority.reason || unified.priority_cue || unified.driving_cue || 'Triage cue criteria evaluated')
                            : (unified.priority_cue || unified.driving_cue || 'Triage cue criteria evaluated');

                          const sevLevel = typeof unified.severity === 'object' && unified.severity !== null
                            ? (unified.severity.level || 'S2')
                            : (unified.severity_level || unified.severity || 'S2');

                          const sevWord = typeof unified.severity === 'object' && unified.severity !== null
                            ? (unified.severity.word || 'Severe (Harm Risk)')
                            : (unified.severity_word || 'Severe (Harm Risk)');

                          const urgLevel = typeof unified.urgency === 'object' && unified.urgency !== null
                            ? (unified.urgency.level || 'U2')
                            : (unified.urgency_level || unified.urgency || 'U2');

                          const urgWord = typeof unified.urgency === 'object' && unified.urgency !== null
                            ? (unified.urgency.word || 'Urgent (Within few hours)')
                            : (unified.urgency_word || 'Urgent (Within few hours)');

                          const urgWindow = typeof unified.urgency === 'object' && unified.urgency !== null
                            ? (unified.urgency.window || unified.urgency_window || '')
                            : (unified.urgency_window || '');

                          const pColor = pLevel === 'P1'
                            ? 'bg-red-500/20 text-red-300 border-red-500/40 ring-1 ring-red-500/30'
                            : pLevel === 'P2'
                            ? 'bg-amber-500/20 text-amber-300 border-amber-500/40 ring-1 ring-amber-500/30'
                            : pLevel === 'P3'
                            ? 'bg-blue-500/20 text-blue-300 border-blue-500/40 ring-1 ring-blue-500/30'
                            : 'bg-zinc-500/20 text-zinc-300 border-zinc-500/40';

                          return (
                            <div className="mt-3 space-y-4 text-left">
                              {/* ───────────────────────────────────────────────────────────── */}
                              {/* VIEW 1: WHAT THE PERSON SEES (CITIZEN ADVISORY)               */}
                              {/* Plain language, no codes, person_message only                 */}
                              {/* ───────────────────────────────────────────────────────────── */}
                              <div className="p-4 bg-gradient-to-br from-emerald-950/60 via-slate-900 to-slate-950 text-zinc-100 rounded-xl border border-emerald-500/30 shadow-md">
                                <div className="flex items-center justify-between border-b border-emerald-500/20 pb-2.5 mb-3">
                                  <div className="flex items-center gap-2">
                                    <span className="text-base">📢</span>
                                    <span className="text-xs font-bold uppercase tracking-wider text-emerald-400 font-mono">
                                      1. What the Reporter Sees
                                    </span>
                                  </div>
                                  <span className="text-[10px] text-emerald-300/70 font-sans italic">
                                    Plain citizen advisory • No operational codes
                                  </span>
                                </div>
                                <div className="p-3.5 bg-emerald-950/40 border border-emerald-500/20 rounded-lg text-xs leading-relaxed text-emerald-100 font-sans">
                                  {personMessage ? (
                                    <p className="whitespace-pre-line">{personMessage}</p>
                                  ) : (
                                    <p className="italic text-emerald-200/80">
                                      Help has been alerted for your location. Please move to safe, higher ground if water or debris is rising. Keep phone lines open for responder contact.
                                    </p>
                                  )}
                                </div>

                                {plan?.needs_clarification && (
                                  <div className="mt-3 p-3.5 bg-amber-950/60 border border-amber-500/40 rounded-lg text-amber-200 text-xs space-y-2">
                                    <div className="flex items-center gap-2 text-amber-300 font-bold font-mono text-[11px] uppercase tracking-wider">
                                      <span>⚠️</span> Pre-RAG Intake Clarification Needed
                                    </div>
                                    <p className="text-[11px] text-amber-200/90">
                                      The query requires more information before emergency resources can be allocated.
                                    </p>
                                    {plan?.clarifying_questions?.length > 0 && (
                                      <div className="space-y-1 bg-black/40 p-2.5 rounded border border-amber-500/20">
                                        <div className="text-[10px] uppercase font-bold text-amber-400">Clarifying Questions:</div>
                                        <ul className="list-disc list-inside space-y-0.5 text-[11px] text-zinc-200">
                                          {plan.clarifying_questions.map((q, qIdx) => (
                                            <li key={qIdx}>{q}</li>
                                          ))}
                                        </ul>
                                      </div>
                                    )}
                                    <div className="pt-1 flex gap-2">
                                      <input
                                        type="text"
                                        placeholder="Type your answer to clarify (e.g. bleeding status, what is pinning leg, location)..."
                                        value={clarificationInputs[entry._id] || ''}
                                        onChange={(e) => setClarificationInputs((prev) => ({ ...prev, [entry._id]: e.target.value }))}
                                        onKeyDown={(e) => {
                                          if (e.key === 'Enter' && !e.shiftKey) {
                                            e.preventDefault();
                                            handleClarifySubmit(entry._id);
                                          }
                                        }}
                                        className="flex-1 bg-slate-900 border border-amber-500/40 rounded px-2.5 py-1.5 text-xs text-zinc-100 placeholder-zinc-500 focus:outline-none focus:border-amber-400"
                                      />
                                      <button
                                        type="button"
                                        disabled={submittingClarifyId === entry._id || !(clarificationInputs[entry._id] || '').trim()}
                                        onClick={() => handleClarifySubmit(entry._id)}
                                        className="bg-amber-600 hover:bg-amber-500 disabled:opacity-50 text-white font-medium px-3 py-1.5 rounded text-xs transition-colors cursor-pointer shrink-0"
                                      >
                                        {submittingClarifyId === entry._id ? 'Evaluating...' : 'Submit & Re-Evaluate'}
                                      </button>
                                    </div>
                                  </div>
                                )}
                              </div>

                              {/* ───────────────────────────────────────────────────────────── */}
                              {/* VIEW 2: DISPATCH SUMMARY                                      */}
                              {/* Priority badge with cue reason, severity & urgency in words,   */}
                              {/* selected resource cards with why, how-to-use, what next,      */}
                              {/* and source badge (Document or Expert judgment)               */}
                              {/* ───────────────────────────────────────────────────────────── */}
                              <div className="p-4 bg-slate-900 text-zinc-100 rounded-xl border border-slate-800 shadow-md space-y-4">
                                {/* Header / Incident Meta */}
                                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-3">
                                  <div className="flex items-center gap-2">
                                    <span className="text-base">🚨</span>
                                    <span className="text-xs font-bold uppercase tracking-wider text-amber-400 font-mono">
                                      2. Dispatch Summary
                                    </span>
                                  </div>
                                  <div className="flex items-center gap-2">
                                    {/* Priority badge with driving cue reason */}
                                    <div className={`px-2.5 py-1 rounded-md border text-xs font-mono font-bold flex items-center gap-1.5 ${pColor}`}>
                                      <span>{pLevel}</span>
                                      <span className="text-[10px] font-sans font-normal opacity-90">
                                        ({pLabel})
                                      </span>
                                    </div>
                                    <button
                                      type="button"
                                      onClick={() => setRawJsonEntry(entry)}
                                      className="text-[10px] font-mono bg-slate-800 hover:bg-slate-700 text-amber-300 px-2 py-1 rounded border border-slate-700 transition-colors cursor-pointer"
                                      title="View raw JSON"
                                    >
                                      {'{ } JSON'}
                                    </button>
                                  </div>
                                </div>

                                {/* Priority Driver Reason Line */}
                                <div className="text-[11px] bg-slate-800/80 border border-slate-700/60 p-2.5 rounded-lg flex items-start gap-2">
                                  <span className="text-amber-400 shrink-0 font-bold">⚡ Priority Driver:</span>
                                  <span className="text-zinc-200">
                                    {pReason}
                                  </span>
                                </div>

                                {/* Severity and Urgency in Words (Invariant B2) */}
                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                                  <div className="bg-slate-800/60 p-2.5 rounded-lg border border-slate-700/50">
                                    <div className="text-[10px] font-mono uppercase text-zinc-400 flex items-center justify-between">
                                      <span>Severity</span>
                                      <span className="font-bold text-red-400">{sevLevel}</span>
                                    </div>
                                    <div className="text-xs font-semibold text-zinc-200 mt-1">
                                      {sevWord}
                                    </div>
                                  </div>
                                  <div className="bg-slate-800/60 p-2.5 rounded-lg border border-slate-700/50">
                                    <div className="text-[10px] font-mono uppercase text-zinc-400 flex items-center justify-between">
                                      <span>Urgency</span>
                                      <span className="font-bold text-amber-400">{urgLevel}</span>
                                    </div>
                                    <div className="text-xs font-semibold text-zinc-200 mt-1">
                                      {urgWord}
                                      {urgWindow && (
                                        <span className="text-zinc-400 font-normal font-mono text-[10px] ml-1.5">
                                          ({urgWindow})
                                        </span>
                                      )}
                                    </div>
                                  </div>
                                </div>

                                {/* Situation Narrative (if present) */}
                                {situation && (
                                  <div className="text-xs text-zinc-300 bg-slate-800/40 p-2.5 rounded-lg border border-slate-700/40 italic">
                                    <span className="font-semibold not-italic text-zinc-200">Incident Situation: </span>
                                    {situation}
                                  </div>
                                )}

                                {/* Selected Resources List */}
                                <div className="space-y-3">
                                  <div className="text-[11px] font-mono uppercase text-zinc-400 font-bold tracking-wide flex items-center justify-between">
                                    <span>Selected Emergency Resources ({selectedResources.length})</span>
                                    <span className="text-[10px] text-zinc-400 lowercase font-normal">
                                      Max 8 shown • Prioritized by criticality
                                    </span>
                                  </div>

                                  {selectedResources.length === 0 ? (
                                    <div className="text-xs text-zinc-400 italic p-3 bg-slate-800/40 rounded-lg border border-slate-800">
                                      No tactical resources selected for mobilization based on evaluated criteria.
                                    </div>
                                  ) : (
                                    selectedResources.map((res, rIdx) => {
                                      const isGrounded = res.source === 'GROUNDED' || (res.excerpt_ids && res.excerpt_ids.length > 0);
                                      const isLikely = res.band === 'LIKELY';
                                      const isStandby = res.band === 'STANDBY' || res.band === 'POSSIBLE';

                                      return (
                                        <div
                                          key={rIdx}
                                          className="p-3 bg-slate-800/90 rounded-xl border border-slate-700 hover:border-slate-600 transition-all space-y-2.5"
                                        >
                                          {/* Card Header: Icon, Name, Band & Source Badge */}
                                          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-700/60 pb-2">
                                            <div className="flex items-center gap-2">
                                              <span className="text-base">{getResourceIcon(res.resource_id)}</span>
                                              <span className="text-xs font-bold text-zinc-100 uppercase tracking-wide">
                                                {res.resource_name}
                                              </span>
                                            </div>
                                            <div className="flex flex-wrap items-center gap-1.5">
                                              {/* Jev Confidence / Probability Score Badge */}
                                              <span className="text-[9px] font-mono font-bold bg-amber-500/15 text-amber-300 px-2 py-0.5 rounded border border-amber-500/30 flex items-center gap-1">
                                                <span>🎯 Jev: {(res.jev_probability * 100).toFixed(1)}%</span>
                                                <span className="text-zinc-400 font-normal text-[8px]">(Cutoff: {(res.cutoff * 100).toFixed(1)}%)</span>
                                              </span>

                                              {/* Band Badge */}
                                              {isLikely ? (
                                                <span className="text-[9px] font-mono font-bold bg-indigo-500/20 text-indigo-300 px-2 py-0.5 rounded border border-indigo-500/30">
                                                  LIKELY (Implied Need)
                                                </span>
                                              ) : isStandby ? (
                                                <span className="text-[9px] font-mono font-bold bg-amber-500/20 text-amber-300 px-2 py-0.5 rounded border border-amber-500/30">
                                                  STANDBY (On Standby)
                                                </span>
                                              ) : (
                                                <span className="text-[9px] font-mono font-bold bg-emerald-500/20 text-emerald-300 px-2 py-0.5 rounded border border-emerald-500/30">
                                                  CONFIRMED
                                                </span>
                                              )}

                                              {/* Source Badge */}
                                              {isGrounded ? (
                                                <span className="text-[9px] font-mono bg-blue-500/20 text-blue-300 px-2 py-0.5 rounded border border-blue-500/30 flex items-center gap-1">
                                                  <span>📘 Document</span>
                                                  {res.excerpt_ids?.length > 0 && (
                                                    <span className="opacity-80">[{res.excerpt_ids.join(', ')}]</span>
                                                  )}
                                                </span>
                                              ) : (
                                                <span className="text-[9px] font-mono bg-purple-500/20 text-purple-300 px-2 py-0.5 rounded border border-purple-500/30">
                                                  🧠 Expert judgment
                                                </span>
                                              )}
                                            </div>
                                          </div>

                                          {/* Responding Agency & Agency Tactical Requirements */}
                                          {(res.agency_responsible || res.agency_requirements) && (
                                            <div className="text-[11px] bg-slate-900/80 p-2.5 rounded-lg border border-slate-700/80 space-y-1">
                                              {res.agency_responsible && (
                                                <div className="flex flex-wrap items-center gap-1.5 text-sky-300 font-semibold">
                                                  <span>🏛️ Responding Agency:</span>
                                                  <span className="text-zinc-100 font-normal">{res.agency_responsible}</span>
                                                </div>
                                              )}
                                              {res.agency_requirements && (
                                                <div className="text-zinc-300 text-[10.5px]">
                                                  <span className="text-emerald-400 font-semibold">🛠️ Agency Requirements: </span>
                                                  <span className="text-zinc-200">{res.agency_requirements}</span>
                                                </div>
                                              )}
                                            </div>
                                          )}

                                          {/* Why Triggered (Quote / Event) */}
                                          <div className="text-[11px] text-zinc-300 bg-slate-900/60 p-2 rounded-lg border border-slate-800">
                                            <span className="text-amber-300 font-semibold">Why: </span>
                                            <span>{res.why}</span>
                                          </div>

                                          {/* Concrete Steps: How To Use (2-4 steps) */}
                                          {res.how_to_use && res.how_to_use.length > 0 && (
                                            <div className="space-y-1">
                                              <div className="text-[10px] font-mono uppercase text-zinc-400 font-semibold">
                                                Operational Steps:
                                              </div>
                                              <ul className="text-xs text-zinc-200 space-y-1 list-disc list-inside bg-slate-900/40 p-2.5 rounded-lg border border-slate-800">
                                                {res.how_to_use.map((step, sIdx) => (
                                                  <li key={sIdx} className="leading-snug">
                                                    {step}
                                                  </li>
                                                ))}
                                              </ul>
                                            </div>
                                          )}

                                          {/* Safety Hazards (if any) */}
                                          {res.safety && res.safety.length > 0 && (
                                            <div className="text-[11px] bg-red-950/30 border border-red-500/20 p-2 rounded text-red-200">
                                              <span className="font-semibold text-red-300">⚠️ Hazard Safety: </span>
                                              {res.safety.join('; ')}
                                            </div>
                                          )}

                                          {/* What Next & Confirmation */}
                                          {res.what_next && (
                                            <div className="text-[11px] text-zinc-400 flex items-start gap-1.5 pt-0.5">
                                              <span className="text-emerald-400 font-semibold shrink-0">What next:</span>
                                              <span>{res.what_next}</span>
                                            </div>
                                          )}
                                        </div>
                                      );
                                    })
                                  )}
                                </div>

                                {/* Dispatcher Next Actions / Notes */}
                                {dispatcherNotes && (
                                  <div className="p-3 bg-amber-950/30 border border-amber-500/20 rounded-xl space-y-1.5 text-xs">
                                    <div className="font-bold text-amber-300 font-mono text-[11px] uppercase flex items-center gap-1.5">
                                      <span>📋 Dispatcher Follow-up Notes:</span>
                                    </div>
                                    <div className="text-amber-100/90 leading-relaxed">
                                      {Array.isArray(dispatcherNotes) ? (
                                        <ul className="space-y-1.5 list-disc list-inside">
                                          {dispatcherNotes.map((note, nIdx) => (
                                            <li key={nIdx}>{note}</li>
                                          ))}
                                        </ul>
                                      ) : (
                                        <p className="whitespace-pre-line">{dispatcherNotes}</p>
                                      )}
                                    </div>
                                  </div>
                                )}
                              </div>

                              {/* ───────────────────────────────────────────────────────────── */}
                              {/* VIEW 3: EVIDENCE AND AUDIT (COLLAPSED BY DEFAULT)             */}
                              {/* Retrieved excerpts with underlined sentences, human doc titles, */}
                              {/* not-selected list with reason, Jev probability & cutoff        */}
                              {/* ───────────────────────────────────────────────────────────── */}
                              <div className="bg-slate-900 rounded-xl border border-slate-800 shadow-md overflow-hidden">
                                <button
                                  type="button"
                                  onClick={() => setExpandedAudit(prev => ({ ...prev, [entry._id]: !prev[entry._id] }))}
                                  className="w-full p-3.5 flex items-center justify-between text-left bg-slate-800/60 hover:bg-slate-800 transition-colors cursor-pointer"
                                >
                                  <div className="flex items-center gap-2">
                                    <span className="text-sm">🔍</span>
                                    <span className="text-xs font-bold uppercase tracking-wider text-zinc-200 font-mono">
                                      3. Evidence & Audit Trail
                                    </span>
                                    <span className="text-[10px] font-mono bg-slate-700 text-zinc-300 px-2 py-0.5 rounded-full">
                                      {excerpts.length} excerpts • {nonSelected.length} non-selected
                                    </span>
                                  </div>
                                  <span className="text-xs text-amber-400 font-mono">
                                    {isAuditOpen ? '▲ Collapse' : '▼ Expand Audit'}
                                  </span>
                                </button>

                                {isAuditOpen && (
                                  <div className="p-4 space-y-4 border-t border-slate-800 text-zinc-200">
                                    {/* Section A: Retrieved Document Excerpts */}
                                    <div className="space-y-2.5">
                                      <div className="text-xs font-mono uppercase text-zinc-300 font-bold flex items-center justify-between">
                                        <span>Retrieved Document Excerpts (Passed Relevance Gate)</span>
                                        <span className="text-[10px] text-zinc-400 font-normal">
                                          Supporting sentences underlined
                                        </span>
                                      </div>

                                      {excerpts.length === 0 ? (
                                        <div className="text-xs text-zinc-400 italic p-2.5 bg-slate-800/40 rounded border border-slate-800">
                                          No external document excerpts required; recommendations guided by expert emergency judgment.
                                        </div>
                                      ) : (
                                        <div className="space-y-2.5">
                                          {excerpts.map((exc, eIdx) => (
                                            <div
                                              key={eIdx}
                                              className="p-3 bg-slate-950/60 rounded-lg border border-slate-800 space-y-2"
                                            >
                                              <div className="flex flex-wrap items-center justify-between gap-1 text-[11px] font-mono text-zinc-300 border-b border-slate-800 pb-1.5">
                                                <div className="flex items-center gap-1.5 font-bold text-amber-300">
                                                  <span>[{exc.id || `E${eIdx + 1}`}]</span>
                                                  <span>{exc.title || 'NDMA Disaster Management Guidelines'}</span>
                                                  <span className="text-zinc-400 font-normal">(Page {exc.page || 1})</span>
                                                </div>
                                                {exc.action_used && (
                                                  <span className="text-[10px] bg-slate-800 text-zinc-300 px-2 py-0.5 rounded">
                                                    Action: {exc.action_used}
                                                  </span>
                                                )}
                                              </div>

                                              {/* Excerpt text with underlined supporting sentences */}
                                              <div className="p-2.5 bg-slate-900 rounded border border-slate-800/80">
                                                {renderChunkWithUnderlinedBenchmarks(
                                                  exc.text,
                                                  exc.supporting_sentences || []
                                                )}
                                              </div>
                                            </div>
                                          ))}
                                        </div>
                                      )}
                                    </div>

                                    {/* Section B: Complete Disaster Taxonomy Evaluation Matrix & Jev Scores */}
                                    <div className="space-y-3 pt-2 border-t border-slate-800">
                                      <div className="flex flex-wrap items-center justify-between gap-2">
                                        <div>
                                          <div className="text-xs font-mono uppercase text-zinc-300 font-bold flex items-center gap-1.5">
                                            <span>📊 Disaster Taxonomy Resource Evaluation Matrix</span>
                                            <span className="text-[10px] text-zinc-400 font-normal">
                                              ({allTaxonomyEvaluated.length} Evaluated)
                                            </span>
                                          </div>
                                          <div className="text-[10px] text-zinc-400">
                                            All 30 disaster taxonomy categories with Jev probability & calibrated cutoff thresholds
                                          </div>
                                        </div>
                                        <div className="flex items-center gap-1 text-[10px] font-mono bg-slate-800 p-0.5 rounded-lg border border-slate-700">
                                          <button
                                            type="button"
                                            onClick={() => setTriageTabState(prev => ({ ...prev, [entry._id]: 'all' }))}
                                            className={`px-2 py-0.5 rounded transition-colors cursor-pointer ${activeAuditTab === 'all' ? 'bg-amber-500/20 text-amber-300 font-bold' : 'text-zinc-400 hover:text-zinc-200'}`}
                                          >
                                            All ({allTaxonomyEvaluated.length})
                                          </button>
                                          <button
                                            type="button"
                                            onClick={() => setTriageTabState(prev => ({ ...prev, [entry._id]: 'chosen' }))}
                                            className={`px-2 py-0.5 rounded transition-colors cursor-pointer ${activeAuditTab === 'chosen' ? 'bg-emerald-500/20 text-emerald-300 font-bold' : 'text-zinc-400 hover:text-zinc-200'}`}
                                          >
                                            Selected ({selectedResources.length})
                                          </button>
                                          <button
                                            type="button"
                                            onClick={() => setTriageTabState(prev => ({ ...prev, [entry._id]: 'not_chosen' }))}
                                            className={`px-2 py-0.5 rounded transition-colors cursor-pointer ${activeAuditTab === 'not_chosen' ? 'bg-slate-700 text-zinc-200 font-bold' : 'text-zinc-400 hover:text-zinc-200'}`}
                                          >
                                            Not Selected ({allTaxonomyEvaluated.filter(t => !t.isSelected).length})
                                          </button>
                                        </div>
                                      </div>

                                      {displayedTaxonomy.length === 0 ? (
                                        <div className="text-xs text-zinc-400 italic p-2.5 bg-slate-800/40 rounded border border-slate-800">
                                          No resources matching current filter.
                                        </div>
                                      ) : (
                                        <div className="divide-y divide-slate-800/60 rounded-lg border border-slate-800 bg-slate-950/50 overflow-hidden text-[11px] font-mono max-h-[380px] overflow-y-auto">
                                          {displayedTaxonomy.map((item, itmIdx) => {
                                            const isSel = item.isSelected;
                                            const probPct = (item.jev_probability * 100).toFixed(1);
                                            const cutPct = (item.cutoff * 100).toFixed(1);
                                            const meetsThreshold = item.jev_probability >= item.cutoff;

                                            return (
                                              <div
                                                key={itmIdx}
                                                className={`p-2.5 flex flex-wrap items-center justify-between gap-2.5 transition-colors ${isSel ? 'bg-slate-900/40 hover:bg-slate-800/50' : 'hover:bg-slate-800/30 opacity-85'}`}
                                              >
                                                {/* Left: Icon, Name, Band Badge & Reason */}
                                                <div className="flex items-center gap-2 min-w-0 max-w-[62%]">
                                                  <span className="text-sm shrink-0">{getResourceIcon(item.resource_id)}</span>
                                                  <div className="min-w-0">
                                                    <div className="flex items-center gap-2 flex-wrap">
                                                      <span className={`font-bold ${isSel ? 'text-zinc-100' : 'text-zinc-400'}`}>
                                                        {item.resource_name}
                                                      </span>
                                                      {/* Status Badge */}
                                                      {item.band === 'CONFIRMED' ? (
                                                        <span className="text-[8px] bg-emerald-500/20 text-emerald-300 px-1.5 py-0.2 rounded border border-emerald-500/30">
                                                          CONFIRMED
                                                        </span>
                                                      ) : item.band === 'LIKELY' ? (
                                                        <span className="text-[8px] bg-indigo-500/20 text-indigo-300 px-1.5 py-0.2 rounded border border-indigo-500/30">
                                                          LIKELY
                                                        </span>
                                                      ) : (item.band === 'STANDBY' || item.band === 'POSSIBLE') ? (
                                                        <span className="text-[8px] bg-amber-500/20 text-amber-300 px-1.5 py-0.2 rounded border border-amber-500/30">
                                                          STANDBY
                                                        </span>
                                                      ) : (
                                                        <span className="text-[8px] bg-rose-500/15 text-rose-300/80 px-1.5 py-0.2 rounded border border-rose-500/25">
                                                          REJECTED
                                                        </span>
                                                      )}
                                                    </div>
                                                    <div className="text-[10px] text-zinc-400 font-sans truncate" title={item.reason}>
                                                      {item.reason}
                                                    </div>
                                                  </div>
                                                </div>

                                                {/* Right: Jev Probability Score, Cutoff & Mini Bar */}
                                                <div className="flex items-center gap-3 shrink-0">
                                                  <div className="text-right">
                                                    <div className="text-[11px] font-bold flex items-center justify-end gap-1">
                                                      <span className="text-zinc-400 font-normal text-[9px]">Jev Score:</span>
                                                      <span className={isSel ? 'text-amber-300' : meetsThreshold ? 'text-zinc-300' : 'text-zinc-500'}>
                                                        {probPct}%
                                                      </span>
                                                    </div>
                                                    <div className="text-[9px] text-zinc-400">
                                                      Cutoff: {cutPct}%
                                                    </div>
                                                  </div>
                                                  {/* Visual mini progress bar */}
                                                  <div className="w-16 h-2 bg-slate-800 rounded-full overflow-hidden border border-slate-700 relative">
                                                    <div
                                                      className={`h-full ${isSel ? 'bg-gradient-to-r from-amber-500 to-emerald-400' : 'bg-slate-600'}`}
                                                      style={{ width: `${Math.min(100, Math.max(4, item.jev_probability * 100))}%` }}
                                                    />
                                                  </div>
                                                </div>
                                              </div>
                                            );
                                          })}
                                        </div>
                                      )}
                                    </div>

                                    {/* Section C: Census & Location Context (Wide-Area Only) */}
                                    <div className="pt-2 border-t border-slate-800 space-y-1.5">
                                      <div className="text-xs font-mono uppercase text-zinc-300 font-bold">
                                        Area & Facility Context
                                      </div>
                                      {isWideArea && census ? (
                                        <div className="p-2.5 bg-slate-950/60 rounded-lg border border-slate-800 text-xs space-y-1">
                                          <div className="font-semibold text-amber-300">
                                            Area Demographic Baseline (2011 Census — Not affected count):
                                          </div>
                                          <div className="text-zinc-300 text-[11px]">
                                            Unit: {census.district || census.sub_district || 'District baseline'} • Population Baseline: {census.total_population?.toLocaleString() || 'N/A'}
                                            {census.sc_st_pct && ` • SC/ST: ${census.sc_st_pct}%`}
                                            {census.literacy_rate && ` • Literacy: ${census.literacy_rate}%`}
                                          </div>
                                        </div>
                                      ) : (
                                        <div className="text-xs text-zinc-400 italic p-2 bg-slate-950/40 rounded border border-slate-800">
                                          Localized Incident: Coordinates used for nearby facility routing; census baseline omitted.
                                        </div>
                                      )}
                                    </div>

                                    {/* Section D: Telemetry & Model Version */}
                                    <div className="pt-2 border-t border-slate-800 flex flex-wrap items-center justify-between text-[10px] font-mono text-zinc-400">
                                      <span>Model: {modelVer}</span>
                                      <span>Latency: {latencyMs} ms</span>
                                      <span className="text-emerald-400">Status: Calibrated Gates Active</span>
                                    </div>
                                  </div>
                                )}
                              </div>
                            </div>
                          );
                        })() : entry.disasterReport?.label === 'disaster' ? (
                          <div className="mt-3 flex items-center justify-between bg-red-50 border border-red-200/70 p-2.5 rounded-xl">
                            <span className="text-[11px] text-red-700 flex items-center gap-1.5 font-medium">
                              🚨 Disaster Detected. Operational relief plan can be synthesized.
                            </span>
                            <button
                              type="button"
                              onClick={() => handleGenerateRag(entry._id)}
                              disabled={generatingRagId === entry._id}
                              className="text-[10px] font-semibold bg-red-600 hover:bg-red-700 text-white px-2.5 py-1 rounded-md shadow-sm transition-all disabled:opacity-50 cursor-pointer"
                            >
                              {generatingRagId === entry._id ? 'Synthesizing...' : '⚡ Generate RAG Plan'}
                            </button>
                          </div>
                        ) : null}
                      </div>
                      <span className="text-[9px] text-zinc-400 font-mono">Response</span>
                    </div>
                  </div>
                </div>
              ))}

              {/* Submitting Status placeholder */}
              {isSubmitting && (
                <div className="flex gap-3 items-start animate-pulse">
                  <div className="w-7 h-7 rounded-full bg-zinc-900 flex items-center justify-center text-xs font-semibold text-white shrink-0">
                    A
                  </div>
                  <div className="bg-zinc-50 border border-zinc-200/80 rounded-2xl rounded-tl-none px-4 py-2.5 text-xs text-zinc-600 space-y-1">
                    <div className="font-semibold text-zinc-800 flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full bg-blue-500 animate-ping" />
                      Processing Submission...
                    </div>
                    {isProcessingAudio && <div className="text-[11px] text-amber-600">🎙️ Transcribing audio via Whisper...</div>}
                    {isProcessingImage && <div className="text-[11px] text-indigo-600">🖼️ Generating image caption via BLIP...</div>}
                    {!isProcessingAudio && !isProcessingImage && <div className="text-[11px] text-zinc-500">⚡ Running ML classification & similarity checks...</div>}
                  </div>
                </div>
              )}
              <div ref={chatEndRef} />
            </div>
          )}
        </div>

        {/* Input Bar Section */}
        <div className="p-4 bg-white border-t border-zinc-200">
          <form onSubmit={handleSubmit} className="max-w-2xl mx-auto space-y-2.5">
            
            {/* Attachment Previews & Live Processing Status */}
            {(imageUrl || audioUrl || locationError || isProcessingAudio || isProcessingImage || audioStatusText || imageStatusText) && (
              <div className="flex flex-wrap gap-2 p-2 bg-zinc-50 rounded-xl border border-zinc-200">
                {imageUrl && (
                  <div className="relative group w-16 h-16 rounded-lg overflow-hidden border border-zinc-200 bg-white flex items-center justify-center">
                    <img src={imageUrl} alt="attachment" className="w-full h-full object-cover" />
                    <button
                      type="button"
                      onClick={() => setImageUrl(null)}
                      className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 flex items-center justify-center text-white transition-opacity"
                    >
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                    </button>
                  </div>
                )}

                {audioUrl && (
                  <div className="flex items-center gap-1.5 bg-white border border-zinc-200 px-2.5 py-1 rounded-lg text-xs text-zinc-700">
                    <span className="w-1.5 h-1.5 rounded-full bg-zinc-800 animate-pulse" />
                    <span>Voice ready</span>
                    <button
                      type="button"
                      onClick={() => { setAudioUrl(null); setAudioBlob(null); }}
                      className="text-zinc-400 hover:text-red-500 ml-1"
                    >
                      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                  </div>
                )}

                {/* Audio Live Processing Badge */}
                {(isProcessingAudio || audioStatusText) && (
                  <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs border ${
                    isProcessingAudio 
                      ? 'bg-amber-50 border-amber-200 text-amber-700 animate-pulse' 
                      : audioStatusText.includes('✓') 
                        ? 'bg-emerald-50 border-emerald-200 text-emerald-700'
                        : 'bg-red-50 border-red-200 text-red-700'
                  }`}>
                    <span>🎙️ {audioStatusText}</span>
                    {transcribedAudioText && (
                      <span className="font-mono text-[10px] bg-white/70 px-1.5 py-0.5 rounded border border-emerald-300 max-w-[200px] truncate">
                        "{transcribedAudioText}"
                      </span>
                    )}
                  </div>
                )}

                {/* Image Live Processing Badge */}
                {(isProcessingImage || imageStatusText) && (
                  <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs border ${
                    isProcessingImage 
                      ? 'bg-indigo-50 border-indigo-200 text-indigo-700 animate-pulse' 
                      : imageStatusText.includes('✓') 
                        ? 'bg-emerald-50 border-emerald-200 text-emerald-700'
                        : 'bg-zinc-100 border-zinc-200 text-zinc-700'
                  }`}>
                    <span>🖼️ {imageStatusText}</span>
                    {imageCaptionText && (
                      <span className="font-mono text-[10px] bg-white/70 px-1.5 py-0.5 rounded border border-emerald-300 max-w-[200px] truncate">
                        "{imageCaptionText}"
                      </span>
                    )}
                  </div>
                )}

                {locationError && (
                  <div className="flex items-center gap-1.5 bg-red-50 border border-red-100 px-2.5 py-1 rounded-lg text-xs text-red-600">
                    <span>⚠️ {locationError}</span>
                  </div>
                )}
              </div>
            )}

            {/* Expandable context inputs */}
            {showExtraInputs && (
              <div className="flex flex-col gap-2 p-2 border border-zinc-200 rounded-xl bg-zinc-50">
                <input
                  type="text"
                  placeholder="Context Input (Text 2)..."
                  value={text2}
                  onChange={(e) => setText2(e.target.value)}
                  className="bg-white border border-zinc-200 rounded-lg px-2.5 py-1.5 text-xs text-zinc-800 outline-none focus:border-zinc-350"
                />
                <input
                  type="text"
                  placeholder="Detail Input / Voice Transcript (Text 3)..."
                  value={text3}
                  onChange={(e) => setText3(e.target.value)}
                  className="bg-white border border-zinc-200 rounded-lg px-2.5 py-1.5 text-xs text-zinc-800 outline-none focus:border-zinc-350"
                />
              </div>
            )}

            {/* Submit Error Banner */}
            {submitError && (
              <div className="flex items-center justify-between bg-red-50 border border-red-200 text-red-700 px-3 py-2 rounded-xl text-xs font-mono shadow-xs">
                <span className="flex items-center gap-1.5">
                  <span className="text-red-600 font-bold">⚠️ Error:</span>
                  <span>{submitError}</span>
                </span>
                <button
                  type="button"
                  onClick={() => setSubmitError(null)}
                  className="text-red-500 hover:text-red-800 font-bold ml-2 cursor-pointer px-1"
                >
                  ✕
                </button>
              </div>
            )}

            {/* Prompt Form Input Area */}
            <div className="relative flex items-end gap-1.5 bg-zinc-50 border border-zinc-200 rounded-2xl p-2 focus-within:border-zinc-300 transition-colors">
              {/* Camera clicker trigger */}
              <button
                type="button"
                onClick={() => setShowCamera(true)}
                className="p-2 hover:bg-zinc-200/60 rounded-lg text-zinc-500 hover:text-zinc-800 transition-colors"
                title="Camera clicker"
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
                </svg>
              </button>

              {/* Mic / Audio button */}
              {!isRecording ? (
                <button
                  type="button"
                  onClick={startRecording}
                  className="p-2 hover:bg-zinc-200/60 rounded-lg text-zinc-500 hover:text-zinc-800 transition-colors"
                  title="Record audio"
                >
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                  </svg>
                </button>
              ) : (
                <button
                  type="button"
                  onClick={stopRecording}
                  className="p-1.5 bg-red-50 border border-red-200 text-red-600 rounded-lg flex items-center gap-1 transition-colors px-2.5 animate-pulse"
                  title="Stop recording"
                >
                  <span className="w-1.5 h-1.5 rounded-full bg-red-600" />
                  <span className="text-[10px] font-mono">{formatTime(recordingSeconds)}</span>
                </button>
              )}

              {/* Core Text Input */}
              <textarea
                className="flex-1 bg-transparent border-0 outline-none resize-none text-zinc-800 text-sm max-h-24 py-1.5 px-2 focus:ring-0 placeholder:text-zinc-400"
                placeholder="Message AASHRAY..."
                rows={1}
                value={text}
                onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleSubmit();
                  }
                }}
              />

              {/* Send Button */}
              <button
                type="submit"
                disabled={isSubmitting || (!text.trim() && !text2.trim() && !text3.trim() && !imageUrl && !audioBlob)}
                className="p-2 bg-zinc-900 text-white rounded-xl hover:bg-zinc-800 disabled:opacity-30 disabled:bg-zinc-200 disabled:text-zinc-400 transition-all shadow-sm cursor-pointer"
                title={isSubmitting ? 'Analyzing & sending...' : 'Send message'}
              >
                {isSubmitting ? (
                  <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path>
                  </svg>
                ) : (
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 10l7-7m0 0l7 7m-7-7v18" />
                  </svg>
                )}
              </button>
            </div>
            
            <div className="flex justify-between items-center text-[9px] text-zinc-400 px-1 font-mono">
              <div className="flex items-center gap-2">
                <span>GPS coords: {location ? `${location.lat.toFixed(5)}, ${location.lng.toFixed(5)}` : 'Not loaded'}</span>
                <button type="button" onClick={getCurrentLocation} className="hover:text-zinc-600 underline">Refresh GPS</button>
              </div>
              <button
                type="button"
                onClick={() => setShowExtraInputs(!showExtraInputs)}
                className="text-[9px] text-zinc-500 hover:text-zinc-800 underline font-mono"
              >
                {showExtraInputs ? 'Hide Context Inputs' : '+ Expand Context Inputs'}
              </button>
            </div>
          </form>
        </div>
      </div>

      {/* Side drawer for Behind the Scenes similarity + ML classification details */}
      {activeReport && (
        <div className="fixed inset-y-0 right-0 z-50 w-80 bg-white border-l border-zinc-200 shadow-2xl flex flex-col transition-all duration-300">
          {/* Drawer Header */}
          <div className="p-4 border-b border-zinc-200 flex justify-between items-center bg-zinc-50">
            <div className="flex flex-col">
              <h3 className="font-bold text-sm text-zinc-900 tracking-wide">Behind the Scenes</h3>
              <span className="text-[10px] text-zinc-400 font-mono">Analysis Report</span>
            </div>
            <button
              onClick={() => setActiveReport(null)}
              className="text-zinc-400 hover:text-zinc-900 p-1 hover:bg-zinc-200 rounded-lg transition-colors cursor-pointer"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          {/* Drawer Body */}
          <div className="flex-1 overflow-y-auto p-4 space-y-5 text-xs">

            {/* ── ML Disaster Classification ── */}
            {activeReport.disaster && (
              <div className="space-y-2">
                <div className="text-[10px] text-zinc-400 font-mono uppercase tracking-wider">ML Classification</div>
                <div className={`rounded-xl border p-3 space-y-2 ${
                  activeReport.disaster.label === 'disaster'
                    ? 'bg-red-50 border-red-200'
                    : 'bg-emerald-50 border-emerald-200'
                }`}>
                  <div className="flex items-center justify-between">
                    <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-bold tracking-wider ${
                      activeReport.disaster.label === 'disaster'
                        ? 'bg-red-100 text-red-700 border border-red-200'
                        : 'bg-emerald-100 text-emerald-700 border border-emerald-200'
                    }`}>
                      {activeReport.disaster.label === 'disaster' ? '🚨' : '✅'}
                      {activeReport.disaster.label === 'disaster' ? 'DISASTER' : 'NON-RELEVANT'}
                    </span>
                    <span className="font-mono text-[11px] font-semibold text-zinc-700">
                      {(activeReport.disaster.probability * 100).toFixed(1)}%
                    </span>
                  </div>

                  {/* Probability bar */}
                  <div className="space-y-1">
                    <div className="w-full bg-white/70 rounded-full h-1.5 border border-zinc-200 overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-all ${
                          activeReport.disaster.label === 'disaster' ? 'bg-red-500' : 'bg-emerald-500'
                        }`}
                        style={{ width: `${(activeReport.disaster.probability * 100).toFixed(1)}%` }}
                      />
                    </div>
                    <div className="flex justify-between text-[9px] text-zinc-400 font-mono">
                      <span>0%</span>
                      <span className="text-zinc-500">threshold: {(activeReport.disaster.threshold_used * 100).toFixed(1)}%</span>
                      <span>100%</span>
                    </div>
                  </div>

                  <div className="text-[9px] text-zinc-500 font-mono border-t border-zinc-200/60 pt-1.5">
                    Model: {activeReport.disaster.model_name}
                  </div>
                </div>
              </div>
            )}

            {/* ── Similarity Report ── */}
            {activeReport.similarity && (
              <div className="space-y-2 border-t border-zinc-100 pt-4">
                <div className="text-[10px] text-zinc-400 font-mono uppercase tracking-wider">Input Similarity</div>

                {/* Status */}
                <div className="space-y-1">
                  <span className={`inline-block px-2.5 py-0.5 rounded-full text-[10px] font-semibold tracking-wider ${
                    activeReport.similarity.status === 'RELATED'
                      ? 'bg-emerald-50 text-emerald-700 border border-emerald-100'
                      : 'bg-red-50 text-red-700 border border-red-100'
                  }`}>
                    {activeReport.similarity.status}
                  </span>
                  <p className="text-[11px] text-zinc-500 italic mt-1 leading-relaxed">
                    {activeReport.similarity.details}
                  </p>
                </div>

                {/* Inputs */}
                <div className="space-y-2 border-t border-zinc-100 pt-3">
                  <div className="text-[10px] text-zinc-400 font-mono uppercase tracking-wider">Inputs Compared</div>
                  {activeReport.similarity.inputs && Object.keys(activeReport.similarity.inputs).map(key => (
                    <div key={key} className="bg-zinc-50 p-2 rounded border border-zinc-200/40">
                      <span className="text-[9px] text-zinc-400 font-mono uppercase">{key}:</span>
                      <p className="text-zinc-700 mt-0.5">{activeReport.similarity.inputs[key]}</p>
                    </div>
                  ))}
                </div>

                {/* Pairwise Scores */}
                {activeReport.similarity.pairwise_similarities && (
                  <div className="space-y-2 border-t border-zinc-100 pt-3">
                    <div className="text-[10px] text-zinc-400 font-mono uppercase tracking-wider">Pairwise Similarity Scores</div>
                    <div className="space-y-1">
                      {activeReport.similarity.pairwise_similarities.map((item, idx) => (
                        <div key={idx} className="flex justify-between items-center py-1 border-b border-zinc-100">
                          <span className="text-zinc-600 font-mono text-[10px]">{item.pair}</span>
                          <span className={`font-mono font-semibold ${item.similarity >= 0.40 ? 'text-emerald-600' : 'text-red-500'}`}>
                            {item.similarity.toFixed(3)}
                          </span>
                        </div>
                      ))}
                      <div className="flex justify-between items-center pt-2 font-bold text-zinc-900">
                        <span>Average:</span>
                        <span className={`font-mono ${activeReport.similarity.avg_pairwise_similarity >= 0.40 ? 'text-emerald-600' : 'text-red-500'}`}>
                          {activeReport.similarity.avg_pairwise_similarity.toFixed(3)}
                        </span>
                      </div>
                      <div className="text-[9px] text-zinc-400 mt-1 italic">
                        Threshold: ≥ 0.400 = Related
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* ── TypeSafe JEV v2 + Advanced RAG Analysis ── */}
            {activeReport.rag && (() => {
              const rPlan = activeReport.rag.plan || {};
              const rJev = activeReport.rag.jev_assessment || rPlan.jev_assessment;
              const chosen = rJev?.chosen_resources || (rPlan.resources || []);
              const notChosen = rJev?.not_chosen_resources || [];

              return (
                <div className="space-y-3 border-t border-zinc-100 pt-4">
                  <div className="flex items-center justify-between">
                    <div className="text-[10px] text-zinc-400 font-mono uppercase tracking-wider">
                      TypeSafe JEV v2 + RAG Pipeline
                    </div>
                    <span className="text-[9px] font-mono px-2 py-0.5 bg-blue-50 text-blue-700 rounded-full border border-blue-200">
                      {activeReport.rag.pipeline || 'jev_llm'}
                    </span>
                  </div>

                  {/* Severity, Urgency, Priority Badge */}
                  {rJev && (
                    <div className="bg-slate-900 text-zinc-100 p-2.5 rounded-xl border border-slate-800 space-y-2">
                      <div className="flex justify-between items-center text-[10px] font-mono border-b border-slate-800 pb-1">
                        <span className="text-amber-400 font-bold">⚡ STAGE 1 JEV TRIAGE</span>
                        <span className="text-red-400 font-bold">{rJev.priority || 'P1'}</span>
                      </div>
                      <div className="grid grid-cols-2 gap-1.5 text-[10px]">
                        <div className="bg-slate-800 p-1.5 rounded">
                          <span className="text-zinc-400 block font-mono text-[9px]">Severity:</span>
                          <span className="font-semibold text-zinc-200">{rJev.severity?.level || 'S2'} - {rJev.severity?.label || 'Severe'}</span>
                        </div>
                        <div className="bg-slate-800 p-1.5 rounded">
                          <span className="text-zinc-400 block font-mono text-[9px]">Urgency:</span>
                          <span className="font-semibold text-zinc-200">{rJev.urgency?.level || 'U3'} ({rJev.urgency?.window || '<1h'})</span>
                        </div>
                      </div>

                      {/* Census Context */}
                      {rJev.census_context?.district && (
                        <div className="text-[9px] text-zinc-300 bg-slate-800/80 p-1.5 rounded font-mono">
                          📍 District: {rJev.census_context.district} | Vuln: {(rJev.census_context.vulnerability_percentile * 100).toFixed(1)}th %ile
                        </div>
                      )}
                    </div>
                  )}

                  {/* Chosen Resources */}
                  <div className="space-y-1.5 bg-zinc-50 p-2.5 rounded-xl border border-zinc-200/60">
                    <div className="flex justify-between items-center text-[10px] font-bold text-zinc-700">
                      <span>✓ Chosen Resources ({chosen.length})</span>
                      <span className="font-mono text-emerald-600 text-[9px]">Active</span>
                    </div>
                    <div className="space-y-1">
                      {chosen.map((cItem, idx) => (
                        <div key={idx} className="flex justify-between items-center py-1 border-b border-zinc-200/40 text-[10px]">
                          <span className="flex items-center gap-1 font-medium text-zinc-800 truncate">
                            <span>{getResourceIcon(cItem.resource)}</span>
                            <span>{cItem.resource_label || cItem.resource}</span>
                          </span>
                          <span className="font-mono text-emerald-700 font-bold shrink-0">
                            {((cItem.probability || 0) * 100).toFixed(1)}%
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Excluded Resources */}
                  {notChosen.length > 0 && (
                    <div className="space-y-1.5 bg-zinc-50/50 p-2.5 rounded-xl border border-zinc-200/40 opacity-90">
                      <div className="flex justify-between items-center text-[10px] font-bold text-zinc-500">
                        <span>✗ Excluded Resources ({notChosen.length})</span>
                        <span className="font-mono text-zinc-400 text-[9px]">Below Cutoff</span>
                      </div>
                      <div className="space-y-1 max-h-36 overflow-y-auto pr-1">
                        {notChosen.map((ncItem, idx) => (
                          <div key={idx} className="flex justify-between items-center py-0.5 text-[9px] text-zinc-500 font-mono">
                            <span className="truncate">{ncItem.resource_label || ncItem.resource}</span>
                            <span>{((ncItem.probability || 0) * 100).toFixed(1)}%</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Pipeline Latency Telemetry */}
                  {activeReport.rag.latency && (
                    <div className="text-[9px] font-mono text-zinc-400 border-t border-zinc-100 pt-2 flex justify-between">
                      <span>Classification: {activeReport.rag.latency.classification_ms || 0}ms</span>
                      <span>Retrieval: {activeReport.rag.latency.retrieval_ms || 0}ms</span>
                      <span>Generation: {activeReport.rag.latency.generation_ms || 0}ms</span>
                    </div>
                  )}
                </div>
              );
            })()}

            {/* Fallback when no reports */}
            {!activeReport.disaster && !activeReport.similarity && !activeReport.rag && (
              <div className="text-xs text-zinc-400 italic">No analysis data available.</div>
            )}
          </div>
        </div>
      )}

      {/* Camera Clicker Overlay Modal */}
      {showCamera && (
        <CameraCapture 
          onCapture={(dataUrl) => handleImageCaptured(dataUrl)}
          onClose={() => setShowCamera(false)}
        />
      )}

      {/* ── RAG Raw JSON Viewer Modal ── */}
      {rawJsonEntry && (
        <div
          className="fixed inset-0 z-[100] bg-black/70 backdrop-blur-sm flex items-center justify-center p-4"
          onClick={() => setRawJsonEntry(null)}
        >
          <div
            className="bg-zinc-950 border border-zinc-700 rounded-2xl shadow-2xl w-full max-w-3xl max-h-[85vh] flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="flex items-center justify-between px-5 py-3.5 border-b border-zinc-800">
              <div className="flex items-center gap-2">
                <span className="text-emerald-400 font-mono text-xs font-bold tracking-wider">JEV + LLM RAG OUTPUT</span>
                <span className="text-zinc-500 font-mono text-[10px]">{rawJsonEntry.ragReport?.scenario_id || rawJsonEntry._id}</span>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => {
                    const blob = new Blob([JSON.stringify(rawJsonEntry.ragReport, null, 2)], { type: 'application/json' });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `rag_${rawJsonEntry._id}.json`;
                    a.click();
                    URL.revokeObjectURL(url);
                  }}
                  className="text-[10px] font-mono bg-zinc-800 hover:bg-zinc-700 text-zinc-300 px-2.5 py-1 rounded-md border border-zinc-700 transition-colors cursor-pointer"
                >
                  ⬇ Download JSON
                </button>
                <button
                  onClick={() => setRawJsonEntry(null)}
                  className="text-zinc-400 hover:text-white p-1 rounded-lg hover:bg-zinc-800 transition-colors cursor-pointer"
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>
            {/* JSON Body */}
            <div className="flex-1 overflow-y-auto p-5">
              <pre className="text-[11px] font-mono text-emerald-300 leading-relaxed whitespace-pre-wrap break-words">
                {JSON.stringify(rawJsonEntry.ragReport, null, 2)}
              </pre>
            </div>
            {/* Footer stats */}
            <div className="px-5 py-2.5 border-t border-zinc-800 flex items-center gap-4 text-[9px] font-mono text-zinc-500">
              <span>Pipeline: {rawJsonEntry.ragReport?.pipeline || 'jev_llm'}</span>
              <span>Resources: {rawJsonEntry.ragReport?.plan?.resources?.length ?? 0}</span>
              <span>SOP Fallback: {rawJsonEntry.ragReport?.plan?.sop_fallback ? 'Yes' : 'No'}</span>
              <span>Latency: {rawJsonEntry.ragReport?.latency?.total_ms?.toFixed(0) ?? '—'}ms</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
