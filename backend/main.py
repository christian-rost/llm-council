"""FastAPI backend for LLM Council with PDF support."""

from fastapi import FastAPI, HTTPException, UploadFile, File, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import uuid
import json
import asyncio
import base64

from . import storage, user_storage, auth
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


class RegisterRequest(BaseModel):
    """Request to register a new user."""
    username: str
    email: str
    password: str


class LoginRequest(BaseModel):
    """Request to login."""
    username: str
    password: str


class TokenResponse(BaseModel):
    """Response with access token."""
    access_token: str
    token_type: str = "bearer"
    user: Dict[str, Any]


class ResetPasswordRequest(BaseModel):
    """Request to reset a user's password."""
    new_password: str


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "service": "LLM Council API"}


@app.post("/api/upload-pdf")
async def upload_pdf(
    file: UploadFile = File(...),
    current_user: dict = Depends(auth.get_current_user)
):
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
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing PDF: {str(e)}")


@app.post("/api/auth/register")
async def register(request: RegisterRequest):
    """Register a new user."""
    try:
        user = user_storage.create_user(
            username=request.username,
            email=request.email,
            password=request.password
        )
        access_token = auth.create_access_token(user["id"])
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "id": user["id"],
                "username": user["username"],
                "email": user["email"],
                "created_at": user["created_at"]
            }
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/auth/login")
async def login(request: LoginRequest):
    """Login and get access token."""
    # Check if it's the admin user
    from .config import ADMIN_USERNAME, ADMIN_PASSWORD
    if request.username == ADMIN_USERNAME and ADMIN_USERNAME and ADMIN_PASSWORD:
        if request.password == ADMIN_PASSWORD:
            access_token = auth.create_access_token("admin")
            return {
                "access_token": access_token,
                "token_type": "bearer",
                "user": {
                    "id": "admin",
                    "username": ADMIN_USERNAME,
                    "email": "",
                    "is_admin": True,
                    "created_at": ""
                }
            }
        else:
            raise HTTPException(status_code=401, detail="Invalid username or password")
    
    # Regular user login
    user = user_storage.get_user_by_username(request.username)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    
    if not user_storage.verify_password(user, request.password):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    
    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="User account is inactive")
    
    access_token = auth.create_access_token(user["id"])
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user["id"],
            "username": user["username"],
            "email": user["email"],
            "created_at": user["created_at"]
        }
    }


@app.get("/api/auth/me")
async def get_current_user_info(current_user: dict = Depends(auth.get_current_user)):
    """Get current user information."""
    return {
        "id": current_user["id"],
        "username": current_user["username"],
        "email": current_user.get("email", ""),
        "created_at": current_user.get("created_at", ""),
        "is_admin": auth.is_admin_user(current_user)
    }


@app.get("/api/conversations", response_model=List[ConversationMetadata])
async def list_conversations(current_user: dict = Depends(auth.get_current_user)):
    """List all conversations for the current user (metadata only). Admin can see all conversations."""
    # Admin can see all conversations
    if auth.is_admin_user(current_user):
        return storage.list_conversations(user_id=None)
    return storage.list_conversations(user_id=current_user["id"])


@app.post("/api/conversations", response_model=Conversation)
async def create_conversation(
    request: CreateConversationRequest,
    current_user: dict = Depends(auth.get_current_user)
):
    """Create a new conversation."""
    conversation_id = str(uuid.uuid4())
    conversation = storage.create_conversation(conversation_id, user_id=current_user["id"])
    return conversation


@app.get("/api/conversations/{conversation_id}", response_model=Conversation)
async def get_conversation(
    conversation_id: str,
    current_user: dict = Depends(auth.get_current_user)
):
    """Get a specific conversation with all its messages."""
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # Admin can see all conversations
    if not auth.is_admin_user(current_user):
    # Admin can see all conversations
    if not auth.is_admin_user(current_user):
        # Check if user owns this conversation
        if conversation.get("user_id") != current_user["id"]:
            raise HTTPException(status_code=403, detail="Access denied")
    
    return conversation


@app.delete("/api/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    current_user: dict = Depends(auth.get_current_user)
):
    """Delete a conversation."""
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # Check if user owns this conversation
    if conversation.get("user_id") != current_user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    success = storage.delete_conversation(conversation_id)
    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"status": "deleted"}


@app.post("/api/conversations/{conversation_id}/message")
async def send_message(
    conversation_id: str,
    request: SendMessageRequest,
    current_user: dict = Depends(auth.get_current_user)
):
    """
    Send a message and run the 3-stage council process.
    Returns the complete response with all stages.
    """
    # Check if conversation exists
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # Check if user owns this conversation
    if conversation.get("user_id") != current_user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")

    # Check if this is the first message
    is_first_message = len(conversation["messages"]) == 0

    # Add user message
    storage.add_user_message(conversation_id, request.content)

    # If this is the first message, generate a title
    if is_first_message:
        title = await generate_conversation_title(request.content)
        storage.update_conversation_title(conversation_id, title)

    # Run the 3-stage council process (with optional PDF)
    stage1_results, stage2_results, stage3_result, metadata = await run_full_council(
        request.content,
        pdf_data=request.pdf_data,
        pdf_filename=request.pdf_filename
    )

    # Add assistant message with all stages
    storage.add_assistant_message(
        conversation_id,
        stage1_results,
        stage2_results,
        stage3_result,
        metadata
    )

    # Return the complete response with metadata
    return {
        "stage1": stage1_results,
        "stage2": stage2_results,
        "stage3": stage3_result,
        "metadata": metadata
    }


@app.post("/api/conversations/{conversation_id}/message/stream")
async def send_message_stream(
    conversation_id: str,
    request: SendMessageRequest,
    current_user: dict = Depends(auth.get_current_user)
):
    """
    Send a message and stream the 3-stage council process.
    Returns Server-Sent Events as each stage completes.
    """
    # Check if conversation exists
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # Check if user owns this conversation
    if conversation.get("user_id") != current_user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")

    # Check if this is the first message
    is_first_message = len(conversation["messages"]) == 0

    async def event_generator():
        try:
            # Add user message
            storage.add_user_message(conversation_id, request.content)

            # Start title generation in parallel (don't await yet)
            title_task = None
            if is_first_message:
                title_task = asyncio.create_task(generate_conversation_title(request.content))

            # Stage 1: Collect responses (with optional PDF)
            yield f"data: {json.dumps({'type': 'stage1_start'})}\n\n"
            stage1_results = await stage1_collect_responses(
                request.content,
                pdf_data=request.pdf_data,
                pdf_filename=request.pdf_filename
            )
            yield f"data: {json.dumps({'type': 'stage1_complete', 'data': stage1_results})}\n\n"

            # Stage 2: Collect rankings (no PDF needed - working with text responses)
            yield f"data: {json.dumps({'type': 'stage2_start'})}\n\n"
            stage2_results, label_to_model = await stage2_collect_rankings(request.content, stage1_results)
            aggregate_rankings = calculate_aggregate_rankings(stage2_results, label_to_model)
            metadata = {
                "label_to_model": label_to_model,
                "aggregate_rankings": aggregate_rankings
            }
            yield f"data: {json.dumps({'type': 'stage2_complete', 'data': stage2_results, 'metadata': metadata})}\n\n"

            # Stage 3: Synthesize final answer (no PDF needed - working with stage results)
            yield f"data: {json.dumps({'type': 'stage3_start'})}\n\n"
            stage3_result = await stage3_synthesize_final(request.content, stage1_results, stage2_results)
            yield f"data: {json.dumps({'type': 'stage3_complete', 'data': stage3_result})}\n\n"

            # Wait for title generation if it was started
            if title_task:
                title = await title_task
                storage.update_conversation_title(conversation_id, title)
                yield f"data: {json.dumps({'type': 'title_complete', 'data': {'title': title}})}\n\n"

            # Save complete assistant message
            storage.add_assistant_message(
                conversation_id,
                stage1_results,
                stage2_results,
                stage3_result,
                metadata
            )

            # Send completion event
            yield f"data: {json.dumps({'type': 'complete'})}\n\n"

        except Exception as e:
            # Send error event
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


# Admin endpoints
@app.get("/api/admin/users")
async def list_all_users(admin: dict = Depends(auth.get_current_admin)):
    """List all users (admin only)."""
    users = user_storage.list_all_users()
    return users


@app.get("/api/admin/users/{user_id}")
async def get_user_by_id(user_id: str, admin: dict = Depends(auth.get_current_admin)):
    """Get a specific user by ID (admin only)."""
    user = user_storage.get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Don't return password hash
    return {
        "id": user.get("id"),
        "username": user.get("username"),
        "email": user.get("email"),
        "created_at": user.get("created_at"),
        "is_active": user.get("is_active", True)
    }


@app.get("/api/admin/users/{user_id}/conversations", response_model=List[ConversationMetadata])
async def get_user_conversations(user_id: str, admin: dict = Depends(auth.get_current_admin)):
    """Get all conversations for a specific user (admin only)."""
    return storage.list_conversations(user_id=user_id)


@app.delete("/api/admin/users/{user_id}")
async def delete_user_endpoint(user_id: str, admin: dict = Depends(auth.get_current_admin)):
    """Delete a user (admin only)."""
    if user_id == "admin":
        raise HTTPException(status_code=400, detail="Cannot delete admin user")
    
    success = user_storage.delete_user(user_id)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    return {"status": "deleted"}


@app.post("/api/admin/users/{user_id}/reset-password")
async def reset_user_password_endpoint(
    user_id: str,
    request: ResetPasswordRequest,
    admin: dict = Depends(auth.get_current_admin)
):
    """Reset a user's password (admin only)."""
    if user_id == "admin":
        raise HTTPException(status_code=400, detail="Cannot reset admin password via API")
    
    success = user_storage.reset_user_password(user_id, request.new_password)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    return {"status": "password_reset"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
