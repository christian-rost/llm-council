"""Supabase-based storage for conversations."""

import uuid
from typing import List, Dict, Any, Optional
from .database import supabase


def create_conversation(conversation_id: str, user_id: Optional[str] = None) -> Dict[str, Any]:
    """Create a new conversation."""
    conv_data = {
        "id": conversation_id,
        "title": "New Conversation",
        "user_id": user_id,
    }

    result = supabase.table("conversations").insert(conv_data).execute()
    conv = result.data[0]
    # Return in expected format with empty messages list
    return {
        "id": conv["id"],
        "created_at": conv["created_at"],
        "title": conv["title"],
        "user_id": conv["user_id"],
        "messages": [],
    }


def get_conversation(conversation_id: str) -> Optional[Dict[str, Any]]:
    """Load a conversation with all its messages."""
    conv_result = (
        supabase.table("conversations")
        .select("*")
        .eq("id", conversation_id)
        .execute()
    )
    if not conv_result.data:
        return None

    conv = conv_result.data[0]

    # Fetch messages ordered by creation time
    msg_result = (
        supabase.table("messages")
        .select("*")
        .eq("conversation_id", conversation_id)
        .order("created_at")
        .execute()
    )

    # Build messages list in the format the frontend expects
    messages = []
    for msg in msg_result.data:
        if msg["role"] == "user":
            messages.append({
                "role": "user",
                "content": msg["content"],
            })
        else:
            message = {"role": "assistant"}
            if msg.get("stage1") is not None:
                message["stage1"] = msg["stage1"]
            if msg.get("stage2") is not None:
                message["stage2"] = msg["stage2"]
            if msg.get("stage3") is not None:
                message["stage3"] = msg["stage3"]
            if msg.get("metadata") is not None:
                message["metadata"] = msg["metadata"]
            if msg.get("content") is not None:
                message["content"] = msg["content"]
            messages.append(message)

    return {
        "id": conv["id"],
        "created_at": conv["created_at"],
        "title": conv["title"],
        "user_id": conv["user_id"],
        "messages": messages,
    }


def delete_conversation(conversation_id: str) -> bool:
    """Delete a conversation (CASCADE deletes messages)."""
    result = (
        supabase.table("conversations")
        .delete()
        .eq("id", conversation_id)
        .execute()
    )
    return len(result.data) > 0


def list_conversations(user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """List all conversations (metadata only)."""
    query = supabase.table("conversations").select("id,created_at,title,user_id")

    if user_id is not None:
        query = query.eq("user_id", user_id)

    query = query.order("created_at", desc=True)
    conv_result = query.execute()

    conversations = []
    for conv in conv_result.data:
        # Count messages for this conversation
        count_result = (
            supabase.table("messages")
            .select("id", count="exact")
            .eq("conversation_id", conv["id"])
            .execute()
        )
        message_count = count_result.count if count_result.count is not None else 0

        conversations.append({
            "id": conv["id"],
            "created_at": conv["created_at"],
            "title": conv["title"],
            "message_count": message_count,
        })

    return conversations


def add_user_message(conversation_id: str, content: str):
    """Add a user message to a conversation."""
    supabase.table("messages").insert({
        "conversation_id": conversation_id,
        "role": "user",
        "content": content,
    }).execute()


def add_assistant_message(
    conversation_id: str,
    stage1: List[Dict[str, Any]],
    stage2: List[Dict[str, Any]],
    stage3: Dict[str, Any],
    metadata: Optional[Dict[str, Any]] = None,
):
    """Add an assistant message with all 3 stages to a conversation."""
    msg_data = {
        "conversation_id": conversation_id,
        "role": "assistant",
        "stage1": stage1,
        "stage2": stage2,
        "stage3": stage3,
    }
    if metadata:
        msg_data["metadata"] = metadata

    result = supabase.table("messages").insert(msg_data).execute()
    return result.data[0]["id"]


def update_conversation_title(conversation_id: str, title: str):
    """Update the title of a conversation."""
    supabase.table("conversations").update({"title": title}).eq("id", conversation_id).execute()
