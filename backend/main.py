"""FastAPI backend for XQT5AIs with PDF support."""

import logging
import os
import re
import time
import uuid
import json
import asyncio
import base64

from fastapi import FastAPI, HTTPException, UploadFile, File, Depends, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator, EmailStr
from typing import List, Dict, Any, Optional
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from . import storage, user_storage, auth, settings, api_keys
from .council import run_full_council, generate_conversation_title, stage1_collect_responses, stage2_collect_rankings, stage3_synthesize_final, calculate_aggregate_rankings

logger = logging.getLogger(__name__)

# Rate limiter setup
limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="XQT5AIs API")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS origins from environment variable (comma-separated) or defaults
DEFAULT_CORS_ORIGINS = "http://localhost:5173,http://localhost:3000"
cors_origins_str = os.getenv("CORS_ORIGINS", DEFAULT_CORS_ORIGINS)
cors_origins = [origin.strip() for origin in cors_origins_str.split(",") if origin.strip()]

# Enable CORS for local development and production
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
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
    email: EmailStr
    password: str

    @field_validator('username')
    @classmethod
    def validate_username(cls, v: str) -> str:
        if len(v) < 3 or len(v) > 32:
            raise ValueError('Username must be between 3 and 32 characters')
        if not re.match(r'^[a-zA-Z0-9_]+$', v):
            raise ValueError('Username can only contain letters, numbers, and underscores')
        return v

    @field_validator('password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        return v


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


class UpdateSettingsRequest(BaseModel):
    """Request to update admin settings."""
    chairman_model: Optional[str] = None
    council_models: Optional[List[str]] = None

    @field_validator('council_models')
    @classmethod
    def validate_council_models(cls, v):
        if v is not None and len(v) > 9:
            raise ValueError('Maximum 9 council models allowed')
        return v


class CouncilRequest(BaseModel):
    """Request for the public council API."""
    question: str
    pdf_data: Optional[str] = None
    pdf_filename: Optional[str] = None

    @field_validator('question')
    @classmethod
    def validate_question(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('Question must not be empty')
        if len(v) > 50000:
            raise ValueError('Question must not exceed 50000 characters')
        return v.strip()


class CreateApiKeyRequest(BaseModel):
    """Request to create a new API key."""
    name: str
    rate_limit: int = 5

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('Name must not be empty')
        if len(v) > 100:
            raise ValueError('Name must not exceed 100 characters')
        return v.strip()

    @field_validator('rate_limit')
    @classmethod
    def validate_rate_limit(cls, v: int) -> int:
        if v < 1 or v > 100:
            raise ValueError('Rate limit must be between 1 and 100')
        return v


async def get_api_key_user(x_api_key: str = Header(...)) -> Dict[str, Any]:
    """Dependency: validate API key from X-API-Key header."""
    key_record = api_keys.verify_api_key(x_api_key)
    if key_record is None:
        raise HTTPException(status_code=401, detail="Invalid or inactive API key")
    return key_record


def get_api_key_for_rate_limit(request: Request) -> str:
    """Rate limit key function: use API key prefix instead of IP."""
    api_key = request.headers.get("X-API-Key", "")
    if api_key and len(api_key) >= 12:
        return api_key[:12]
    return get_remote_address(request)


# Secondary limiter for API key-based rate limiting
api_limiter = Limiter(key_func=get_api_key_for_rate_limit, app=app)


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "XQT5AIs API"
    }


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
        logger.error(f"Error processing PDF: {e}")
        raise HTTPException(status_code=500, detail="Error processing PDF file")


@app.post("/api/auth/register")
@limiter.limit("3/minute")
async def register(request: Request, body: RegisterRequest):
    """Register a new user."""
    try:
        user = user_storage.create_user(
            username=body.username,
            email=body.email,
            password=body.password
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
@limiter.limit("5/minute")
async def login(request: Request, body: LoginRequest):
    """Login and get access token."""
    # Check if it's the admin user
    from .config import ADMIN_USERNAME, ADMIN_PASSWORD

    # Check admin login first (only if admin is configured)
    if ADMIN_USERNAME and ADMIN_PASSWORD:
        if body.username == ADMIN_USERNAME:
            if body.password == ADMIN_PASSWORD:
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
    user = user_storage.get_user_by_username(body.username)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    if not user_storage.verify_password(user, body.password):
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
    # Admin user has id "admin" (not a UUID), so pass None for user_id
    user_id = None if auth.is_admin_user(current_user) else current_user["id"]
    conversation = storage.create_conversation(conversation_id, user_id=user_id)
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
    
    # Admin can delete any conversation
    if not auth.is_admin_user(current_user):
        # Check if user owns this conversation
        if conversation.get("user_id") != current_user["id"]:
            raise HTTPException(status_code=403, detail="Access denied")
    
    success = storage.delete_conversation(conversation_id)
    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"status": "deleted"}


@app.post("/api/conversations/{conversation_id}/message")
@limiter.limit("10/minute")
async def send_message(
    request: Request,
    conversation_id: str,
    body: SendMessageRequest,
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

    # Admin can send messages to any conversation
    if not auth.is_admin_user(current_user):
        # Check if user owns this conversation
        if conversation.get("user_id") != current_user["id"]:
            raise HTTPException(status_code=403, detail="Access denied")

    # Check if this is the first message
    is_first_message = len(conversation["messages"]) == 0

    # Add user message
    storage.add_user_message(conversation_id, body.content)

    # If this is the first message, generate a title
    if is_first_message:
        title = await generate_conversation_title(body.content)
        storage.update_conversation_title(conversation_id, title)

    # Run the 3-stage council process (with optional PDF)
    stage1_results, stage2_results, stage3_result, metadata = await run_full_council(
        body.content,
        pdf_data=body.pdf_data,
        pdf_filename=body.pdf_filename
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
@limiter.limit("10/minute")
async def send_message_stream(
    request: Request,
    conversation_id: str,
    body: SendMessageRequest,
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

    # Admin can send messages to any conversation
    if not auth.is_admin_user(current_user):
        # Check if user owns this conversation
        if conversation.get("user_id") != current_user["id"]:
            raise HTTPException(status_code=403, detail="Access denied")

    # Check if this is the first message
    is_first_message = len(conversation["messages"]) == 0

    async def event_generator():
        try:
            # Add user message
            storage.add_user_message(conversation_id, body.content)

            # Start title generation in parallel (don't await yet)
            title_task = None
            if is_first_message:
                title_task = asyncio.create_task(generate_conversation_title(body.content))

            # Stage 1: Collect responses (with optional PDF)
            yield f"data: {json.dumps({'type': 'stage1_start'})}\n\n"
            stage1_results, stage1_failed = await stage1_collect_responses(
                body.content,
                pdf_data=body.pdf_data,
                pdf_filename=body.pdf_filename
            )
            yield f"data: {json.dumps({'type': 'stage1_complete', 'data': stage1_results, 'failed_models': stage1_failed})}\n\n"

            # Stage 2: Collect rankings (no PDF needed - working with text responses)
            yield f"data: {json.dumps({'type': 'stage2_start'})}\n\n"
            stage2_results, label_to_model, stage2_failed = await stage2_collect_rankings(body.content, stage1_results)
            aggregate_rankings = calculate_aggregate_rankings(stage2_results, label_to_model)
            metadata = {
                "label_to_model": label_to_model,
                "aggregate_rankings": aggregate_rankings,
                "stage1_failed": stage1_failed,
                "stage2_failed": stage2_failed,
            }
            yield f"data: {json.dumps({'type': 'stage2_complete', 'data': stage2_results, 'metadata': metadata})}\n\n"

            # Stage 3: Synthesize final answer (no PDF needed - working with stage results)
            yield f"data: {json.dumps({'type': 'stage3_start'})}\n\n"
            stage3_result = await stage3_synthesize_final(body.content, stage1_results, stage2_results)
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
            # Send error event (don't expose internal details)
            logger.error(f"Error in streaming response: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': 'An error occurred processing your request'})}\n\n"

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


@app.get("/api/admin/settings")
async def get_admin_settings(admin: dict = Depends(auth.get_current_admin)):
    """Get current admin settings (admin only)."""
    return {
        "chairman_model": settings.get_chairman_model(),
        "council_models": settings.get_council_models(),
    }


@app.put("/api/admin/settings")
async def update_admin_settings(
    body: UpdateSettingsRequest,
    admin: dict = Depends(auth.get_current_admin),
):
    """Update admin settings (admin only)."""
    if body.chairman_model is not None:
        settings.set_setting("chairman_model", body.chairman_model)
    if body.council_models is not None:
        settings.set_setting("council_models", body.council_models)
    return {"status": "updated"}


# ── Public REST API ──────────────────────────────────────────────────────────

@app.post("/api/v1/council")
@api_limiter.limit("5/minute")
async def public_council(
    request: Request,
    body: CouncilRequest,
    key_record: dict = Depends(get_api_key_user),
):
    """
    Public API: Run a full council deliberation.
    Authenticated via X-API-Key header. Stateless (no conversation stored).
    """
    start_time = time.time()

    try:
        stage1_results, stage2_results, stage3_result, metadata = await run_full_council(
            body.question,
            pdf_data=body.pdf_data,
            pdf_filename=body.pdf_filename,
        )
    except Exception as e:
        logger.error(f"Council API error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

    # Check if all models failed
    if not stage1_results:
        raise HTTPException(status_code=503, detail="All council models failed")

    processing_time = round(time.time() - start_time, 2)

    # Reshape into public API response format
    council_responses = [
        {"model": r["model"], "response": r["response"]}
        for r in stage1_results
    ]

    evaluations = [
        {
            "model": r["model"],
            "evaluation": r["ranking"],
            "ranking": r.get("parsed_ranking", []),
        }
        for r in stage2_results
    ]

    return {
        "status": "success",
        "question": body.question,
        "council_responses": council_responses,
        "evaluations": evaluations,
        "aggregate_rankings": metadata.get("aggregate_rankings", []),
        "final_answer": {
            "model": stage3_result.get("model", ""),
            "response": stage3_result.get("response", ""),
        },
        "metadata": {
            "council_models": settings.get_council_models(),
            "chairman_model": settings.get_chairman_model(),
            "stage1_failed": metadata.get("stage1_failed", []),
            "stage2_failed": metadata.get("stage2_failed", []),
            "processing_time_seconds": processing_time,
        },
    }


# ── Admin: API Key Management ───────────────────────────────────────────────

@app.post("/api/admin/api-keys")
async def create_api_key_endpoint(
    body: CreateApiKeyRequest,
    admin: dict = Depends(auth.get_current_admin),
):
    """Create a new API key (admin only). The plaintext key is returned only once."""
    try:
        result = api_keys.create_api_key(name=body.name, rate_limit=body.rate_limit)
        return result
    except Exception as e:
        logger.error(f"Error creating API key: {e}")
        raise HTTPException(status_code=500, detail="Error creating API key")


@app.get("/api/admin/api-keys")
async def list_api_keys_endpoint(admin: dict = Depends(auth.get_current_admin)):
    """List all API keys (admin only). Never returns the full key."""
    return api_keys.list_api_keys()


@app.delete("/api/admin/api-keys/{key_id}")
async def delete_api_key_endpoint(
    key_id: str,
    admin: dict = Depends(auth.get_current_admin),
):
    """Deactivate an API key (admin only)."""
    success = api_keys.delete_api_key(key_id)
    if not success:
        raise HTTPException(status_code=404, detail="API key not found")
    return {"status": "deactivated"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
