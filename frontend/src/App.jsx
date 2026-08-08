import { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import { api } from './api';
import { useAuth } from './auth';
import Login from './components/Login';
import AdminDashboard from './components/AdminDashboard';
import './App.css';

function App() {
  const [conversations, setConversations] = useState([]);
  const [currentConversation, setCurrentConversation] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [stage1Results, setStage1Results] = useState(null);
  const [stage2Results, setStage2Results] = useState(null);
  const [stage3Result, setStage3Result] = useState(null);
  const [metadata, setMetadata] = useState(null);
  const [activeTab, setActiveTab] = useState(0);
  const [failedModels, setFailedModels] = useState({ stage1: [], stage2: [] });
  const [currentStage, setCurrentStage] = useState(null);
  const [view, setView] = useState('chat');
  const [uploadingPdf, setUploadingPdf] = useState(false);
  const [pdfData, setPdfData] = useState(null);
  const [pdfFilename, setPdfFilename] = useState(null);
  const fileInputRef = useRef(null);
  const messagesEndRef = useRef(null);

  const { user, logout, loading: authLoading } = useAuth();

  useEffect(() => {
    if (user) {
      loadConversations();
    }
  }, [user]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, stage1Results, stage2Results, stage3Result]);

  const loadConversations = async () => {
    try {
      const convs = await api.listConversations();
      // Filter out any conversations that don't belong to the current user
      // This is a safety measure in case the backend returns unexpected data
      setConversations(convs);
    } catch (error) {
      console.error('Failed to load conversations:', error);
      // If loading fails, clear conversations to prevent showing stale data
      setConversations([]);
    }
  };

  const createNewConversation = () => {
    setCurrentConversation(null);
    setMessages([]);
    resetCouncilState();
    clearPdfState();
  };

  const selectConversation = async (conv) => {
    try {
      const fullConv = await api.getConversation(conv.id);
      setCurrentConversation(fullConv);
      setMessages(fullConv.messages);
      resetCouncilState();
      clearPdfState();
    } catch (error) {
      console.error('Failed to load conversation:', error);
      // If access is denied (403), remove this conversation from the list
      if (error.status === 403 || (error.message && (error.message.includes('403') || error.message.includes('Access denied')))) {
        setConversations(conversations.filter(c => c.id !== conv.id));
        alert('You do not have access to this conversation. It has been removed from your list.');
      } else {
        alert('Failed to load conversation. Please try again.');
      }
    }
  };

  const deleteConversation = async (e, convId) => {
    e.stopPropagation(); // Prevent selecting the conversation
    
    if (!confirm('Delete this conversation?')) return;
    
    try {
      await api.deleteConversation(convId);
      setConversations(conversations.filter(c => c.id !== convId));
      
      // If we deleted the current conversation, clear it
      if (currentConversation?.id === convId) {
        setCurrentConversation(null);
        setMessages([]);
        resetCouncilState();
      }
    } catch (error) {
      console.error('Failed to delete conversation:', error);
      alert('Failed to delete conversation');
    }
  };

  const resetCouncilState = () => {
    setStage1Results(null);
    setStage2Results(null);
    setStage3Result(null);
    setMetadata(null);
    setFailedModels({ stage1: [], stage2: [] });
    setCurrentStage(null);
    setActiveTab(0);
  };

  const clearPdfState = () => {
    setPdfData(null);
    setPdfFilename(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handlePdfUpload = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;

    if (!file.name.toLowerCase().endsWith('.pdf')) {
      alert('Please select a PDF file');
      return;
    }

    setUploadingPdf(true);
    try {
      const result = await api.uploadPdf(file);
      setPdfData(result.base64);
      setPdfFilename(result.filename);
    } catch (error) {
      alert(`Failed to upload PDF: ${error.message}`);
    } finally {
      setUploadingPdf(false);
    }
  };

  const removePdf = () => {
    clearPdfState();
  };

  const sendMessage = async () => {
    if (!input.trim() || loading) return;

    let conversation = currentConversation;
    if (!conversation) {
      try {
        conversation = await api.createConversation();
        setConversations(prev => [conversation, ...prev]);
        setCurrentConversation(conversation);
        setMessages([]);
      } catch (error) {
        console.error('Failed to create conversation:', error);
        return;
      }
    }

    const userMessage = { role: 'user', content: input.trim() };
    const displayContent = pdfFilename
      ? `${input.trim()}\n\n📄 Attached: ${pdfFilename}`
      : input.trim();

    setMessages(prev => [...prev, { ...userMessage, content: displayContent }]);

    const messageContent = input.trim();
    const currentPdfData = pdfData;
    const currentPdfFilename = pdfFilename;

    setInput('');
    setLoading(true);
    resetCouncilState();
    clearPdfState();

    try {
      setCurrentStage(1);
      await api.sendMessageStream(
        conversation.id,
        messageContent,
        (data, failed, failures) => {
          setStage1Results(data);
          setFailedModels(prev => ({ ...prev, stage1: normalizeFailures(failures, failed) }));
          setCurrentStage(2);
        },
        (data, meta) => {
          setStage2Results(data);
          setMetadata(meta);
          setFailedModels(prev => ({
            ...prev,
            stage2: normalizeFailures(meta?.stage2_errors, meta?.stage2_failed),
          }));
          setCurrentStage(3);
        },
        (data) => {
          setStage3Result(data);
          setCurrentStage(null);
        },
        (title) => {
          setCurrentConversation(prev => prev ? { ...prev, title } : { ...conversation, title });
          loadConversations();
        },
        currentPdfData,
        currentPdfFilename
      );
    } catch (error) {
      console.error('Failed to send message:', error);
      const details = (error.failures || [])
        .map(f => `• ${getModelDisplayName(f.model)}: ${f.error || 'failed'}`)
        .join('\n');
      alert(details ? `${error.message}\n\n${details}` : `Error: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const KNOWN_PROVIDERS = ['openrouter', 'openai', 'google', 'anthropic', 'xai', 'mistral'];
  const getModelDisplayName = (modelId) => {
    if (!modelId) return 'Unknown';
    let name = modelId;
    // Strip known provider prefix (e.g. "openai:gpt-5.1" → "gpt-5.1")
    // But keep OpenRouter suffixes (e.g. "openai/gpt-5.1:online" stays intact)
    if (name.includes(':')) {
      const prefix = name.split(':')[0];
      if (KNOWN_PROVIDERS.includes(prefix)) {
        name = name.split(':').slice(1).join(':');
      }
    }
    if (name.includes('/')) name = name.split('/').pop();
    return name;
  };

  // Extract the final response text from various message formats
  const getAssistantResponseText = (content) => {
    if (!content) return 'No response';
    
    // If it's a string, return it directly
    if (typeof content === 'string') return content;
    
    // Try to get stage3 response (new format)
    if (content.stage3?.response) return content.stage3.response;
    
    // Try to get from nested structure
    if (content.response) return content.response;
    
    // If it's an array (old format), try to find the synthesis
    if (Array.isArray(content)) {
      const lastItem = content[content.length - 1];
      if (lastItem?.response) return lastItem.response;
    }
    
    return 'Response format not recognized';
  };

  // Check if a message has stage data (loaded from backend)
  const hasStageData = (msg) => {
    return msg.stage1 || msg.stage2 || msg.stage3;
  };

  // Failures arrive as objects {model, error, fallback_model, fallback_error};
  // older stored messages only have a list of model-name strings.
  const normalizeFailures = (...sources) => {
    const source = sources.find(s => Array.isArray(s) && s.length > 0) || [];
    return source
      .filter(Boolean)
      .map(entry => (typeof entry === 'string' ? { model: entry } : entry));
  };

  const renderFailedModelsBanner = (failures, totalCount) => {
    const entries = normalizeFailures(failures);
    if (entries.length === 0) return null;
    return (
      <div className="failed-models-banner">
        <div className="notice-title">
          &#9888; {entries.length} of {totalCount} model{totalCount !== 1 ? 's' : ''} failed
        </div>
        <ul className="notice-list">
          {entries.map((entry, idx) => (
            <li key={entry.model || idx}>
              <strong>{getModelDisplayName(entry.model)}</strong>
              {entry.error ? ` — ${entry.error}` : ''}
              {entry.fallback_model && (
                <div className="notice-sub">
                  Fallback {getModelDisplayName(entry.fallback_model)} also failed
                  {entry.fallback_error ? ` — ${entry.fallback_error}` : ''}
                </div>
              )}
            </li>
          ))}
        </ul>
      </div>
    );
  };

  // Models that answered only because their slot's fallback stepped in
  const renderFallbackBanner = (results) => {
    const used = (results || []).filter(r => r && r.fallback_used);
    if (used.length === 0) return null;
    return (
      <div className="fallback-models-banner">
        <div className="notice-title">
          &#8635; {used.length} model{used.length !== 1 ? 's' : ''} replaced by fallback
        </div>
        <ul className="notice-list">
          {used.map((entry, idx) => (
            <li key={entry.model || idx}>
              <strong>{getModelDisplayName(entry.primary_model)}</strong> failed
              {entry.primary_error ? ` — ${entry.primary_error}` : ''}
              <div className="notice-sub">
                Answered by {getModelDisplayName(entry.model)} instead
              </div>
            </li>
          ))}
        </ul>
      </div>
    );
  };

  const renderStageErrorBanner = (stage3) => {
    if (!stage3 || !stage3.error) return null;
    return (
      <div className="failed-models-banner">
        <div className="notice-title">
          &#9888; Chairman {getModelDisplayName(stage3.primary_model || stage3.model)} failed
        </div>
        <ul className="notice-list">
          <li>
            {stage3.error}
            {stage3.fallback_model && (
              <div className="notice-sub">
                Fallback {getModelDisplayName(stage3.fallback_model)} also failed
                {stage3.fallback_error ? ` — ${stage3.fallback_error}` : ''}
              </div>
            )}
          </li>
        </ul>
      </div>
    );
  };

  const renderModelTabLabel = (result) => (
    <>
      {getModelDisplayName(result.model)}
      {result.fallback_used && <span className="fallback-badge" title={`Fallback for ${result.primary_model}`}>&#8635;</span>}
    </>
  );

  // Render a loaded assistant message with stage data
  const renderLoadedAssistantMessage = (msg) => {
    // Ensure activeTab is within bounds for this message's stage1
    const safeActiveTab = msg.stage1 && Array.isArray(msg.stage1) && msg.stage1.length > 0
      ? Math.min(activeTab, msg.stage1.length - 1)
      : 0;

    return (
      <div className="message-content council-response">
        {(msg.stage1 || msg.stage2 || msg.stage3) && (
          <div className="copy-results-btn-container">
            <button 
              className="copy-results-btn" 
              onClick={() => copyMessageResults(msg)}
              title="Copy all results to clipboard"
            >
              📋 Copy Results
            </button>
          </div>
        )}
        {msg.stage1 && Array.isArray(msg.stage1) && msg.stage1.length > 0 && (
          <div className="stage-section">
            <h3>Stage 1: Individual Responses</h3>
            {renderFailedModelsBanner(
              normalizeFailures(msg.metadata?.stage1_errors, msg.metadata?.stage1_failed),
              msg.stage1.length + (msg.metadata?.stage1_failed?.length || 0)
            )}
            {renderFallbackBanner(msg.stage1)}
            <div className="tabs">
              {msg.stage1.map((result, idx) => (
                <button
                  key={result.model || idx}
                  className={`tab ${safeActiveTab === idx ? 'active' : ''}`}
                  onClick={() => setActiveTab(idx)}
                >
                  {renderModelTabLabel(result)}
                </button>
              ))}
              {normalizeFailures(msg.metadata?.stage1_errors, msg.metadata?.stage1_failed).map((entry, idx) => (
                <span key={entry.model || idx} className="tab failed" title={entry.error || 'Failed'}>
                  {getModelDisplayName(entry.model)}
                </span>
              ))}
            </div>
            <div className="tab-content">
              <ReactMarkdown>{msg.stage1[safeActiveTab]?.response || 'No response'}</ReactMarkdown>
            </div>
          </div>
        )}
        {msg.stage2 && Array.isArray(msg.stage2) && msg.stage2.length > 0 && (
          <div className="stage-section">
            <h3>Stage 2: Peer Reviews</h3>
            {renderFailedModelsBanner(
              normalizeFailures(msg.metadata?.stage2_errors, msg.metadata?.stage2_failed),
              msg.stage2.length + (msg.metadata?.stage2_failed?.length || 0)
            )}
            {renderFallbackBanner(msg.stage2)}
            {msg.metadata?.aggregate_rankings && Array.isArray(msg.metadata.aggregate_rankings) && msg.metadata.aggregate_rankings.length > 0 && (
              <div className="rankings">
                <h4>Aggregate Rankings</h4>
                <ol>
                  {msg.metadata.aggregate_rankings.map((item, idx) => (
                    <li key={item.model || idx}>
                      <strong>{getModelDisplayName(item.model)}</strong>: {item.average_rank?.toFixed(2) || 'N/A'} avg rank
                    </li>
                  ))}
                </ol>
              </div>
            )}
          </div>
        )}
        {msg.stage3 && (
          <div className="stage-section final-answer">
            <h3>Stage 3: Final Council Answer</h3>
            {renderStageErrorBanner(msg.stage3)}
            {msg.stage3.fallback_used && (
              <div className="fallback-models-banner">
                <div className="notice-title">
                  &#8635; Chairman {getModelDisplayName(msg.stage3.primary_model)} failed
                  {msg.stage3.primary_error ? ` — ${msg.stage3.primary_error}` : ''}
                </div>
              </div>
            )}
            {msg.stage3.model && (
              <div className="chairman-badge">
                Chairman: {getModelDisplayName(msg.stage3.model)}
              </div>
            )}
            <ReactMarkdown>{msg.stage3.response || 'No response'}</ReactMarkdown>
          </div>
        )}
      </div>
    );
  };

  const renderStage1 = () => {
    if (!stage1Results || !Array.isArray(stage1Results)) return null;
    // Still render when every model failed — the banner is the whole point then
    if (stage1Results.length === 0 && failedModels.stage1.length === 0) return null;

    return (
      <div className="stage-section">
        <div className="stage-header">
          <h3>Stage 1: Individual Responses</h3>
        </div>
        {renderFailedModelsBanner(
          failedModels.stage1,
          stage1Results.length + failedModels.stage1.length
        )}
        {renderFallbackBanner(stage1Results)}
        <div className="tabs">
          {stage1Results.map((result, idx) => (
            <button
              key={result.model || idx}
              className={`tab ${activeTab === idx ? 'active' : ''}`}
              onClick={() => setActiveTab(idx)}
            >
              {renderModelTabLabel(result)}
            </button>
          ))}
          {failedModels.stage1.map((entry, idx) => (
            <span key={entry.model || idx} className="tab failed" title={entry.error || 'Failed'}>
              {getModelDisplayName(entry.model)}
            </span>
          ))}
        </div>
        <div className="tab-content">
          <ReactMarkdown>{stage1Results[activeTab]?.response || 'No response'}</ReactMarkdown>
        </div>
      </div>
    );
  };

  const renderStage2 = () => {
    if (!stage2Results || !metadata) return null;

    return (
      <div className="stage-section">
        <div className="stage-header">
          <h3>Stage 2: Peer Reviews</h3>
        </div>
        {renderFailedModelsBanner(
          failedModels.stage2,
          stage2Results.length + failedModels.stage2.length
        )}
        {renderFallbackBanner(stage2Results)}
        {metadata.aggregate_rankings && Array.isArray(metadata.aggregate_rankings) && (
          <div className="rankings">
            <h4>Aggregate Rankings</h4>
            <ol>
              {metadata.aggregate_rankings.map((item, idx) => (
                <li key={item.model || idx}>
                  <strong>{getModelDisplayName(item.model)}</strong>: {item.average_rank?.toFixed(2) || 'N/A'} avg rank
                </li>
              ))}
            </ol>
          </div>
        )}
      </div>
    );
  };

  const renderStage3 = () => {
    if (!stage3Result) return null;

    return (
      <div className="stage-section final-answer">
        <div className="stage-header">
          <h3>Stage 3: Final Council Answer</h3>
        </div>
        {renderStageErrorBanner(stage3Result)}
        {stage3Result.fallback_used && (
          <div className="fallback-models-banner">
            <div className="notice-title">
              &#8635; Chairman {getModelDisplayName(stage3Result.primary_model)} failed
              {stage3Result.primary_error ? ` — ${stage3Result.primary_error}` : ''}
            </div>
          </div>
        )}
        <div className="chairman-badge">
          Chairman: {getModelDisplayName(stage3Result.model)}
        </div>
        <ReactMarkdown>{stage3Result.response || 'No response'}</ReactMarkdown>
      </div>
    );
  };

  // Format and copy stage results to clipboard
  const copyResultsToClipboard = (stage1Data, stage2Data, stage3Data, metadataData) => {
    let text = '';

    // Stage 1: Individual Responses
    if (stage1Data && Array.isArray(stage1Data) && stage1Data.length > 0) {
      text += '=== Stage 1: Individual Responses ===\n\n';
      stage1Data.forEach((result, idx) => {
        text += `--- ${getModelDisplayName(result.model)} ---\n`;
        text += `${result.response || 'No response'}\n\n`;
      });
    }

    // Stage 2: Peer Reviews
    if (stage2Data && Array.isArray(stage2Data) && stage2Data.length > 0) {
      text += '=== Stage 2: Peer Reviews ===\n\n';
      if (metadataData?.aggregate_rankings && Array.isArray(metadataData.aggregate_rankings)) {
        text += 'Aggregate Rankings:\n';
        metadataData.aggregate_rankings.forEach((item, idx) => {
          text += `${idx + 1}. ${getModelDisplayName(item.model)}: ${item.average_rank?.toFixed(2) || 'N/A'} avg rank\n`;
        });
        text += '\n';
      }
    }

    // Stage 3: Final Council Answer
    if (stage3Data) {
      text += '=== Stage 3: Final Council Answer ===\n\n';
      if (stage3Data.model) {
        text += `Chairman: ${getModelDisplayName(stage3Data.model)}\n\n`;
      }
      text += `${stage3Data.response || 'No response'}\n`;
    }

    // Check if we have any data to copy
    if (!text.trim()) {
      alert('No results available to copy');
      return;
    }

    // Copy to clipboard
    navigator.clipboard.writeText(text).then(() => {
      alert('Results copied to clipboard!');
    }).catch((err) => {
      console.error('Failed to copy to clipboard:', err);
      alert('Failed to copy to clipboard');
    });
  };

  // Copy current streaming results
  const copyCurrentResults = () => {
    copyResultsToClipboard(stage1Results, stage2Results, stage3Result, metadata);
  };

  // Copy results from a loaded message
  const copyMessageResults = (msg) => {
    copyResultsToClipboard(msg.stage1, msg.stage2, msg.stage3, msg.metadata);
  };

  const renderLoadingStage = () => {
    if (!currentStage) return null;

    const stageMessages = {
      1: pdfFilename 
        ? `Analyzing PDF "${pdfFilename}" and gathering opinions...`
        : 'Gathering individual opinions from council members...',
      2: 'Council members are reviewing each other\'s responses...',
      3: 'Chairman is synthesizing the final response...',
    };

    return (
      <div className="loading-stage">
        <div className="spinner"></div>
        <p>{stageMessages[currentStage]}</p>
      </div>
    );
  };

  // Show login if not authenticated
  if (authLoading) {
    return (
      <div className="app">
        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
          <div className="spinner"></div>
        </div>
      </div>
    );
  }

  if (!user) {
    return <Login />;
  }

  return (
    <div className="app">
      <aside className="sidebar">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <h1>XQT5AIs</h1>
          <button 
            className="logout-btn" 
            onClick={logout}
            title="Logout"
          >
            Logout
          </button>
        </div>
        <div style={{ fontSize: '12px', color: '#888', marginBottom: '16px', paddingBottom: '16px', borderBottom: '1px solid #444' }}>
          {user.username}
        </div>
        {user?.is_admin && (
          <button
            className={`admin-toggle-btn ${view === 'admin' ? 'active' : ''}`}
            onClick={() => setView(view === 'admin' ? 'chat' : 'admin')}
          >
            {view === 'admin' ? 'Back to Chat' : 'Admin'}
          </button>
        )}
        <button className="new-chat-btn" onClick={createNewConversation}>
          + New Conversation
        </button>
        <div className="conversation-list">
          {conversations.length === 0 ? (
            <p className="no-conversations">No conversations yet</p>
          ) : (
            conversations.map((conv) => (
              <div
                key={conv.id}
                className={`conversation-item ${currentConversation?.id === conv.id ? 'active' : ''}`}
                onClick={() => selectConversation(conv)}
              >
                <span className="conversation-title">{conv.title}</span>
                <span className="message-count">{conv.message_count} messages</span>
                <button 
                  className="delete-btn"
                  onClick={(e) => deleteConversation(e, conv.id)}
                  title="Delete conversation"
                >
                  ×
                </button>
              </div>
            ))
          )}
        </div>
      </aside>

      <main className="chat-area">
        {view === 'admin' ? (
          <AdminDashboard />
        ) : !currentConversation ? (
          <div className="welcome-new">
            <div className="welcome-header">
              <h2>Welcome to XQT5AIs</h2>
              <p>Create a new conversation to get started</p>
            </div>
            <div className="welcome-input-area">
              {pdfFilename && (
                <div className="pdf-badge">
                  <span>📄 {pdfFilename}</span>
                  <button onClick={removePdf} className="remove-pdf" title="Remove PDF">×</button>
                </div>
              )}
              <div className="welcome-input-row">
                <input
                  type="file"
                  accept=".pdf"
                  onChange={handlePdfUpload}
                  ref={fileInputRef}
                  style={{ display: 'none' }}
                  id="pdf-upload-welcome"
                />
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyPress={handleKeyPress}
                  placeholder={pdfFilename ? "Ask a question about the PDF..." : "Ask the council a question..."}
                  disabled={loading}
                  rows={5}
                  className="welcome-textarea"
                />
              </div>
              <div className="welcome-actions">
                <button
                  className="upload-btn"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={loading || uploadingPdf}
                  title="Upload PDF"
                >
                  {uploadingPdf ? '⏳' : '📎'}
                </button>
                <button
                  className="welcome-send-btn"
                  onClick={sendMessage}
                  disabled={loading || !input.trim()}
                >
                  {loading ? '...' : 'Ask the Council →'}
                </button>
              </div>
              <p className="pdf-hint">
                {pdfFilename
                  ? "PDF will be analyzed by OpenRouter's native PDF processing"
                  : "Tip: Upload a PDF to have the council analyze it"}
              </p>
            </div>
          </div>
        ) : (
          <>
            <div className="messages">
              {messages.map((msg, idx) => (
                <div key={idx} className={`message ${msg.role}`}>
                  <div className="message-header">
                    {msg.role === 'user' ? 'YOU' : 'XQT5AIs'}
                  </div>
                  {msg.role === 'user' ? (
                    <div className="message-content">
                      <p style={{ whiteSpace: 'pre-wrap' }}>{msg.content}</p>
                    </div>
                  ) : hasStageData(msg) ? (
                    renderLoadedAssistantMessage(msg)
                  ) : (
                    <div className="message-content">
                      <ReactMarkdown>{getAssistantResponseText(msg.content)}</ReactMarkdown>
                    </div>
                  )}
                </div>
              ))}

              {(stage1Results || stage2Results || stage3Result || currentStage) && (
                <div className="message assistant">
                  <div className="message-header">XQT5AIs</div>
                  <div className="message-content council-response">
                    {(stage1Results || stage2Results || stage3Result) && (
                      <div className="copy-results-btn-container">
                        <button 
                          className="copy-results-btn" 
                          onClick={copyCurrentResults}
                          title="Copy all results to clipboard"
                        >
                          📋 Copy Results
                        </button>
                      </div>
                    )}
                    {renderLoadingStage()}
                    {renderStage1()}
                    {renderStage2()}
                    {renderStage3()}
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>

            <div className="input-area">
              {pdfFilename && (
                <div className="pdf-badge">
                  <span>📄 {pdfFilename}</span>
                  <button onClick={removePdf} className="remove-pdf" title="Remove PDF">×</button>
                </div>
              )}
              <div className="input-row">
                <input
                  type="file"
                  accept=".pdf"
                  onChange={handlePdfUpload}
                  ref={fileInputRef}
                  style={{ display: 'none' }}
                  id="pdf-upload"
                />
                <button
                  className="upload-btn"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={loading || uploadingPdf}
                  title="Upload PDF (processed by OpenRouter)"
                >
                  {uploadingPdf ? '⏳' : '📎'}
                </button>
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyPress={handleKeyPress}
                  placeholder={pdfFilename ? "Ask a question about the PDF..." : "Ask the council a question..."}
                  disabled={loading}
                  rows={1}
                />
                <button
                  className="send-btn"
                  onClick={sendMessage}
                  disabled={loading || !input.trim()}
                >
                  {loading ? '...' : '→'}
                </button>
              </div>
              <p className="pdf-hint">
                {pdfFilename 
                  ? "PDF will be analyzed by OpenRouter's native PDF processing"
                  : "Tip: Upload a PDF to have the council analyze it"}
              </p>
            </div>
          </>
        )}
      </main>
    </div>
  );
}

export default App;
