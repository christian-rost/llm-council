"""
LLM Council orchestration with PDF support.
"""

import asyncio
import string
from typing import Dict, List, Tuple, Any, Optional

from .config import COUNCIL_MODELS, CHAIRMAN_MODEL
from .openrouter import query_model, query_model_simple


async def stage1_collect_responses(
    user_query: str,
    pdf_data: Optional[str] = None,
    pdf_filename: Optional[str] = None
) -> Dict[str, str]:
    """
    Stage 1: Collect individual responses from all council members.
    PDF is sent to each model if provided.
    """
    async def get_response(model: str) -> Tuple[str, str]:
        try:
            messages = [{"role": "user", "content": user_query}]
            response = await query_model(
                model,
                messages,
                pdf_data=pdf_data,
                pdf_filename=pdf_filename
            )
            return model, response
        except Exception as e:
            return model, f"Error: {str(e)}"
    
    tasks = [get_response(model) for model in COUNCIL_MODELS]
    results = await asyncio.gather(*tasks)
    
    return {model: response for model, response in results}


async def stage2_collect_rankings(
    user_query: str,
    stage1_results: Dict[str, str]
) -> Tuple[Dict[str, Dict], Dict[str, str]]:
    """
    Stage 2: Each model ranks the other models' responses.
    Returns rankings and the label-to-model mapping.
    """
    # Create anonymous labels for responses
    labels = list(string.ascii_uppercase[:len(stage1_results)])
    models = list(stage1_results.keys())
    label_to_model = {label: model for label, model in zip(labels, models)}
    
    # Build the prompt with anonymized responses
    responses_text = ""
    for label, model in zip(labels, models):
        responses_text += f"\n\n**Response {label}:**\n{stage1_results[model]}"
    
    ranking_prompt = f"""You are evaluating responses to this question: "{user_query}"

Here are the responses from different sources:{responses_text}

Please evaluate each response for accuracy, completeness, and insight.
Then provide your ranking from best to worst.

Format your response as:
1. Your evaluation of each response (2-3 sentences each)
2. FINAL RANKING: (list responses from best to worst, e.g., "1. Response B, 2. Response A, 3. Response C")
"""
    
    async def get_ranking(model: str) -> Tuple[str, Dict]:
        try:
            response = await query_model_simple(model, ranking_prompt)
            # Parse ranking from response
            ranking = parse_ranking_from_text(response, labels)
            return model, {"evaluation": response, "ranking": ranking}
        except Exception as e:
            return model, {"evaluation": f"Error: {str(e)}", "ranking": []}
    
    tasks = [get_ranking(model) for model in COUNCIL_MODELS]
    results = await asyncio.gather(*tasks)
    
    return {model: data for model, data in results}, label_to_model


def parse_ranking_from_text(text: str, valid_labels: List[str]) -> List[str]:
    """Extract ranking from model's evaluation text."""
    import re
    
    # Look for "FINAL RANKING:" section
    ranking_match = re.search(r'FINAL RANKING[:\s]*(.*?)(?:\n\n|$)', text, re.IGNORECASE | re.DOTALL)
    if ranking_match:
        ranking_text = ranking_match.group(1)
    else:
        ranking_text = text
    
    # Extract response labels (A, B, C, etc.)
    found_labels = []
    for label in valid_labels:
        pattern = rf'Response\s+{label}\b'
        if re.search(pattern, ranking_text, re.IGNORECASE):
            if label not in found_labels:
                found_labels.append(label)
    
    # If we didn't find enough, try simpler pattern
    if len(found_labels) < len(valid_labels):
        found_labels = []
        for match in re.finditer(r'\b([A-Z])\b', ranking_text):
            label = match.group(1)
            if label in valid_labels and label not in found_labels:
                found_labels.append(label)
    
    return found_labels


def calculate_aggregate_rankings(
    stage2_results: Dict[str, Dict],
    label_to_model: Dict[str, str]
) -> List[Tuple[str, float]]:
    """Calculate aggregate rankings across all evaluators."""
    model_scores = {model: [] for model in label_to_model.values()}
    
    for evaluator, data in stage2_results.items():
        ranking = data.get("ranking", [])
        for position, label in enumerate(ranking):
            if label in label_to_model:
                model = label_to_model[label]
                model_scores[model].append(position + 1)  # 1-indexed position
    
    # Calculate average position (lower is better)
    avg_scores = []
    for model, scores in model_scores.items():
        if scores:
            avg = sum(scores) / len(scores)
            avg_scores.append((model, avg))
        else:
            avg_scores.append((model, float('inf')))
    
    # Sort by average position (ascending)
    avg_scores.sort(key=lambda x: x[1])
    
    return avg_scores


async def stage3_synthesize_final(
    user_query: str,
    stage1_results: Dict[str, str],
    stage2_results: Dict[str, Dict]
) -> Dict[str, str]:
    """
    Stage 3: Chairman synthesizes final response based on all inputs.
    """
    # Compile all responses and rankings
    responses_summary = ""
    for model, response in stage1_results.items():
        model_name = model.split("/")[-1]
        responses_summary += f"\n\n**{model_name}:**\n{response[:1000]}..."  # Truncate for prompt
    
    synthesis_prompt = f"""You are the Chairman of an LLM Council. Your task is to synthesize the best possible answer.

Original question: "{user_query}"

The council members provided these responses:{responses_summary}

Based on all perspectives, provide a comprehensive final answer that:
1. Incorporates the strongest points from each response
2. Resolves any contradictions
3. Provides a clear, well-structured answer

Your synthesis:"""
    
    try:
        response = await query_model_simple(CHAIRMAN_MODEL, synthesis_prompt)
        return {"model": CHAIRMAN_MODEL, "response": response}
    except Exception as e:
        return {"model": CHAIRMAN_MODEL, "response": f"Error: Unable to generate final synthesis. {str(e)}"}


async def run_full_council(
    user_query: str,
    pdf_data: Optional[str] = None,
    pdf_filename: Optional[str] = None
) -> Dict[str, Any]:
    """Run the complete 3-stage council process."""
    # Stage 1: Get individual responses (with PDF if provided)
    stage1_results = await stage1_collect_responses(user_query, pdf_data, pdf_filename)
    
    # Stage 2: Get rankings
    stage2_results, label_to_model = await stage2_collect_rankings(user_query, stage1_results)
    aggregate_rankings = calculate_aggregate_rankings(stage2_results, label_to_model)
    
    # Stage 3: Final synthesis
    stage3_result = await stage3_synthesize_final(user_query, stage1_results, stage2_results)
    
    return {
        "stage1": stage1_results,
        "stage2": stage2_results,
        "stage3": stage3_result,
        "metadata": {
            "label_to_model": label_to_model,
            "aggregate_rankings": aggregate_rankings
        }
    }


async def generate_conversation_title(first_message: str) -> str:
    """Generate a short title for a conversation based on the first message."""
    prompt = f"""Generate a very short title (max 5 words) for a conversation that starts with this message:

"{first_message[:200]}"

Reply with just the title, nothing else."""
    
    try:
        title = await query_model_simple(CHAIRMAN_MODEL, prompt)
        return title.strip().strip('"')[:50]
    except Exception:
        return "New Conversation"
