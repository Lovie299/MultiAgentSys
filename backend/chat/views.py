import json
import logging
import uuid
import asyncio
import os

from pathlib import Path

from django.conf import settings
from django.http import StreamingHttpResponse, JsonResponse, FileResponse
from django.views.decorators.csrf import csrf_exempt

from asgiref.sync import async_to_sync

from .freemad.agent import run_freemad_protocol

logger = logging.getLogger(__name__)

os.environ["GOOGLE_API_KEY"] = "AIzaSyAvXM3NaC893IbPHnFAkFRuQG0TA9AY698"


@csrf_exempt
def chat_stream(request):   # ⚠️ NOTE: this is NOW sync
    """
    Proper async SSE handling in Django.
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

    # ─────────────────────────────────────────────────────────────
    # 🔥 KEY PART: async generator
    # ─────────────────────────────────────────────────────────────
    async def async_event_generator():
        try:
            async for update in run_freemad_protocol(
                user_message, guiding_prompt, user_id
            ):
                yield f"data: {json.dumps(update)}\n\n"

        except Exception as e:
            logger.exception("Error in async generator")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

        finally:
            yield "data: [DONE]\n\n"

    # ─────────────────────────────────────────────────────────────
    # 🔥 BRIDGE async → sync (THIS FIXES YOUR ERROR)
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