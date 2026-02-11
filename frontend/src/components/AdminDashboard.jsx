import { useState, useEffect } from 'react';
import { api } from '../api';
import './AdminDashboard.css';

const PROVIDER_OPTIONS = [
  { value: 'openrouter', label: 'OpenRouter' },
  { value: 'openai', label: 'OpenAI' },
  { value: 'google', label: 'Google (Gemini)' },
  { value: 'anthropic', label: 'Anthropic' },
  { value: 'xai', label: 'xAI (Grok)' },
  { value: 'mistral', label: 'Mistral' },
];

const KNOWN_PROVIDERS = PROVIDER_OPTIONS.map(p => p.value);

function parseModelId(modelId) {
  if (modelId.includes(':')) {
    const [prefix, ...rest] = modelId.split(':');
    if (KNOWN_PROVIDERS.includes(prefix)) {
      return { provider: prefix, model: rest.join(':') };
    }
  }
  // Legacy format or OpenRouter with suffix (e.g. "openai/gpt-5.1:online")
  return { provider: 'openrouter', model: modelId };
}

function buildModelId(provider, model) {
  if (provider === 'openrouter') return model; // Keep legacy format for openrouter
  return `${provider}:${model}`;
}

function AdminDashboard() {
  const [activeSection, setActiveSection] = useState('models');
  const [chairmanModel, setChairmanModel] = useState('');
  const [councilModels, setCouncilModels] = useState([]);
  const [newModelProvider, setNewModelProvider] = useState('openrouter');
  const [newModelName, setNewModelName] = useState('');
  const [chairmanProvider, setChairmanProvider] = useState('openrouter');
  const [chairmanModelName, setChairmanModelName] = useState('');
  const [users, setUsers] = useState([]);
  const [apiKeys, setApiKeys] = useState([]);
  const [newKeyName, setNewKeyName] = useState('');
  const [createdKey, setCreatedKey] = useState(null);
  const [providers, setProviders] = useState([]);
  const [providerKeyInputs, setProviderKeyInputs] = useState({});
  const [testingProvider, setTestingProvider] = useState(null);
  const [savingProviderKey, setSavingProviderKey] = useState(null);
  const [webSearchEnabled, setWebSearchEnabled] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState(null);

  useEffect(() => {
    loadSettings();
    loadUsers();
    loadApiKeys();
    loadProviders();
  }, []);

  const loadSettings = async () => {
    try {
      const data = await api.getAdminSettings();
      const chairman = data.chairman_model || '';
      setChairmanModel(chairman);
      setCouncilModels(data.council_models || []);
      setWebSearchEnabled(data.web_search_enabled || false);
      // Parse chairman into provider + model
      const parsed = parseModelId(chairman);
      setChairmanProvider(parsed.provider);
      setChairmanModelName(parsed.model);
    } catch (error) {
      setMessage({ type: 'error', text: 'Failed to load settings' });
    } finally {
      setLoading(false);
    }
  };

  const loadUsers = async () => {
    try {
      const data = await api.getAdminUsers();
      setUsers(data);
    } catch (error) {
      console.error('Failed to load users:', error);
    }
  };

  const loadApiKeys = async () => {
    try {
      const data = await api.getAdminApiKeys();
      setApiKeys(data);
    } catch (error) {
      console.error('Failed to load API keys:', error);
    }
  };

  const loadProviders = async () => {
    try {
      const data = await api.getAdminProviders();
      setProviders(data);
    } catch (error) {
      console.error('Failed to load providers:', error);
    }
  };

  const saveProviderKey = async (provider) => {
    const key = providerKeyInputs[provider]?.trim();
    if (!key) return;
    setSavingProviderKey(provider);
    try {
      await api.setAdminProviderKey(provider, key);
      setProviderKeyInputs({ ...providerKeyInputs, [provider]: '' });
      setMessage({ type: 'success', text: `API key for ${provider} saved` });
      loadProviders();
    } catch (error) {
      setMessage({ type: 'error', text: `Failed to save key: ${error.message}` });
    } finally {
      setSavingProviderKey(null);
    }
  };

  const deleteProviderKey = async (provider, providerName) => {
    if (!confirm(`Delete database API key for "${providerName}"?`)) return;
    try {
      await api.deleteAdminProviderKey(provider);
      setMessage({ type: 'success', text: `Database key for ${providerName} deleted` });
      loadProviders();
    } catch (error) {
      setMessage({ type: 'error', text: `Failed to delete key: ${error.message}` });
    }
  };

  const testProvider = async (provider) => {
    setTestingProvider(provider);
    setMessage(null);
    try {
      const result = await api.testAdminProvider(provider);
      if (result.status === 'ok') {
        setMessage({ type: 'success', text: `${provider}: Connection successful` });
      } else {
        setMessage({ type: 'error', text: `${provider}: ${result.message || 'Test failed'}` });
      }
    } catch (error) {
      setMessage({ type: 'error', text: `${provider}: ${error.message}` });
    } finally {
      setTestingProvider(null);
    }
  };

  const createApiKey = async () => {
    const trimmed = newKeyName.trim();
    if (!trimmed) return;
    try {
      const data = await api.createAdminApiKey(trimmed);
      setCreatedKey(data.api_key);
      setNewKeyName('');
      loadApiKeys();
      setMessage({ type: 'success', text: 'API key created' });
    } catch (error) {
      setMessage({ type: 'error', text: `Failed to create API key: ${error.message}` });
    }
  };

  const deleteApiKey = async (keyId, keyName) => {
    if (!confirm(`Deactivate API key "${keyName}"? This cannot be undone.`)) return;
    try {
      await api.deleteAdminApiKey(keyId);
      setApiKeys(apiKeys.filter((k) => k.id !== keyId));
      setMessage({ type: 'success', text: `API key "${keyName}" deactivated` });
    } catch (error) {
      setMessage({ type: 'error', text: `Failed to delete API key: ${error.message}` });
    }
  };

  const copyToClipboard = async (text) => {
    try {
      await navigator.clipboard.writeText(text);
      setMessage({ type: 'success', text: 'API key copied to clipboard' });
    } catch {
      setMessage({ type: 'error', text: 'Failed to copy to clipboard' });
    }
  };

  const saveSettings = async () => {
    setSaving(true);
    setMessage(null);
    // Build chairman model ID from provider + model
    const fullChairman = buildModelId(chairmanProvider, chairmanModelName);
    try {
      await api.updateAdminSettings({
        chairman_model: fullChairman,
        council_models: councilModels,
        web_search_enabled: webSearchEnabled,
      });
      setChairmanModel(fullChairman);
      setMessage({ type: 'success', text: 'Settings saved successfully' });
    } catch (error) {
      setMessage({ type: 'error', text: 'Failed to save settings' });
    } finally {
      setSaving(false);
    }
  };

  const MAX_COUNCIL_MODELS = 9;

  const addCouncilModel = () => {
    const trimmedName = newModelName.trim();
    if (!trimmedName) return;
    if (councilModels.length >= MAX_COUNCIL_MODELS) {
      setMessage({ type: 'error', text: `Maximum ${MAX_COUNCIL_MODELS} council models allowed` });
      return;
    }
    const fullId = buildModelId(newModelProvider, trimmedName);
    if (councilModels.includes(fullId)) {
      setMessage({ type: 'error', text: 'Model already in the list' });
      return;
    }
    setCouncilModels([...councilModels, fullId]);
    setNewModelName('');
    setMessage(null);
  };

  const removeCouncilModel = (model) => {
    setCouncilModels(councilModels.filter((m) => m !== model));
  };

  const deleteUser = async (userId, username) => {
    if (!confirm(`Delete user "${username}"? This cannot be undone.`)) return;
    try {
      await api.deleteAdminUser(userId);
      setUsers(users.filter((u) => u.id !== userId));
      setMessage({ type: 'success', text: `User "${username}" deleted` });
    } catch (error) {
      setMessage({ type: 'error', text: `Failed to delete user: ${error.message}` });
    }
  };

  const handleNewModelKeyPress = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      addCouncilModel();
    }
  };

  const getDisplayModelId = (modelId) => {
    const { provider, model } = parseModelId(modelId);
    const providerLabel = PROVIDER_OPTIONS.find(p => p.value === provider)?.label || provider;
    return { provider, providerLabel, model };
  };

  // Helper: check if a provider has a configured API key
  const isProviderConfigured = (providerId) => {
    const p = providers.find((pr) => pr.provider === providerId);
    return p?.configured || false;
  };

  if (loading) {
    return (
      <div className="admin-dashboard">
        <div className="admin-loading">
          <div className="spinner"></div>
          <p>Loading admin settings...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="admin-dashboard">
      <div className="admin-header">
        <h2>Admin Dashboard</h2>
      </div>

      {message && (
        <div className={`admin-message ${message.type}`}>
          {message.text}
        </div>
      )}

      <div className="admin-tabs">
        <button
          className={`admin-tab ${activeSection === 'models' ? 'active' : ''}`}
          onClick={() => setActiveSection('models')}
        >
          Model Configuration
        </button>
        <button
          className={`admin-tab ${activeSection === 'providers' ? 'active' : ''}`}
          onClick={() => { setActiveSection('providers'); loadProviders(); }}
        >
          Providers
        </button>
        <button
          className={`admin-tab ${activeSection === 'users' ? 'active' : ''}`}
          onClick={() => setActiveSection('users')}
        >
          User Management
        </button>
        <button
          className={`admin-tab ${activeSection === 'apikeys' ? 'active' : ''}`}
          onClick={() => { setActiveSection('apikeys'); setCreatedKey(null); }}
        >
          API Keys
        </button>
      </div>

      {activeSection === 'models' && (
        <div className="admin-section">
          <div className="admin-form-group">
            <label>Chairman / Moderator</label>
            <p className="admin-hint">The model that synthesizes the final answer in Stage 3.</p>
            <div className="model-input-row">
              <select
                value={chairmanProvider}
                onChange={(e) => setChairmanProvider(e.target.value)}
                className="provider-select"
              >
                {PROVIDER_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}{isProviderConfigured(opt.value) ? '' : ' (no key)'}
                  </option>
                ))}
              </select>
              <input
                type="text"
                value={chairmanModelName}
                onChange={(e) => setChairmanModelName(e.target.value)}
                placeholder={chairmanProvider === 'openrouter' ? 'e.g. google/gemini-3-pro-preview' : 'e.g. gemini-3-pro-preview'}
              />
            </div>
          </div>

          <div className="admin-form-group">
            <label>Council Models</label>
            <p className="admin-hint">Models that provide individual responses (Stage 1) and peer reviews (Stage 2).</p>
            <div className="council-models-list">
              {councilModels.map((model) => {
                const { providerLabel, model: bareModel } = getDisplayModelId(model);
                return (
                  <div key={model} className="council-model-item">
                    <span className="model-provider-badge">{providerLabel}</span>
                    <span className="model-name">{bareModel}</span>
                    <button
                      className="remove-model-btn"
                      onClick={() => removeCouncilModel(model)}
                      title="Remove model"
                    >
                      x
                    </button>
                  </div>
                );
              })}
            </div>
            <div className="model-input-row">
              <select
                value={newModelProvider}
                onChange={(e) => setNewModelProvider(e.target.value)}
                className="provider-select"
                disabled={councilModels.length >= MAX_COUNCIL_MODELS}
              >
                {PROVIDER_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}{isProviderConfigured(opt.value) ? '' : ' (no key)'}
                  </option>
                ))}
              </select>
              <input
                type="text"
                value={newModelName}
                onChange={(e) => setNewModelName(e.target.value)}
                onKeyPress={handleNewModelKeyPress}
                placeholder={newModelProvider === 'openrouter' ? 'e.g. openai/gpt-5.1' : 'e.g. gpt-5.1'}
                disabled={councilModels.length >= MAX_COUNCIL_MODELS}
              />
              <button
                className="add-model-btn"
                onClick={addCouncilModel}
                disabled={councilModels.length >= MAX_COUNCIL_MODELS}
              >
                Add
              </button>
            </div>
            <p className="admin-hint">{councilModels.length}/{MAX_COUNCIL_MODELS} Models</p>
          </div>

          <div className="admin-form-group">
            <label>Web Search</label>
            <p className="admin-hint">
              Enables web search for Stage 1 responses. Supported by: OpenRouter (:online), OpenAI, Google Gemini, xAI. Not available for: Anthropic, Mistral.
            </p>
            <div className="toggle-row">
              <label className="toggle-switch">
                <input
                  type="checkbox"
                  checked={webSearchEnabled}
                  onChange={(e) => setWebSearchEnabled(e.target.checked)}
                />
                <span className="toggle-slider"></span>
              </label>
              <span className="toggle-label">{webSearchEnabled ? 'Enabled' : 'Disabled'}</span>
            </div>
          </div>

          <button
            className="save-settings-btn"
            onClick={saveSettings}
            disabled={saving}
          >
            {saving ? 'Saving...' : 'Save Settings'}
          </button>
        </div>
      )}

      {activeSection === 'providers' && (
        <div className="admin-section">
          <p className="admin-hint" style={{ marginBottom: 16 }}>
            Configure API keys for direct provider access. Environment variable keys are used as fallback — database keys take priority.
          </p>
          <div className="provider-cards">
            {providers.map((p) => (
              <div key={p.provider} className="provider-card">
                <div className="provider-card-header">
                  <span className="provider-card-name">{p.name}</span>
                  <span className={`status-badge ${p.configured ? 'active' : 'inactive'}`}>
                    {p.configured ? p.source === 'database' ? 'DB Key' : 'Env Var' : 'Not configured'}
                  </span>
                </div>
                <div className="provider-card-body">
                  <div className="provider-key-row">
                    <input
                      type="password"
                      value={providerKeyInputs[p.provider] || ''}
                      onChange={(e) =>
                        setProviderKeyInputs({ ...providerKeyInputs, [p.provider]: e.target.value })
                      }
                      placeholder="Enter API key..."
                      className="provider-key-input"
                    />
                    <button
                      className="add-model-btn"
                      onClick={() => saveProviderKey(p.provider)}
                      disabled={savingProviderKey === p.provider || !providerKeyInputs[p.provider]?.trim()}
                    >
                      {savingProviderKey === p.provider ? '...' : 'Save'}
                    </button>
                  </div>
                  <div className="provider-card-actions">
                    {p.source === 'database' && (
                      <button
                        className="delete-user-btn"
                        onClick={() => deleteProviderKey(p.provider, p.name)}
                      >
                        Delete DB Key
                      </button>
                    )}
                    {p.configured && (
                      <button
                        className="test-provider-btn"
                        onClick={() => testProvider(p.provider)}
                        disabled={testingProvider === p.provider}
                      >
                        {testingProvider === p.provider ? 'Testing...' : 'Test'}
                      </button>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {activeSection === 'users' && (
        <div className="admin-section">
          <table className="users-table">
            <thead>
              <tr>
                <th>Username</th>
                <th>Email</th>
                <th>Created</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.length === 0 ? (
                <tr>
                  <td colSpan="5" className="no-users">No registered users</td>
                </tr>
              ) : (
                users.map((user) => (
                  <tr key={user.id}>
                    <td>{user.username}</td>
                    <td>{user.email}</td>
                    <td>{new Date(user.created_at).toLocaleDateString()}</td>
                    <td>
                      <span className={`status-badge ${user.is_active ? 'active' : 'inactive'}`}>
                        {user.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </td>
                    <td>
                      <button
                        className="delete-user-btn"
                        onClick={() => deleteUser(user.id, user.username)}
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}

      {activeSection === 'apikeys' && (
        <div className="admin-section">
          <div className="admin-form-group">
            <label>Create New API Key</label>
            <p className="admin-hint">The key will only be shown once after creation. Copy it immediately.</p>
            <div className="add-model-row">
              <input
                type="text"
                value={newKeyName}
                onChange={(e) => setNewKeyName(e.target.value)}
                onKeyPress={(e) => { if (e.key === 'Enter') { e.preventDefault(); createApiKey(); } }}
                placeholder="Key name (e.g. Production, Testing)"
              />
              <button className="add-model-btn" onClick={createApiKey}>
                Create
              </button>
            </div>
          </div>

          {createdKey && (
            <div className="api-key-created">
              <strong>New API Key (copy now — it won't be shown again):</strong>
              <div className="api-key-created-value">
                <code>{createdKey}</code>
                <button className="copy-key-btn" onClick={() => copyToClipboard(createdKey)}>
                  Copy
                </button>
              </div>
            </div>
          )}

          <table className="users-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Prefix</th>
                <th>Rate Limit</th>
                <th>Usage</th>
                <th>Created</th>
                <th>Last Used</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {apiKeys.length === 0 ? (
                <tr>
                  <td colSpan="8" className="no-users">No API keys</td>
                </tr>
              ) : (
                apiKeys.map((key) => (
                  <tr key={key.id}>
                    <td>{key.name}</td>
                    <td><code className="key-prefix">{key.key_prefix}...</code></td>
                    <td>{key.rate_limit}/min</td>
                    <td>{key.usage_count}</td>
                    <td>{new Date(key.created_at).toLocaleDateString()}</td>
                    <td>{key.last_used_at ? new Date(key.last_used_at).toLocaleDateString() : 'Never'}</td>
                    <td>
                      <span className={`status-badge ${key.is_active ? 'active' : 'inactive'}`}>
                        {key.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </td>
                    <td>
                      {key.is_active && (
                        <button
                          className="delete-user-btn"
                          onClick={() => deleteApiKey(key.id, key.name)}
                        >
                          Deactivate
                        </button>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default AdminDashboard;
