import { useState, useEffect } from 'react';
import { api } from '../api';
import './AdminDashboard.css';

function AdminDashboard() {
  const [activeSection, setActiveSection] = useState('models');
  const [chairmanModel, setChairmanModel] = useState('');
  const [councilModels, setCouncilModels] = useState([]);
  const [newModel, setNewModel] = useState('');
  const [users, setUsers] = useState([]);
  const [apiKeys, setApiKeys] = useState([]);
  const [newKeyName, setNewKeyName] = useState('');
  const [createdKey, setCreatedKey] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState(null);

  useEffect(() => {
    loadSettings();
    loadUsers();
    loadApiKeys();
  }, []);

  const loadSettings = async () => {
    try {
      const data = await api.getAdminSettings();
      setChairmanModel(data.chairman_model || '');
      setCouncilModels(data.council_models || []);
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
    try {
      await api.updateAdminSettings({
        chairman_model: chairmanModel,
        council_models: councilModels,
      });
      setMessage({ type: 'success', text: 'Settings saved successfully' });
    } catch (error) {
      setMessage({ type: 'error', text: 'Failed to save settings' });
    } finally {
      setSaving(false);
    }
  };

  const MAX_COUNCIL_MODELS = 9;

  const addCouncilModel = () => {
    const trimmed = newModel.trim();
    if (!trimmed) return;
    if (councilModels.length >= MAX_COUNCIL_MODELS) {
      setMessage({ type: 'error', text: `Maximum ${MAX_COUNCIL_MODELS} council models allowed` });
      return;
    }
    if (councilModels.includes(trimmed)) {
      setMessage({ type: 'error', text: 'Model already in the list' });
      return;
    }
    setCouncilModels([...councilModels, trimmed]);
    setNewModel('');
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
            <input
              type="text"
              value={chairmanModel}
              onChange={(e) => setChairmanModel(e.target.value)}
              placeholder="e.g. google/gemini-3-pro-preview"
            />
          </div>

          <div className="admin-form-group">
            <label>Council Models</label>
            <p className="admin-hint">Models that provide individual responses (Stage 1) and peer reviews (Stage 2).</p>
            <div className="council-models-list">
              {councilModels.map((model) => (
                <div key={model} className="council-model-item">
                  <span>{model}</span>
                  <button
                    className="remove-model-btn"
                    onClick={() => removeCouncilModel(model)}
                    title="Remove model"
                  >
                    x
                  </button>
                </div>
              ))}
            </div>
            <div className="add-model-row">
              <input
                type="text"
                value={newModel}
                onChange={(e) => setNewModel(e.target.value)}
                onKeyPress={handleNewModelKeyPress}
                placeholder="e.g. openai/gpt-5.1"
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

          <button
            className="save-settings-btn"
            onClick={saveSettings}
            disabled={saving}
          >
            {saving ? 'Saving...' : 'Save Settings'}
          </button>
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
