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

  const getResourceIcon = (resource) => {
    switch (resource?.toLowerCase()) {
      case 'water': return '💧';
      case 'food': return '🥫';
      case 'shelter': return '⛺';
      case 'clothing': return '👕';
      case 'money': return '💰';
      case 'medical_help': return '🩺';
      case 'medical_products': return '💊';
      case 'search_and_rescue': return '🛟';
      case 'tools': return '🛠️';
      default: return '📦';
    }
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

    try {
      let finalAudioText = transcribedAudioText;
      let finalImageCaption = imageCaptionText;

      // If user hit submit while audio is still processing, wait for it automatically!
      if (audioPromiseRef.current) {
        const result = await audioPromiseRef.current;
        if (result) finalAudioText = result;
      }

      // If user hit submit while image is still processing, wait for it automatically!
      if (imagePromiseRef.current) {
        const result = await imagePromiseRef.current;
        if (result) finalImageCaption = result;
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
          <button 
            onClick={() => setSidebarOpen(false)}
            className="p-1.5 hover:bg-zinc-100 rounded-lg text-zinc-500 hover:text-zinc-900 md:hidden"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
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

                        {/* ── TypeSafe JEV + LLM RAG Operational Dispatch Plan ── */}
                        {entry.ragReport?.plan ? (
                          <div className="mt-3 p-3 bg-red-50/70 border border-red-200/80 rounded-xl space-y-2.5 text-left">
                            <div className="flex items-center justify-between">
                              <div className="flex items-center gap-1.5 text-red-700 font-semibold text-xs tracking-wide">
                                <span className="w-2 h-2 rounded-full bg-red-600 animate-pulse" />
                                🛡️ Crisis Operations Dispatch Plan (JEV + LLM RAG)
                              </div>
                              <div className="flex items-center gap-1.5">
                                <span className="text-[9px] font-mono bg-red-100 text-red-800 px-2 py-0.5 rounded-full border border-red-200">
                                  {entry.ragReport.pipeline || 'jev_llm'}
                                </span>
                                <button
                                  type="button"
                                  onClick={() => setRawJsonEntry(entry)}
                                  className="text-[9px] font-mono bg-zinc-800 hover:bg-zinc-700 text-white px-2 py-0.5 rounded-full border border-zinc-700 transition-colors cursor-pointer"
                                  title="View full RAG output as JSON"
                                >
                                  {'{ } JSON'}
                                </button>
                              </div>
                            </div>

                            {/* Operational Synthesis Report */}
                            <p className="text-zinc-800 text-xs leading-relaxed bg-white/90 p-2.5 rounded-lg border border-red-100 font-sans shadow-sm">
                              {entry.ragReport.plan.report}
                            </p>

                            {/* Required Resource pills & field instructions */}
                            {entry.ragReport.plan.resources?.length > 0 && (
                              <div className="space-y-2 pt-1">
                                <div className="text-[10px] font-mono text-zinc-500 uppercase tracking-wider">
                                  Required Relief Resources & Field SOPs:
                                </div>
                                <div className="space-y-2">
                                  {entry.ragReport.plan.resources.map((resItem, rIdx) => (
                                    <div key={rIdx} className="bg-white border border-zinc-200/80 rounded-lg p-2.5 text-xs space-y-1.5 shadow-xs">
                                      <div className="flex items-center justify-between">
                                        <span className="font-semibold text-zinc-900 capitalize flex items-center gap-1.5">
                                          <span>{getResourceIcon(resItem.resource)}</span>
                                          <span>{resItem.resource_label || resItem.resource.replace(/_/g, ' ')}</span>
                                        </span>
                                        <div className="flex items-center gap-1">
                                          {resItem.probability != null && (
                                            <span className="text-[9px] font-mono text-zinc-400">
                                              {(resItem.probability * 100).toFixed(0)}%
                                            </span>
                                          )}
                                          <span className={`text-[9px] px-2 py-0.5 rounded font-mono font-medium ${
                                            resItem.evidence_sufficient 
                                              ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' 
                                              : 'bg-amber-50 text-amber-700 border border-amber-200'
                                          }`}>
                                            {resItem.evidence_sufficient ? '✓ Verified SOP' : '⚠ Protocol Guidelines'}
                                          </span>
                                        </div>
                                      </div>

                                      <ul className="list-disc list-inside text-zinc-700 text-[11px] space-y-0.5 pl-1 leading-relaxed">
                                        {resItem.instructions?.map((inst, iIdx) => (
                                          <li key={iIdx}>{inst}</li>
                                        ))}
                                      </ul>

                                      {resItem.sources?.length > 0 && (
                                        <div className="flex flex-wrap items-center gap-1 pt-1.5 border-t border-zinc-100 text-[9px] font-mono text-zinc-400">
                                          <span>Official Citations:</span>
                                          {resItem.sources.map((src, sIdx) => (
                                            <span key={sIdx} className="bg-zinc-50 text-zinc-600 border border-zinc-200/60 px-1.5 py-0.5 rounded">
                                              📄 {src.file} (p. {src.page})
                                            </span>
                                          ))}
                                        </div>
                                      )}
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )}
                          </div>
                        ) : entry.disasterReport?.label === 'disaster' && (
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
                        )}
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
                disabled={isSubmitting || !isOnline || (!text.trim() && !text2.trim() && !text3.trim() && !imageUrl && !audioBlob)}
                className="p-2 bg-zinc-900 text-white rounded-xl hover:bg-zinc-800 disabled:opacity-30 disabled:bg-zinc-200 disabled:text-zinc-400 transition-all shadow-sm"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 10l7-7m0 0l7 7m-7-7v18" />
                </svg>
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

            {/* ── TypeSafe JEV + LLM RAG Analysis ── */}
            {activeReport.rag && (
              <div className="space-y-3 border-t border-zinc-100 pt-4">
                <div className="flex items-center justify-between">
                  <div className="text-[10px] text-zinc-400 font-mono uppercase tracking-wider">
                    JEV + LLM RAG Pipeline
                  </div>
                  <span className="text-[9px] font-mono px-2 py-0.5 bg-blue-50 text-blue-700 rounded-full border border-blue-200">
                    {activeReport.rag.pipeline || 'jev_llm'}
                  </span>
                </div>

                {/* Stage 1: JEV Resource Probabilities */}
                {activeReport.rag.stage_1_probabilities && (
                  <div className="space-y-2 bg-zinc-50 p-2.5 rounded-xl border border-zinc-200/60">
                    <div className="flex justify-between items-center text-[10px] font-bold text-zinc-700">
                      <span>TypeSafe JEV Probabilities</span>
                      <span className="font-mono text-zinc-400 text-[9px]">Threshold: 15.0%</span>
                    </div>
                    <div className="space-y-1.5">
                      {Object.entries(activeReport.rag.stage_1_probabilities).map(([resKey, prob]) => {
                        const isReq = prob >= 0.15;
                        return (
                          <div key={resKey} className="space-y-0.5">
                            <div className="flex justify-between text-[10px]">
                              <span className={`capitalize flex items-center gap-1 ${isReq ? 'font-semibold text-zinc-900' : 'text-zinc-500'}`}>
                                <span>{getResourceIcon(resKey)}</span>
                                <span>{resKey.replace(/_/g, ' ')}</span>
                              </span>
                              <span className={`font-mono text-[9px] ${isReq ? 'text-red-600 font-bold' : 'text-zinc-400'}`}>
                                {(prob * 100).toFixed(1)}% {isReq ? 'REQUIRED' : ''}
                              </span>
                            </div>
                            <div className="w-full bg-zinc-200 rounded-full h-1 overflow-hidden">
                              <div
                                className={`h-full rounded-full transition-all ${isReq ? 'bg-red-500' : 'bg-zinc-400'}`}
                                style={{ width: `${Math.min(100, Math.max(2, prob * 100))}%` }}
                              />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* Stage 2 & 3: Retrieved Sources & Operational Plan */}
                {activeReport.rag.plan && (
                  <div className="space-y-2 bg-zinc-50 p-2.5 rounded-xl border border-zinc-200/60">
                    <div className="text-[10px] font-bold text-zinc-700">
                      Synthesized Dispatch Summary
                    </div>
                    <p className="text-[11px] text-zinc-600 leading-relaxed italic">
                      "{activeReport.rag.plan.report}"
                    </p>

                    {/* Source Citations */}
                    {activeReport.rag.plan.resources?.some(r => r.sources?.length > 0) && (
                      <div className="pt-2 border-t border-zinc-200/50 space-y-1">
                        <span className="text-[9px] font-mono text-zinc-400 uppercase">Authoritative NDMA Citations:</span>
                        <div className="flex flex-wrap gap-1">
                          {activeReport.rag.plan.resources.flatMap(r => r.sources || []).filter((s, idx, arr) => 
                            arr.findIndex(x => x.file === s.file && x.page === s.page) === idx
                          ).map((src, sIdx) => (
                            <span key={sIdx} className="bg-white border border-zinc-200 text-zinc-700 text-[9px] font-mono px-1.5 py-0.5 rounded">
                              📄 {src.file} (p. {src.page})
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
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
            )}

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
