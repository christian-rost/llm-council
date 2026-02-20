"""3-stage XQT5AIs orchestration with PDF support."""

import asyncio
import logging
from typing import List, Dict, Any, Tuple, Optional
from .providers import query_model
from .settings import get_council_models, get_chairman_model, get_chairman_fallback_model

logger = logging.getLogger(__name__)

# Stage 3 resilience defaults: initial attempt + retries
CHAIRMAN_MAX_ATTEMPTS = 3
CHAIRMAN_RETRY_BACKOFF_SECONDS = 1.0


def _normalize_council_slots(raw_models: List[Any]) -> List[Dict[str, str]]:
    """Normalize council model config into slot objects with primary/fallback."""
    slots: List[Dict[str, str]] = []
    for entry in raw_models:
        if isinstance(entry, str):
            primary = entry.strip()
            if primary:
                slots.append({"primary": primary, "fallback": ""})
            continue
        if isinstance(entry, dict):
            primary = str(entry.get("primary", "")).strip()
            fallback = str(entry.get("fallback", "")).strip()
            if primary:
                slots.append({"primary": primary, "fallback": fallback})
    return slots


async def _query_slots_with_optional_fallback(
    slots: List[Dict[str, str]],
    messages: List[Dict[str, Any]],
    pdf_data: Optional[str] = None,
    pdf_filename: Optional[str] = None,
    web_search: bool = False,
) -> Tuple[List[Dict[str, Any]], List[str], Dict[str, Any]]:
    """Query council slots; each slot can fail over from primary to fallback."""
    if not slots:
        return [], [], {}

    primary_tasks = [
        query_model(
            slot["primary"],
            messages,
            pdf_data=pdf_data,
            pdf_filename=pdf_filename,
            web_search=web_search,
        )
        for slot in slots
    ]
    primary_responses = await asyncio.gather(*primary_tasks)

    slot_outputs: List[Optional[Dict[str, Any]]] = [None] * len(slots)
    failed_models: List[str] = []
    raw_responses: Dict[str, Any] = {}

    fallback_indices: List[int] = []
    fallback_tasks = []

    for idx, (slot, response) in enumerate(zip(slots, primary_responses)):
        primary_model = slot["primary"]
        fallback_model = slot.get("fallback", "")
        if response is not None:
            raw_responses[primary_model] = response
            slot_outputs[idx] = {
                "model": primary_model,
                "primary_model": primary_model,
                "fallback_model": fallback_model or None,
                "fallback_used": False,
                "response": response.get("content", ""),
            }
            continue
        if fallback_model and fallback_model != primary_model:
            fallback_indices.append(idx)
            fallback_tasks.append(
                query_model(
                    fallback_model,
                    messages,
                    pdf_data=pdf_data,
                    pdf_filename=pdf_filename,
                    web_search=web_search,
                )
            )
        else:
            failed_models.append(primary_model)

    if fallback_tasks:
        fallback_responses = await asyncio.gather(*fallback_tasks)
        for idx, fallback_response in zip(fallback_indices, fallback_responses):
            slot = slots[idx]
            primary_model = slot["primary"]
            fallback_model = slot["fallback"]
            if fallback_response is not None:
                raw_responses[fallback_model] = fallback_response
                slot_outputs[idx] = {
                    "model": fallback_model,
                    "primary_model": primary_model,
                    "fallback_model": fallback_model,
                    "fallback_used": True,
                    "response": fallback_response.get("content", ""),
                }
            else:
                failed_models.append(primary_model)

    final_results = [output for output in slot_outputs if output is not None]

    return final_results, failed_models, raw_responses


async def _query_with_retries(
    model_id: str,
    messages: List[Dict[str, Any]],
    max_attempts: int = CHAIRMAN_MAX_ATTEMPTS,
    base_backoff_seconds: float = CHAIRMAN_RETRY_BACKOFF_SECONDS,
) -> Optional[Dict[str, Any]]:
    """Query a single model with retries and exponential backoff."""
    attempts = max(1, max_attempts)
    for attempt in range(1, attempts + 1):
        response = await query_model(model_id, messages)
        if response is not None:
            return response
        if attempt < attempts:
            delay = base_backoff_seconds * (2 ** (attempt - 1))
            logger.warning(
                f"Stage3 attempt {attempt}/{attempts} failed for {model_id}; retrying in {delay:.1f}s"
            )
            await asyncio.sleep(delay)
    return None


async def stage1_collect_responses(
    user_query: str,
    pdf_data: Optional[str] = None,
    pdf_filename: Optional[str] = None,
    web_search: bool = False,
) -> Tuple[List[Dict[str, Any]], List[str], Dict[str, Any]]:
    """
    Stage 1: Collect individual responses from all council models.

    Args:
        user_query: The user's question
        pdf_data: Optional base64-encoded PDF data
        pdf_filename: Optional filename for the PDF
        web_search: Enable web search for providers that support it

    Returns:
        Tuple of (results list, failed_models list, raw_responses dict)
    """
    messages = [{"role": "user", "content": user_query}]

    # Query all council slots (with PDF if provided)
    council_slots = _normalize_council_slots(get_council_models())
    stage1_results, failed_models, raw_responses = await _query_slots_with_optional_fallback(
        council_slots,
        messages,
        pdf_data=pdf_data,
        pdf_filename=pdf_filename,
        web_search=web_search,
    )

    return stage1_results, failed_models, raw_responses


async def stage2_collect_rankings(
    user_query: str,
    stage1_results: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], Dict[str, str], List[str], Dict[str, Any]]:
    """
    Stage 2: Each model ranks the anonymized responses.

    Args:
        user_query: The original user query
        stage1_results: Results from Stage 1

    Returns:
        Tuple of (rankings list, label_to_model mapping, failed_models list, raw_responses dict)
    """
    # Create anonymized labels for responses (Response A, Response B, etc.)
    labels = [chr(65 + i) for i in range(len(stage1_results))]  # A, B, C, ...

    # Create mapping from label to model name
    label_to_model = {
        f"Response {label}": result['model']
        for label, result in zip(labels, stage1_results)
    }

    # Build the ranking prompt
    responses_text = "\n\n".join([
        f"Response {label}:\n{result['response']}"
        for label, result in zip(labels, stage1_results)
    ])

    ranking_prompt = f"""You are evaluating different responses to the following question:

Question: {user_query}

Here are the responses from different models (anonymized):

{responses_text}

Your task:
1. First, evaluate each response individually. For each response, explain what it does well and what it does poorly.
2. Then, at the very end of your response, provide a final ranking.

IMPORTANT: Your final ranking MUST be formatted EXACTLY as follows:
- Start with the line "FINAL RANKING:" (all caps, with colon)
- Then list the responses from best to worst as a numbered list
- Each line should be: number, period, space, then ONLY the response label (e.g., "1. Response A")
- Do not add any other text or explanations in the ranking section

Example of the correct format for your ENTIRE response:

Response A provides good detail on X but misses Y...
Response B is accurate but lacks depth on Z...
Response C offers the most comprehensive answer...

FINAL RANKING:
1. Response C
2. Response A
3. Response B

Now provide your evaluation and ranking:"""

    messages = [{"role": "user", "content": ranking_prompt}]

    # Get rankings from council slots with optional fallback (no PDF needed for ranking)
    council_slots = _normalize_council_slots(get_council_models())
    slot_results, failed_models, raw_responses = await _query_slots_with_optional_fallback(
        council_slots,
        messages,
    )

    stage2_results = []
    for slot_result in slot_results:
        full_text = slot_result.get("response", "")
        parsed = parse_ranking_from_text(full_text)
        stage2_results.append({
            "model": slot_result["model"],
            "primary_model": slot_result.get("primary_model"),
            "fallback_model": slot_result.get("fallback_model"),
            "fallback_used": slot_result.get("fallback_used", False),
            "ranking": full_text,
            "parsed_ranking": parsed
        })

    return stage2_results, label_to_model, failed_models, raw_responses


async def stage3_synthesize_final(
    user_query: str,
    stage1_results: List[Dict[str, Any]],
    stage2_results: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Stage 3: Chairman synthesizes final response.

    Args:
        user_query: The original user query
        stage1_results: Individual model responses from Stage 1
        stage2_results: Rankings from Stage 2

    Returns:
        Dict with 'model' and 'response' keys
    """
    # Build comprehensive context for chairman
    stage1_text = "\n\n".join([
        f"Model: {result['model']}\nResponse: {result['response']}"
        for result in stage1_results
    ])

    stage2_text = "\n\n".join([
        f"Model: {result['model']}\nRanking: {result['ranking']}"
        for result in stage2_results
    ])

    chairman_prompt = f"""You are the Chairman of XQT5AIs. Multiple AI models have provided responses to a user's question, and then ranked each other's responses.

Original Question: {user_query}

STAGE 1 - Individual Responses:
{stage1_text}

STAGE 2 - Peer Rankings:
{stage2_text}

Your task as Chairman is to synthesize all of this information into a single, comprehensive, accurate answer to the user's original question. Consider:
- The individual responses and their insights
- The peer rankings and what they reveal about response quality
- Any patterns of agreement or disagreement

Provide a clear, well-reasoned final answer that represents the council's collective wisdom:"""

    messages = [{"role": "user", "content": chairman_prompt}]

    # Query chairman model with configured fallback (no PDF needed for synthesis)
    chairman_model = get_chairman_model()
    fallback_model = get_chairman_fallback_model()
    attempted_models = [chairman_model]

    response = await _query_with_retries(chairman_model, messages)
    used_model = chairman_model
    fallback_used = False

    if response is None and fallback_model and fallback_model != chairman_model:
        attempted_models.append(fallback_model)
        response = await _query_with_retries(fallback_model, messages)
        if response is not None:
            used_model = fallback_model
            fallback_used = True

    if response is None:
        return {
            "model": chairman_model,
            "primary_model": chairman_model,
            "fallback_model": fallback_model,
            "fallback_used": False,
            "attempted_models": attempted_models,
            "response": "Error: Unable to generate final synthesis.",
            "raw_response": None,
        }

    return {
        "model": used_model,
        "primary_model": chairman_model,
        "fallback_model": fallback_model,
        "fallback_used": fallback_used,
        "attempted_models": attempted_models,
        "response": response.get('content', ''),
        "raw_response": response,
    }


def parse_ranking_from_text(ranking_text: str) -> List[str]:
    """
    Parse the FINAL RANKING section from the model's response.

    Args:
        ranking_text: The full text response from the model

    Returns:
        List of response labels in ranked order
    """
    import re

    # Look for "FINAL RANKING:" section
    if "FINAL RANKING:" in ranking_text:
        # Extract everything after "FINAL RANKING:"
        parts = ranking_text.split("FINAL RANKING:")
        if len(parts) >= 2:
            ranking_section = parts[1]
            # Try to extract numbered list format (e.g., "1. Response A")
            # This pattern looks for: number, period, optional space, "Response X"
            numbered_matches = re.findall(r'\d+\.\s*Response [A-Z]', ranking_section)
            if numbered_matches:
                # Extract just the "Response X" part
                return [re.search(r'Response [A-Z]', m).group() for m in numbered_matches]

            # Fallback: Extract all "Response X" patterns in order
            matches = re.findall(r'Response [A-Z]', ranking_section)
            return matches

    # Fallback: try to find any "Response X" patterns in order
    matches = re.findall(r'Response [A-Z]', ranking_text)
    return matches


def calculate_aggregate_rankings(
    stage2_results: List[Dict[str, Any]],
    label_to_model: Dict[str, str]
) -> List[Dict[str, Any]]:
    """
    Calculate aggregate rankings across all models.

    Args:
        stage2_results: Rankings from each model
        label_to_model: Mapping from anonymous labels to model names

    Returns:
        List of dicts with model name and average rank, sorted best to worst
    """
    from collections import defaultdict

    # Track positions for each model
    model_positions = defaultdict(list)

    for ranking in stage2_results:
        ranking_text = ranking['ranking']

        # Parse the ranking from the structured format
        parsed_ranking = parse_ranking_from_text(ranking_text)

        for position, label in enumerate(parsed_ranking, start=1):
            if label in label_to_model:
                model_name = label_to_model[label]
                model_positions[model_name].append(position)

    # Calculate average position for each model
    aggregate = []
    for model, positions in model_positions.items():
        if positions:
            avg_rank = sum(positions) / len(positions)
            aggregate.append({
                "model": model,
                "average_rank": round(avg_rank, 2),
                "rankings_count": len(positions)
            })

    # Sort by average rank (lower is better)
    aggregate.sort(key=lambda x: x['average_rank'])

    return aggregate


async def generate_conversation_title(user_query: str) -> str:
    """
    Generate a short title for a conversation based on the first user message.

    Args:
        user_query: The first user message

    Returns:
        A short title (3-5 words)
    """
    title_prompt = f"""Generate a very short title (3-5 words maximum) that summarizes the following question.
The title should be concise and descriptive. Do not use quotes or punctuation in the title.

Question: {user_query}

Title:"""

    messages = [{"role": "user", "content": title_prompt}]

    # Use gemini-2.5-flash for title generation (fast and cheap)
    response = await query_model("google/gemini-2.5-flash", messages, timeout=30.0)

    if response is None:
        # Fallback to a generic title
        return "New Conversation"

    title = response.get('content', 'New Conversation').strip()

    # Clean up the title - remove quotes, limit length
    title = title.strip('"\'')

    # Truncate if too long
    if len(title) > 50:
        title = title[:47] + "..."

    return title


async def run_full_council(
    user_query: str,
    pdf_data: Optional[str] = None,
    pdf_filename: Optional[str] = None,
    web_search: bool = False,
) -> Tuple[List, List, Dict, Dict]:
    """
    Run the complete 3-stage council process.

    Args:
        user_query: The user's question
        pdf_data: Optional base64-encoded PDF data
        pdf_filename: Optional filename for the PDF
        web_search: Enable web search for Stage 1 (providers that support it)

    Returns:
        Tuple of (stage1_results, stage2_results, stage3_result, metadata)
    """
    # Stage 1: Collect individual responses (with PDF if provided)
    stage1_results, stage1_failed, stage1_raw = await stage1_collect_responses(
        user_query,
        pdf_data=pdf_data,
        pdf_filename=pdf_filename,
        web_search=web_search,
    )

    # If no models responded successfully, return error
    if not stage1_results:
        return [], [], {
            "model": "error",
            "response": "All models failed to respond. Please try again."
        }, {"stage1_failed": stage1_failed}

    # Stage 2: Collect rankings (no PDF needed - working with text responses)
    stage2_results, label_to_model, stage2_failed, stage2_raw = await stage2_collect_rankings(user_query, stage1_results)

    # Calculate aggregate rankings
    aggregate_rankings = calculate_aggregate_rankings(stage2_results, label_to_model)

    # Stage 3: Synthesize final answer (no PDF needed - working with stage results)
    stage3_result = await stage3_synthesize_final(
        user_query,
        stage1_results,
        stage2_results
    )

    # Prepare metadata
    metadata = {
        "label_to_model": label_to_model,
        "aggregate_rankings": aggregate_rankings,
        "stage1_failed": stage1_failed,
        "stage2_failed": stage2_failed,
        "stage1_raw_responses": stage1_raw,
        "stage2_raw_responses": stage2_raw,
        "stage3_raw_response": stage3_result.get("raw_response"),
    }

    return stage1_results, stage2_results, stage3_result, metadata
