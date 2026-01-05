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
    const parts = modelId.split('/');
    return parts[parts.length - 1];
  };

  const renderStage1 = () => {
    if (!stage1Results) return null;
    const models = Object.keys(stage1Results);

    return (
      <div className="stage-section">
        <h3>Stage 1: Individual Responses</h3>
        <div className="tabs">
          {models.map((model, idx) => (
            <button
              key={model}
              className={`tab ${activeTab === idx ? 'active' : ''}`}
              onClick={() => setActiveTab(idx)}
            >
              {getModelDisplayName(model)}
            </button>
          ))}
        </div>
        <div className="tab-content">
          <ReactMarkdown>{stage1Results[models[activeTab]]}</ReactMarkdown>
        </div>
      </div>
    );
  };

  const renderStage2 = () => {
    if (!stage2Results || !metadata) return null;

    return (
      <div className="stage-section">
        <h3>Stage 2: Peer Reviews</h3>
        {metadata.aggregate_rankings && (
          <div className="rankings">
            <h4>Aggregate Rankings</h4>
            <ol>
              {metadata.aggregate_rankings.map(([model, score]) => (
                <li key={model}>
                  <strong>{getModelDisplayName(model)}</strong>: {score.toFixed(2)} avg rank
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
        <ReactMarkdown>{stage3Result.response}</ReactMarkdown>
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
                  <div className="message-content">
                    {msg.role === 'user' ? (
                      <p style={{ whiteSpace: 'pre-wrap' }}>{msg.content}</p>
                    ) : (
                      <ReactMarkdown>{msg.content?.stage3?.response || 'Processing...'}</ReactMarkdown>
                    )}
                  </div>
                </div>
              ))}

              {(stage1Results || stage2Results || stage3Result || currentStage) && (
                <div className="message assistant">
                  <div className="message-header">LLM COUNCIL</div>
                  <div className="message-content council-response">
                    {renderLoadingStage()}
                    {renderStage3()}
                    {renderStage2()}
                    {renderStage1()}
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
