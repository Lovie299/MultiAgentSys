import json
import logging
import uuid
import os

from pathlib import Path

from django.conf import settings
from django.http import StreamingHttpResponse, JsonResponse, FileResponse
from django.views.decorators.csrf import csrf_exempt

from .freemad.agent import run_freemad_protocol

logger = logging.getLogger(__name__)


@csrf_exempt
async def chat_stream(request):
    """
    Async SSE endpoint. Django 4.2 + Uvicorn (ASGI) support async views
    natively — no manual event-loop bridging needed.
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

    if not user_message:
        return JsonResponse({"error": "Message is required"}, status=400)

    user_id = str(uuid.uuid4())

    async def event_generator():
        try:
            async for update in run_freemad_protocol(
                user_message, guiding_prompt, user_id
            ):
                yield f"data: {json.dumps(update)}\n\n"

        except Exception as e:
            logger.exception("Error in event generator")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

        finally:
            yield "data: [DONE]\n\n"

    response = StreamingHttpResponse(
        event_generator(),
        content_type="text/event-stream",
    )

    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"

    return response


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