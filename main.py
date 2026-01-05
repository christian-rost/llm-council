"""
FastAPI backend for LLM Council with PDF support.
"""

import json
import uuid
import base64
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .storage import storage
from .council import run_full_council, generate_conversation_title, stage1_collect_responses, stage2_collect_rankings, stage3_synthesize_final, calculate_aggregate_rankings

app = FastAPI(title="LLM Council API")

# Enable CORS for local development and production
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "https://llm-council-frontend.xqtfive.de",
        "https://llm-frontend.xqtfive.de"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CreateConversationRequest(BaseModel):
    """Request to create a new conversation."""
    pass


class SendMessageRequest(BaseModel):
    """Request to send a message in a conversation."""
    content: str
    pdf_data: Optional[str] = None  # Base64 encoded PDF
    pdf_filename: Optional[str] = None


class ConversationMetadata(BaseModel):
    """Conversation metadata for list view."""
    id: str
    created_at: str
    title: str
    message_count: int


class Conversation(BaseModel):
    """Full conversation with all messages."""
    id: str
    created_at: str
    title: str
    messages: List[Dict[str, Any]]


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "service": "LLM Council API"}


@app.post("/api/upload-pdf")
async def upload_pdf(file: UploadFile = File(...)):
    """
    Upload a PDF file and return it as base64.
    The actual PDF processing is done by OpenRouter when sending to LLMs.
    """
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files allowed")
    
    try:
        content = await file.read()
        
        # Check file size (max 20MB)
        if len(content) > 20 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="PDF file too large. Maximum size is 20MB.")
        
        # Encode to base64
        base64_content = base64.b64encode(content).decode('utf-8')
        
        return {
            "filename": file.filename,
            "base64": base64_content,
            "size_bytes": len(content)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing PDF: {str(e)}")


@app.get("/api/conversations", response_model=List[ConversationMetadata])
async def list_conversations():
    """List all conversations (metadata only)."""
    return storage.list_conversations()


@app.post("/api/conversations", response_model=Conversation)
async def create_conversation(request: CreateConversationRequest):
    """Create a new conversation."""
    conversation_id = str(uuid.uuid4())
    conversation = storage.create_conversation(conversation_id)
    return conversation


@app.get("/api/conversations/{conversation_id}", response_model=Conversation)
async def get_conversation(conversation_id: str):
    """Get a specific conversation with all its messages."""
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@app.delete("/api/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """Delete a conversation."""
    success = storage.delete_conversation(conversation_id)
    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"status": "deleted"}


@app.post("/api/conversations/{conversation_id}/message")
async def send_message(conversation_id: str, request: SendMessageRequest):
    """Send a message and get a full council response (non-streaming)."""
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # Add user message
    storage.add_message(conversation_id, "user", request.content)
    
    # Run the council with optional PDF
    result = await run_full_council(
        request.content,
        pdf_data=request.pdf_data,
        pdf_filename=request.pdf_filename
    )
    
    # Add assistant message with full council result
    storage.add_message(conversation_id, "assistant", result)
    
    # Generate title if this is the first message
    if len(conversation["messages"]) == 0:
        title = await generate_conversation_title(request.content)
        storage.update_conversation_title(conversation_id, title)
    
    return result


@app.post("/api/conversations/{conversation_id}/message/stream")
async def send_message_stream(conversation_id: str, request: SendMessageRequest):
    """Send a message and stream the council response."""
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # Add user message
    storage.add_message(conversation_id, "user", request.content)
    
    async def generate():
        # Stage 1: Collect individual responses
        stage1_results = await stage1_collect_responses(
            request.content,
            pdf_data=request.pdf_data,
            pdf_filename=request.pdf_filename
        )
        yield f"data: {json.dumps({'type': 'stage1_complete', 'data': stage1_results})}\n\n"
        
        # Stage 2: Rankings (without PDF - just text responses)
        stage2_results, label_to_model = await stage2_collect_rankings(request.content, stage1_results)
        aggregate_rankings = calculate_aggregate_rankings(stage2_results, label_to_model)
        yield f"data: {json.dumps({'type': 'stage2_complete', 'data': stage2_results, 'metadata': {'label_to_model': label_to_model, 'aggregate_rankings': aggregate_rankings}})}\n\n"
        
        # Stage 3: Final synthesis (without PDF - uses stage1/stage2 results)
        stage3_result = await stage3_synthesize_final(request.content, stage1_results, stage2_results)
        yield f"data: {json.dumps({'type': 'stage3_complete', 'data': stage3_result})}\n\n"
        
        # Save the complete result
        full_result = {
            "stage1": stage1_results,
            "stage2": stage2_results,
            "stage3": stage3_result,
            "metadata": {
                "label_to_model": label_to_model,
                "aggregate_rankings": aggregate_rankings
            }
        }
        storage.add_message(conversation_id, "assistant", full_result)
        
        # Generate title if first message
        if len(conversation["messages"]) == 0:
            title = await generate_conversation_title(request.content)
            storage.update_conversation_title(conversation_id, title)
            yield f"data: {json.dumps({'type': 'title_update', 'title': title})}\n\n"
        
        yield "data: [DONE]\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")
