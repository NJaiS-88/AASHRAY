with open('frontend/src/pages/Dashboard.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. State and handleClearConversations
t1 = """  const [conversations, setConversations] = useState([]);
  const [activeConversationId, setActiveConversationId] = useState(null);"""

r1 = """  const [conversations, setConversations] = useState([]);
  const [activeConversationId, setActiveConversationId] = useState(null);
  const [showClearModal, setShowClearModal] = useState(false);
  const [isClearing, setIsClearing] = useState(false);
  const [clearError, setClearError] = useState(null);

  const handleClearConversations = async () => {
    try {
      setIsClearing(true);
      setClearError(null);
      const res = await axiosClient.delete('/entries');
      if (res.data?.status === 'success' || res.status === 200) {
        setConversations([]);
        setEntries([]);
        setActiveConversationId(null);
        setShowClearModal(false);
      } else {
        setClearError(res.data?.message || 'Failed to clear conversations');
      }
    } catch (err) {
      console.error('Failed to clear conversations:', err);
      setClearError(err.response?.data?.message || err.message || 'Failed to clear conversations');
    } finally {
      setIsClearing(false);
    }
  };"""

assert t1 in content, "t1 not found in Dashboard.jsx"
content = content.replace(t1, r1, 1)

# 2. Sidebar Header
t2 = """        {/* Conversation Threads List */}
        <div className="flex-1 overflow-y-auto p-3 space-y-1.5">
          <div className="text-[10px] font-bold uppercase tracking-wider px-2 py-1" style={{ color: 'var(--muted-text)' }}>
            Conversations ({conversations.length})
          </div>"""

r2 = """        {/* Conversation Threads List */}
        <div className="flex-1 overflow-y-auto p-3 space-y-1.5">
          <div className="flex items-center justify-between px-2 py-1">
            <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--muted-text)' }}>
              Conversations ({conversations.length})
            </span>
            {conversations.length > 0 && (
              <button
                type="button"
                onClick={() => {
                  setClearError(null);
                  setShowClearModal(true);
                }}
                title="Clear conversations"
                className="text-[10px] font-semibold flex items-center gap-1 px-1.5 py-0.5 rounded transition-colors text-zinc-400 hover:text-rose-600 hover:bg-rose-50 cursor-pointer"
              >
                <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
                <span>Clear</span>
              </button>
            )}
          </div>"""

assert t2 in content, "t2 not found in Dashboard.jsx"
content = content.replace(t2, r2, 1)

# 3. Confirmation Modal before RAG modal
t3 = """      {/* ── RAG Raw JSON Viewer Modal ── */}"""

r3 = """      {/* ── Clear Conversations Confirmation Modal ── */}
      {showClearModal && (
        <div
          className="fixed inset-0 z-[100] bg-black/50 backdrop-blur-xs flex items-center justify-center p-4 animate-in fade-in duration-150"
          onClick={() => !isClearing && setShowClearModal(false)}
        >
          <div
            className="bg-white rounded-2xl shadow-xl w-full max-w-md border overflow-hidden flex flex-col"
            style={{ borderColor: 'var(--border)' }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="p-5 pb-3 flex items-start gap-3.5">
              <div className="w-10 h-10 rounded-full flex items-center justify-center shrink-0 bg-rose-50 text-rose-600 border border-rose-100">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </div>
              <div className="flex-1">
                <h3 className="font-bold text-sm" style={{ color: 'var(--heading-text)', fontFamily: 'var(--font-headline)' }}>
                  Clear Conversation History?
                </h3>
                <p className="text-xs mt-1.5 leading-relaxed" style={{ color: 'var(--body-text)' }}>
                  This will remove your past chat history and user-facing emergency reports from this conversation list.
                </p>
                <div className="mt-3 p-2.5 rounded-lg bg-indigo-50/70 border border-indigo-100/80 text-[11px] text-indigo-900 leading-normal">
                  <strong className="font-semibold">Note:</strong> Active dispatches and operational emergency records remain safely on file with emergency dispatch services for coordination.
                </div>
                {clearError && (
                  <div className="mt-2.5 p-2 rounded bg-rose-50 border border-rose-200 text-rose-700 text-xs">
                    {clearError}
                  </div>
                )}
              </div>
            </div>

            {/* Modal Actions */}
            <div className="p-4 pt-2 bg-zinc-50 border-t flex items-center justify-end gap-2" style={{ borderColor: 'var(--border)' }}>
              <button
                type="button"
                disabled={isClearing}
                onClick={() => setShowClearModal(false)}
                className="px-3.5 py-1.5 rounded-lg text-xs font-semibold text-zinc-600 hover:bg-zinc-200/60 transition-colors cursor-pointer disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={isClearing}
                onClick={handleClearConversations}
                className="px-3.5 py-1.5 rounded-lg text-xs font-semibold text-white bg-rose-600 hover:bg-rose-700 transition-colors shadow-sm flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
              >
                {isClearing ? (
                  <>
                    <svg className="animate-spin w-3.5 h-3.5 text-white" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path>
                    </svg>
                    <span>Clearing...</span>
                  </>
                ) : (
                  <span>Clear All Conversations</span>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── RAG Raw JSON Viewer Modal ── */}"""

assert t3 in content, "t3 not found in Dashboard.jsx"
content = content.replace(t3, r3, 1)

with open('frontend/src/pages/Dashboard.jsx', 'w', encoding='utf-8') as f:
    f.write(content)

print("Successfully updated frontend/src/pages/Dashboard.jsx")
