import { useState, useEffect } from 'react';
import { api } from '../api';
import './AdminDashboard.css';

function AdminDashboard() {
  const [activeSection, setActiveSection] = useState('models');
  const [chairmanModel, setChairmanModel] = useState('');
  const [councilModels, setCouncilModels] = useState([]);
  const [newModel, setNewModel] = useState('');
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState(null);

  useEffect(() => {
    loadSettings();
    loadUsers();
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

  const addCouncilModel = () => {
    const trimmed = newModel.trim();
    if (!trimmed) return;
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
              />
              <button className="add-model-btn" onClick={addCouncilModel}>
                Add
              </button>
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
    </div>
  );
}

export default AdminDashboard;
