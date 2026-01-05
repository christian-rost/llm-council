/**
 * API client for the LLM Council backend.
 */

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8001';

export const api = {
  /**
   * List all conversations
   */
  async listConversations() {
    const response = await fetch(`${API_BASE}/api/conversations`);
    if (!response.ok) throw new Error('Failed to fetch conversations');
    return response.json();
  },

  /**
   * Create a new conversation
   */
  async createConversation() {
    const response = await fetch(`${API_BASE}/api/conversations`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    if (!response.ok) throw new Error('Failed to create conversation');
    return response.json();
  },

  /**
   * Get a specific conversation
   */
  async getConversation(conversationId) {
    const response = await fetch(`${API_BASE}/api/conversations/${conversationId}`);
    if (!response.ok) throw new Error('Failed to fetch conversation');
    return response.json();
  },

  /**
   * Delete a conversation
   */
  async deleteConversation(conversationId) {
    const response = await fetch(`${API_BASE}/api/conversations/${conversationId}`, {
      method: 'DELETE',
    });
    if (!response.ok) throw new Error('Failed to delete conversation');
    return response.json();
  },

  /**
   * Send a message (non-streaming)
   */
  async sendMessage(conversationId, content, pdfData = null, pdfFilename = null) {
    const response = await fetch(`${API_BASE}/api/conversations/${conversationId}/message`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        content,
        pdf_data: pdfData,
        pdf_filename: pdfFilename,
      }),
    });
    if (!response.ok) throw new Error('Failed to send message');
    return response.json();
  },

  /**
   * Send a message with streaming response
   */
  async sendMessageStream(conversationId, content, onStage1, onStage2, onStage3, onTitleUpdate, pdfData = null, pdfFilename = null) {
    const response = await fetch(`${API_BASE}/api/conversations/${conversationId}/message/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        content,
        pdf_data: pdfData,
        pdf_filename: pdfFilename,
      }),
    });

    if (!response.ok) throw new Error('Failed to send message');

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value);
      const lines = chunk.split('\n');

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6);
          if (data === '[DONE]') return;

          try {
            const parsed = JSON.parse(data);
            switch (parsed.type) {
              case 'stage1_complete':
                onStage1?.(parsed.data);
                break;
              case 'stage2_complete':
                onStage2?.(parsed.data, parsed.metadata);
                break;
              case 'stage3_complete':
                onStage3?.(parsed.data);
                break;
              case 'title_update':
                onTitleUpdate?.(parsed.title);
                break;
            }
          } catch (e) {
            console.error('Failed to parse SSE data:', e);
          }
        }
      }
    }
  },

  /**
   * Upload a PDF file and get base64 encoding
   * The PDF will be sent to OpenRouter for native processing
   */
  async uploadPdf(file) {
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch(`${API_BASE}/api/upload-pdf`, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to upload PDF');
    }

    return response.json();
  },
};
