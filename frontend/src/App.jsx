import { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import { api } from './api';
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
  const [currentStage, setCurrentStage] = useState(null);
  const [uploadingPdf, setUploadingPdf] = useState(false);
  const [pdfData, setPdfData] = useState(null);
  const [pdfFilename, setPdfFilename] = useState(null);
  const fileInputRef = useRef(null);
  const messagesEndRef = useRef(null);

  useEffect(() => {
    loadConversations();
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, stage1Results, stage2Results, stage3Result]);

  const loadConversations = async () => {
    try {
      const convs = await api.listConversations();
      setConversations(convs);
    } catch (error) {
      console.error('Failed to load conversations:', error);
    }
  };

  const createNewConversation = async () => {
    try {
      const conv = await api.createConversation();
      setConversations([conv, ...conversations]);
      setCurrentConversation(conv);
      setMessages([]);
      resetCouncilState();
      clearPdfState();
    } catch (error) {
      console.error('Failed to create conversation:', error);
    }
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
    if (!input.trim() || !currentConversation || loading) return;

    const userMessage = { role: 'user', content: input.trim() };
    const displayContent = pdfFilename 
      ? `${input.trim()}\n\n📄 Attached: ${pdfFilename}`
      : input.trim();
    
    setMessages([...messages, { ...userMessage, content: displayContent }]);
    
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
        currentConversation.id,
        messageContent,
        (data) => {
          setStage1Results(data);
          setCurrentStage(2);
        },
        (data, meta) => {
          setStage2Results(data);
          setMetadata(meta);
          setCurrentStage(3);
        },
        (data) => {
          setStage3Result(data);
          setCurrentStage(null);
        },
        (title) => {
          setCurrentConversation({ ...currentConversation, title });
          loadConversations();
        },
        currentPdfData,
        currentPdfFilename
      );
    } catch (error) {
      console.error('Failed to send message:', error);
      alert(`Error: ${error.message}`);
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

  const getModelDisplayName = (modelId) => {
    if (!modelId) return 'Unknown';
    const parts = modelId.split('/');
    return parts[parts.length - 1];
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

  // Render a loaded assistant message with stage data
  const renderLoadedAssistantMessage = (msg) => {
    // Ensure activeTab is within bounds for this message's stage1
    const safeActiveTab = msg.stage1 && Array.isArray(msg.stage1) && msg.stage1.length > 0
      ? Math.min(activeTab, msg.stage1.length - 1)
      : 0;

    return (
      <div className="message-content council-response">
        {msg.stage1 && Array.isArray(msg.stage1) && msg.stage1.length > 0 && (
          <div className="stage-section">
            <h3>Stage 1: Individual Responses</h3>
            <div className="tabs">
              {msg.stage1.map((result, idx) => (
                <button
                  key={result.model || idx}
                  className={`tab ${safeActiveTab === idx ? 'active' : ''}`}
                  onClick={() => setActiveTab(idx)}
                >
                  {getModelDisplayName(result.model)}
                </button>
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
    if (!stage1Results || !Array.isArray(stage1Results) || stage1Results.length === 0) return null;

    return (
      <div className="stage-section">
        <h3>Stage 1: Individual Responses</h3>
        <div className="tabs">
          {stage1Results.map((result, idx) => (
            <button
              key={result.model || idx}
              className={`tab ${activeTab === idx ? 'active' : ''}`}
              onClick={() => setActiveTab(idx)}
            >
              {getModelDisplayName(result.model)}
            </button>
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
        <h3>Stage 2: Peer Reviews</h3>
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
        <h3>Stage 3: Final Council Answer</h3>
        <div className="chairman-badge">
          Chairman: {getModelDisplayName(stage3Result.model)}
        </div>
        <ReactMarkdown>{stage3Result.response || 'No response'}</ReactMarkdown>
      </div>
    );
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

  return (
    <div className="app">
      <aside className="sidebar">
        <h1>LLM Council</h1>
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
        {!currentConversation ? (
          <div className="welcome">
            <h2>Welcome to LLM Council</h2>
            <p>Create a new conversation to get started</p>
          </div>
        ) : (
          <>
            <div className="messages">
              {messages.map((msg, idx) => (
                <div key={idx} className={`message ${msg.role}`}>
                  <div className="message-header">
                    {msg.role === 'user' ? 'YOU' : 'LLM COUNCIL'}
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
                  <div className="message-header">LLM COUNCIL</div>
                  <div className="message-content council-response">
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
