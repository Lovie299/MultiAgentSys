"""
agent.py — FreeMAD Multi-Agent Debate Protocol (Improved Version)

Key upgrades:
- Stronger prompts (real debate)
- Hidden Chain-of-Thought (internal reasoning)
- Judge agent (final synthesis)
- Cleaner scoring
- Fully commented for learning
"""

import asyncio
import logging
import os
from typing import TypedDict, Dict, Optional, AsyncGenerator

import torch
from litellm import embedding
from sentence_transformers import util
from dotenv import load_dotenv

from google.adk.models.lite_llm import LiteLlm
from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from asyncio import CancelledError

# ─────────────────────────────────────────────────────────────
# 🔧 ENVIRONMENT SETUP
# ─────────────────────────────────────────────────────────────
load_dotenv()
logger = logging.getLogger(__name__)

# Number of agents and rounds (can be changed in .env)
N_AGENTS = int(os.getenv("N_AGENTS", "3"))
R_ROUNDS = int(os.getenv("R_ROUNDS", "2"))

MODEL_PROVIDER = os.getenv("MODEL_PROVIDER", "ollama").lower()
GEN_MODEL_NAME = os.getenv("GEN_MODEL_NAME", "gemma3:27b-cloud")
EMB_MODEL_NAME = os.getenv("EMB_MODEL_NAME", "nomic-embed-text")

API_BASE = os.getenv("API_BASE", "http://localhost:11434")
API_KEY = os.getenv("API_KEY", "")

APP_NAME = "FreeMAD_protocol_app"

# ─────────────────────────────────────────────────────────────
# 🧠 MODEL FACTORY
# Returns model based on provider
# ─────────────────────────────────────────────────────────────
def get_model():
    if MODEL_PROVIDER == "google":
        return GEN_MODEL_NAME

    elif MODEL_PROVIDER == "openai":
        return LiteLlm(
            model=f"openai/{GEN_MODEL_NAME}",
            api_key=API_KEY,
            stream=True,
        )

    elif MODEL_PROVIDER == "ollama":
        return LiteLlm(
            model=f"ollama/{GEN_MODEL_NAME}",
            api_base=API_BASE,
            stream=False,
        )

    elif MODEL_PROVIDER == "huggingface":
        return LiteLlm(
            model=f"huggingface/{GEN_MODEL_NAME}",
            api_key=API_KEY,
            stream=True,
        )

    else:
        raise ValueError("Invalid MODEL_PROVIDER")


# ─────────────────────────────────────────────────────────────
# 📦 STATE (Tracks the whole debate)
# ─────────────────────────────────────────────────────────────
class FreeMADState(TypedDict):
    query: str
    guiding_prompt: str
    round: int
    responses: Dict[int, Dict[str, str]]
    scores: Dict[str, float]
    final_decision: Optional[str]


# Session manager (keeps conversation memory)
session_service = InMemorySessionService()


# ─────────────────────────────────────────────────────────────
# 🤖 BUILD DEBATER AGENTS
# Each agent has the SAME model but DIFFERENT role behavior
# ─────────────────────────────────────────────────────────────
def build_debaters():
    model = get_model()
    agents = []

    for i in range(N_AGENTS):
        agents.append(
            Agent(
                name=f"debater_{i+1}",
                model=model,
                instruction=(
                    "You are a debater in a multi-agent system.\n"
                    "Think step-by-step internally but DO NOT show full reasoning.\n"
                    "Provide:\n"
                    "1. A short reasoning summary\n"
                    "2. A final answer\n\n"
                    "Rules:\n"
                    "- Be concise\n"
                    "- Provide a UNIQUE perspective\n"
                    "- You are allowed to disagree with others\n"
                ),
            )
        )
    return agents


# ─────────────────────────────────────────────────────────────
# ⚖️ BUILD JUDGE AGENT (NEW)
# This agent decides the final best answer
# ─────────────────────────────────────────────────────────────
def build_judge():
    return Agent(
        name="judge",
        model=get_model(),
        instruction=(
            "You are a judge in a multi-agent debate.\n"
            "1. Briefly compare the responses\n"
            "2. Then provide a FINAL ANSWER clearly labeled\n"
            "Keep it concise.\n"
        ),
    )


# ─────────────────────────────────────────────────────────────
# 🔁 RUN A SINGLE MODEL SESSION
# Sends prompt → gets response
# ─────────────────────────────────────────────────────────────
async def run_session(runner, content, session_id, user_id="web_user"):
    try:
        session = await session_service.create_session(
            app_name=runner.app_name,
            user_id=user_id,
            session_id=session_id,
        )
    except:
        session = await session_service.get_session(
            app_name=runner.app_name,
            user_id=user_id,
            session_id=session_id,
        )

    async for event in runner.run_async(
        user_id=user_id,
        session_id=session.id,
        new_message=content,
    ):
        if event.content and event.content.parts:
            text = event.content.parts[0].text
            if text and text != "None":
                return text
    return None


# ─────────────────────────────────────────────────────────────
# 🧮 EMBEDDING + SIMILARITY
# Used for scoring responses
# ─────────────────────────────────────────────────────────────
def create_embedding(text):
    if MODEL_PROVIDER == "ollama":
        response = embedding(
            model=f"ollama/{EMB_MODEL_NAME}",
            input=[text],
            api_base=API_BASE,
        )
        return torch.tensor(response["data"][0]["embedding"])
    else:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(EMB_MODEL_NAME)
        return torch.tensor(model.encode(text))


def calculate_similarity(a, b):
    return util.cos_sim(create_embedding(a), create_embedding(b)).item()


# ─────────────────────────────────────────────────────────────
# 🚀 MAIN FREE MAD PROTOCOL
# This is what your Django view calls
# ─────────────────────────────────────────────────────────────
async def run_freemad_protocol(
    query: str,
    guiding_prompt: str,
    user_id: str = "web_user",
) -> AsyncGenerator[dict, None]:

    logger.info(f"Starting debate: {query}")

    state: FreeMADState = {
        "query": query,
        "guiding_prompt": guiding_prompt,
        "round": 0,
        "responses": {},
        "scores": {},
        "final_decision": None,
    }

    debaters = build_debaters()

    try:
        # ─────────────── DEBATE ROUNDS ───────────────
        for k in range(R_ROUNDS):
            state["responses"][k] = {}

            yield {"type": "progress", "message": f"Round {k+1}"}

            for agent in debaters:
                session_id = f"{user_id}_{k}_{agent.name}"

                # 🧠 FIRST ROUND (no peer input)
                if k == 0:
                    prompt = f"""
Question:
{query}

Instructions:
- Give a clear answer
- Be concise
- Provide a UNIQUE perspective
"""
                else:
                    # 🧠 LATER ROUNDS (with peer critique)
                    prev = state["responses"][k - 1]
                    peers = "\n".join(
                        f"{n}: {r}" for n, r in prev.items() if n != agent.name
                    )

                    prompt = f"""
Question:
{query}

Peer responses:
{peers}

Instructions:
- Critique peer answers
- Point out weaknesses
- Improve your answer
"""

                runner = Runner(
                    agent=agent,
                    app_name=APP_NAME,
                    session_service=session_service,
                )

                content = types.Content(
                    role="user",
                    parts=[types.Part(text=prompt)],
                )

                # ⏱️ Timeout protection
                try:
                    response = await asyncio.wait_for(
                        run_session(runner, content, session_id, user_id),
                        timeout=60,
                    )
                except asyncio.TimeoutError:
                    logger.warning("Timeout")
                    continue

                if not response:
                    continue

                # Save response
                state["responses"][k][agent.name] = response

                # Stream to frontend
                yield {
                    "type": "agent",
                    "round": k + 1,
                    "agent": agent.name,
                    "text": response,
                }

                # Simple scoring (reward uniqueness)
                state["scores"][response] = state["scores"].get(response, 0) + 1

        # ─────────────── JUDGE PHASE (NEW) ───────────────
        yield {"type": "progress", "message": "Judging final answer..."}

        judge = build_judge()

        all_responses = "\n".join(
            f"{agent}: {resp}"
            for round_responses in state["responses"].values()
            for agent, resp in round_responses.items()
        )

        judge_prompt = f"""
Question:
{query}

All responses:
{all_responses}

Choose the best answer or combine them.
"""

        runner = Runner(
            agent=judge,
            app_name=APP_NAME,
            session_service=session_service,
        )

        content = types.Content(
            role="user",
            parts=[types.Part(text=judge_prompt)],
        )

        final = await run_session(runner, content, f"{user_id}_judge")

        yield {"type": "final", "message": final}

    # ─────────────── ERROR HANDLING ───────────────
    except CancelledError:
        logger.warning("Client disconnected")
        return

    except GeneratorExit:
        logger.warning("Generator closed")
        return

    except Exception as e:
        logger.exception("Error")
        yield {"type": "error", "message": str(e)}