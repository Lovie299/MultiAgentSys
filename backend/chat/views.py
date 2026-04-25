import json
import logging
import uuid
import asyncio
import os
import sys  # 🆕 ADD THIS

from pathlib import Path

from django.conf import settings
from django.http import StreamingHttpResponse, JsonResponse, FileResponse
from django.views.decorators.csrf import csrf_exempt

from asgiref.sync import async_to_sync

from .freemad.agent import run_freemad_protocol

# 🆕 ADD THIS BLOCK: Add the root directory to Python path
root_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(root_dir))
from maternal_knowledge_base import get_knowledge_base

logger = logging.getLogger(__name__)

# os.environ["GOOGLE_API_KEY"] = "AIzaSyAvXM3NaC893IbPHnFAkFRuQG0TA9AY698"

# ========== ADD THIS NEW FUNCTION HERE ==========
@csrf_exempt
async def chat_view(request):
    """
    Simple endpoint for non-streaming chat responses using Ollama.
    First checks dataset, then falls back to Ollama's Gemma 3 model.
    """
    if request.method != 'POST':
        return JsonResponse({"error": "Only POST requests are accepted."}, status=405)
    
    try:
        data = json.loads(request.body)
        message = data.get('message', '').strip()
        
        if not message:
            return JsonResponse({"error": "Message is required"}, status=400)
        
        # First, check if the question is in the dataset
        kb = get_knowledge_base()
        dataset_match = kb.find_best_match(message)
        
        # If high confidence match found (above 70%), return dataset answer
        if dataset_match["found"] and dataset_match["confidence"] > 0.7:
            return JsonResponse({
                "response": dataset_match["answer"],
                "matched_question": dataset_match["matched_question"],
                "confidence": dataset_match["confidence"],
                "source": "Mother Dataset (Verified Medical Data)",
                "model_used": "dataset"
            })
        
        # Otherwise, use Ollama for AI-generated response
        import aiohttp
        
        # Get Ollama configuration from environment
        ollama_api_base = os.getenv("API_BASE", "http://localhost:11434")
        ollama_model = os.getenv("GEN_MODEL_NAME", "gemma3:27b-cloud")
        
        logger.info(f"Calling Ollama with model: {ollama_model}")
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{ollama_api_base}/api/generate",
                json={
                    "model": ollama_model,
                    "prompt": f"You are a maternal health expert. Please provide a clear, accurate, and helpful answer to this question: {message}",
                    "stream": False,
                    "options": {
                        "temperature": 0.7,
                        "top_p": 0.9
                    }
                },
                timeout=aiohttp.ClientTimeout(total=120)
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    ai_response = result.get("response", "No response generated")
                    
                    return JsonResponse({
                        "response": ai_response,
                        "source": f"AI Generated (Ollama - {ollama_model})",
                        "dataset_match_found": dataset_match["found"],
                        "dataset_confidence": dataset_match.get("confidence", 0),
                        "model_used": "ollama"
                    })
                else:
                    error_text = await response.text()
                    logger.error(f"Ollama API error: {response.status} - {error_text}")
                    return JsonResponse({
                        "error": f"Ollama API error: {response.status}",
                        "response": "Sorry, I'm having trouble generating a response right now. Please try again."
                    }, status=500)
        
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except aiohttp.ClientError as e:
        logger.exception("Ollama connection error")
        return JsonResponse({
            "error": "Cannot connect to Ollama. Make sure Ollama is running.",
            "response": "The AI service is currently unavailable. Please make sure Ollama is running with 'ollama serve'"
        }, status=503)
    except Exception as e:
        logger.exception("Error in chat_view")
        return JsonResponse({
            "error": str(e),
            "response": "An unexpected error occurred. Please try again."
        }, status=500)
# ========== END OF NEW FUNCTION ==========

# 🆕 ADD THIS: Non-streaming endpoint for simple Q&A
@csrf_exempt
def quick_answer(request):
    """
    Simple endpoint that returns just the dataset answer without full debate.
    Useful for testing or when you don't need multi-agent reasoning.
    """
    if request.method != "POST":
        return JsonResponse({"error": "Only POST requests are accepted."}, status=405)
    
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    
    user_question = body.get("message", "").strip()
    
    if not user_question:
        return JsonResponse({"error": "Message is required"}, status=400)
    
    # Get dataset answer
    kb = get_knowledge_base()
    match = kb.find_best_match(user_question)
    
    if match["found"]:
        return JsonResponse({
            "answer": match["answer"],
            "matched_question": match["matched_question"],
            "confidence": match["confidence"],
            "source": "Mother Dataset (Verified Medical Data)",
            "disclaimer": kb.get_disclaimer()
        })
    else:
        return JsonResponse({
            "answer": None,
            "message": "Question not found in the verified dataset. Please use the streaming endpoint for AI-generated responses.",
            "confidence": 0,
            "source": "No match found"
        }, status=404)
        
        


# 🆕 MODIFY THIS: Add dataset grounding to chat_stream
@csrf_exempt
def chat_stream(request):
    """
    Proper async SSE handling in Django.
    🆕 Now includes dataset grounding information in the stream.
    """

    if request.method != "POST":
        return JsonResponse({"error": "Only POST requests are accepted."}, status=405)

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    user_message = body.get("message", "").strip()
    guiding_prompt = body.get(
        "guiding_prompt",
        "Evaluate your peers' logic carefully. Correct any errors you find.",
    )
    
    # Optional: Get dataset info first (for logging/initial response)
    include_dataset_info = body.get("include_dataset_info", True)

    if not user_message:
        return JsonResponse({"error": "Message is required"}, status=400)

    user_id = str(uuid.uuid4())
    
    # 🆕 Get dataset match for this question
    kb = get_knowledge_base()
    dataset_match = kb.find_best_match(user_message)

    # ─────────────────────────────────────────────────────────────
    # 🔥 KEY PART: async generator (MODIFIED to include dataset info)
    # ─────────────────────────────────────────────────────────────
    async def async_event_generator():
        try:
            # 🆕 Send dataset match info first (if requested)
            if include_dataset_info:
                yield f"data: {json.dumps({
                    'type': 'dataset_info',
                    'found': dataset_match['found'],
                    'matched_question': dataset_match.get('matched_question'),
                    'confidence': dataset_match.get('confidence', 0),
                    'verified_answer': dataset_match.get('answer') if dataset_match.get('found') else None,
                    'disclaimer': kb.get_disclaimer()
                })}\n\n"
            
            # Then continue with the debate
            async for update in run_freemad_protocol(
                user_message, 
                guiding_prompt, 
                user_id
            ):
                yield f"data: {json.dumps(update)}\n\n"

        except Exception as e:
            logger.exception("Error in async generator")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

        finally:
            yield "data: [DONE]\n\n"

    # ─────────────────────────────────────────────────────────────
    # 🔥 BRIDGE async → sync
    # ─────────────────────────────────────────────────────────────
    def sync_event_generator():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async_gen = async_event_generator()

        try:
            while True:
                chunk = loop.run_until_complete(async_gen.__anext__())
                yield chunk
        except StopAsyncIteration:
            pass
        finally:
            loop.close()

    response = StreamingHttpResponse(
        sync_event_generator(),
        content_type="text/event-stream",
    )

    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"

    return response


# 🆕 ADD THIS: Endpoint to search the dataset
@csrf_exempt
def search_dataset(request):
    """
    Search the Mother dataset for questions matching a query.
    Returns a list of matching Q&A pairs.
    """
    if request.method == "GET":
        query = request.GET.get("q", "").strip()
        limit = int(request.GET.get("limit", 5))
        
        if not query:
            return JsonResponse({"error": "Search query 'q' is required"}, status=400)
        
        kb = get_knowledge_base()
        
        # Simple search - find matches
        results = []
        for item in kb.qa_pairs:
            if query.lower() in item["question"].lower():
                results.append({
                    "question": item["question"],
                    "answer_preview": item["answer"][:200] + "..." if len(item["answer"]) > 200 else item["answer"]
                })
                if len(results) >= limit:
                    break
        
        return JsonResponse({
            "query": query,
            "count": len(results),
            "results": results
        })
    
    return JsonResponse({"error": "Only GET requests are accepted."}, status=405)


# 🆕 ADD THIS: Endpoint to get dataset statistics
@csrf_exempt
def dataset_stats(request):
    """
    Returns statistics about the Mother dataset.
    """
    if request.method == "GET":
        kb = get_knowledge_base()
        
        return JsonResponse({
            "total_qa_pairs": len(kb.qa_pairs),
            "disclaimer": kb.get_disclaimer(),
            "sample_questions": [item["question"] for item in kb.qa_pairs[:10]]
        })
    
    return JsonResponse({"error": "Only GET requests are accepted."}, status=405)


# ─────────────────────────────────────────────────────────────
# FRONTEND VIEW (unchanged)
# ─────────────────────────────────────────────────────────────

def frontend(request):
    index_path = Path(settings.FRONTEND_BUILD_DIR) / "index.html"

    if not index_path.exists():
        return JsonResponse(
            {
                "error": "React build not found. Run 'npm run build' in frontend."
            },
            status=503,
        )

    return FileResponse(open(index_path, "rb"))