"""
agent.py — FreeMAD Multi-Agent Debate Protocol (Improved Version)
With Mother Dataset Integration for Grounded Maternal Health Responses

Key upgrades:
- Stronger prompts (real debate)
- Hidden Chain-of-Thought (internal reasoning)
- Judge agent (final synthesis)
- Cleaner scoring
- FULLY COMMENTED for learning
- ✅ Mother Dataset grounding for evidence-based responses
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
# 🆕 MOTHER DATASET INTEGRATION
# ─────────────────────────────────────────────────────────────
from pathlib import Path
import json

class MotherDataset:
    """
    Loads and queries the Mother maternal health dataset.
    Provides grounded medical answers for agent debates.
    """
    def __init__(self, data_path: str = "data/"):
        # Look for data folder relative to this file
        base_dir = Path(__file__).parent.parent
        data_dir = base_dir / data_path
        
        qa_file = data_dir / "mother_question_and_answer_pairs_data.json"
        
        if not qa_file.exists():
            print(f"⚠️ Warning: Could not find {qa_file}. Dataset grounding disabled.")
            self.qa_pairs = []
            return
        
        with open(qa_file, 'r', encoding='utf-8') as f:
            self.qa_pairs = json.load(f)
        
        print(f"✅ Loaded {len(self.qa_pairs)} validated Q&A pairs from Mother dataset")
    
    def find_best_match(self, user_question: str) -> dict:
        """
        Find the closest matching question in the dataset.
        Uses simple keyword overlap for speed.
        """
        if not self.qa_pairs:
            return {"found": False, "answer": None, "confidence": 0}
        
        user_words = set(user_question.lower().split())
        
        best_match = None
        best_score = 0
        
        for item in self.qa_pairs:
            question_words = set(item["question"].lower().split())
            # Calculate overlap score
            overlap = len(user_words & question_words)
            score = overlap / max(len(user_words), len(question_words), 1)
            
            if score > best_score and score > 0.15:  # 15% threshold
                best_score = score
                best_match = item
        
        if best_match:
            return {
                "found": True,
                "answer": best_match["answer"],
                "matched_question": best_match["question"],
                "confidence": best_score
            }
        
        return {"found": False, "answer": None, "confidence": 0}
    
    def get_grounding_prompt(self, user_question: str) -> str:
        """
        Returns a prompt segment to inject into agent instructions.
        """
        match = self.find_best_match(user_question)
        
        if match["found"]:
            return f"""
╔══════════════════════════════════════════════════════════════╗
║  📋 VERIFIED MEDICAL DATA (Mother Dataset)                   ║
╠══════════════════════════════════════════════════════════════╣
║  Question matched: {match['matched_question']}
║  Confidence: {match['confidence']:.2f}
║  ═══════════════════════════════════════════════════════════
║  Verified Answer:
║  {match['answer']}
║  ═══════════════════════════════════════════════════════════
║  ⚠️ You MUST base your response on this verified data.
║  Do NOT add medical advice not present above.
╚══════════════════════════════════════════════════════════════╝
"""
        else:
            return """
╔══════════════════════════════════════════════════════════════╗
║  ⚠️ NOT IN VERIFIED DATASET                                   ║
╠══════════════════════════════════════════════════════════════╣
║  This specific question was not found in the Mother dataset.
║  Answer using general medical knowledge but INCLUDE:
║  "⚠️ This information is based on general knowledge.
║   Please consult a healthcare provider for medical advice."
╚══════════════════════════════════════════════════════════════╝
"""
    
    def get_disclaimer(self) -> str:
        return "⚠️ This information comes from a clinically validated dataset but does not replace professional medical advice. Please consult a healthcare provider."


# Initialize the Mother Dataset (global singleton)
_mother_dataset = None

def get_mother_dataset():
    global _mother_dataset
    if _mother_dataset is None:
        _mother_dataset = MotherDataset()
    return _mother_dataset


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
    dataset_match: Optional[dict]  # 🆕 Track dataset grounding


# Session manager (keeps conversation memory)
session_service = InMemorySessionService()


# ─────────────────────────────────────────────────────────────
# 🤖 BUILD DEBATER AGENTS (WITH DATASET GROUNDING)
# Each agent has the SAME model but DIFFERENT role behavior
# ─────────────────────────────────────────────────────────────
def build_debaters(user_question: str = ""):
    """
    Builds debater agents with dataset grounding injected into instructions.
    """
    model = get_model()
    dataset = get_mother_dataset()
    
    # Get grounding prompt for this specific question
    grounding_prompt = dataset.get_grounding_prompt(user_question)
    disclaimer = dataset.get_disclaimer()
    
    agents = []
    
    # Define different perspectives for each agent
    agent_perspectives = [
        {
            "name_suffix": "Evidence-Based",
            "focus": "Focus STRICTLY on the verified dataset answer. Defend it against other perspectives."
        },
        {
            "name_suffix": "Safety-First",
            "focus": "Focus on patient safety. Critique if the dataset answer lacks warnings or disclaimers."
        },
        {
            "name_suffix": "Holistic",
            "focus": "Synthesize the dataset answer with practical, empathetic advice for the mother."
        }
    ]
    
    for i in range(N_AGENTS):
        perspective = agent_perspectives[i % len(agent_perspectives)]
        
        # Enhanced instruction with dataset grounding
        instruction = f"""
{grounding_prompt}

You are Debater {i+1} - The {perspective['name_suffix']} Perspective.

YOUR ROLE: {perspective['focus']}

DEBATE RULES:
1. Think step-by-step internally but DO NOT show full reasoning.
2. Provide:
   - A short reasoning summary (2-3 sentences)
   - A final answer clearly labeled "FINAL ANSWER:"
3. Be concise but medically accurate.
4. You are allowed to disagree with other debaters.
5. If the dataset provided a verified answer, you MUST prioritize it.
6. {disclaimer}

Remember: Your goal is to provide the BEST possible answer for the expectant mother.
"""
        
        agents.append(
            Agent(
                name=f"debater_{i+1}_{perspective['name_suffix']}",
                model=model,
                instruction=instruction,
            )
        )
    return agents


# ─────────────────────────────────────────────────────────────
# ⚖️ BUILD JUDGE AGENT (WITH DATASET AS SOURCE OF TRUTH)
# This agent decides the final best answer using Chain-of-Thought
# ─────────────────────────────────────────────────────────────
def build_judge(user_question: str = ""):
    dataset = get_mother_dataset()
    match = dataset.find_best_match(user_question)
    
    if match["found"]:
        ground_truth_section = f"""
╔══════════════════════════════════════════════════════════════╗
║  ⚖️ SOURCE OF TRUTH (Mother Dataset)                        ║
╠══════════════════════════════════════════════════════════════╣
║  Question: {match['matched_question']}
║  Verified Answer: {match['answer']}
║  Confidence: {match['confidence']:.2f}
║  ═══════════════════════════════════════════════════════════
║  Use this as your gold standard for evaluating responses.
╚══════════════════════════════════════════════════════════════╝
"""
    else:
        ground_truth_section = """
╔══════════════════════════════════════════════════════════════╗
║  ⚠️ NO DATASET MATCH FOUND                                   ║
╠══════════════════════════════════════════════════════════════╣
║  This question was not in the verified dataset.
║  Evaluate based on medical accuracy and safety.
║  Require all responses to include a medical disclaimer.
╚══════════════════════════════════════════════════════════════╝
"""
    
    judge_instruction = f"""
{ground_truth_section}

You are the JUDGE in a multi-agent maternal health debate.

YOUR CHAIN-OF-THOUGHT EVALUATION (internal):
1. FACTUAL ACCURACY: Which debater's answer best matches the dataset (if available)?
2. COMPLETENESS: Did any debater miss critical information?
3. SAFETY: Were proper disclaimers included? Any potentially harmful advice?
4. EMPATHY: Which answer would be most helpful for an expectant mother?

YOUR RESPONSE FORMAT:
[BRIEF ANALYSIS] - 2-3 sentences explaining your reasoning
[FINAL ANSWER] - The synthesized best answer for the mother
[DISCLAIMER] - Include the medical disclaimer

Keep it concise but thorough.
"""
    
    return Agent(
        name="judge",
        model=get_model(),
        instruction=judge_instruction,
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
# 🚀 MAIN FREE MAD PROTOCOL (WITH DATASET GROUNDING)
# This is what your Django view calls
# ─────────────────────────────────────────────────────────────
async def run_freemad_protocol(
    query: str,
    guiding_prompt: str,
    user_id: str = "web_user",
) -> AsyncGenerator[dict, None]:

    logger.info(f"Starting debate: {query}")
    
    # 🆕 Check dataset match first
    dataset = get_mother_dataset()
    dataset_match = dataset.find_best_match(query)
    
    if dataset_match["found"]:
        logger.info(f"✅ Dataset match found (confidence: {dataset_match['confidence']:.2f})")
        yield {
            "type": "dataset_info",
            "found": True,
            "matched_question": dataset_match["matched_question"],
            "confidence": dataset_match["confidence"]
        }
    else:
        logger.info("⚠️ No dataset match found")
        yield {"type": "dataset_info", "found": False}

    state: FreeMADState = {
        "query": query,
        "guiding_prompt": guiding_prompt,
        "round": 0,
        "responses": {},
        "scores": {},
        "final_decision": None,
        "dataset_match": dataset_match,  # 🆕 Store dataset match
    }

    # 🆕 Build debaters with the specific question (so they get grounding)
    debaters = build_debaters(query)

    try:
        # ─────────────── DEBATE ROUNDS ───────────────
        for k in range(R_ROUNDS):
            state["responses"][k] = {}

            yield {"type": "progress", "message": f"Round {k+1}"}

            for agent in debaters:
                session_id = f"{user_id}_{k}_{agent.name}"

                # 🧠 FIRST ROUND (no peer input)
                if k == 0:
                    # 🆕 Enhanced prompt with dataset grounding
                    grounding = dataset.get_grounding_prompt(query)
                    prompt = f"""
{grounding}

QUESTION:
{query}

INSTRUCTIONS:
- Give a clear, medically accurate answer
- Be concise
- Provide a UNIQUE perspective based on your role
- If dataset provided an answer, prioritize it
- Include the medical disclaimer
"""
                else:
                    # 🧠 LATER ROUNDS (with peer critique)
                    prev = state["responses"][k - 1]
                    peers = "\n".join(
                        f"{n}: {r}" for n, r in prev.items() if n != agent.name
                    )
                    
                    grounding = dataset.get_grounding_prompt(query)
                    
                    prompt = f"""
{grounding}

QUESTION:
{query}

PEER RESPONSES:
{peers}

INSTRUCTIONS:
- Critique peer answers based on the dataset (if available)
- Point out weaknesses, missing disclaimers, or inaccuracies
- Improve your answer based on this critique
- Be respectful but firm
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
                    logger.warning(f"Timeout for {agent.name}")
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

        # ─────────────── JUDGE PHASE (WITH DATASET AS SOURCE OF TRUTH) ───────────────
        yield {"type": "progress", "message": "Judge evaluating final answer..."}

        judge = build_judge(query)  # 🆕 Pass query for dataset grounding

        all_responses = "\n".join(
            f"=== {agent} ===\n{resp}\n"
            for round_responses in state["responses"].values()
            for agent, resp in round_responses.items()
        )
        
        # 🆕 Include dataset info in judge prompt
        dataset_section = ""
        if dataset_match["found"]:
            dataset_section = f"""
DATASET VERIFIED ANSWER (use as gold standard):
"{dataset_match['answer']}"
"""

        judge_prompt = f"""
{dataset_section}

QUESTION:
{query}

ALL DEBATER RESPONSES:
{all_responses}

INSTRUCTIONS:
1. Compare each response against the dataset (if available)
2. Identify the most accurate, complete, and safe answer
3. Synthesize the best elements into a final answer
4. Output in this format:
   [ANALYSIS] - Your reasoning
   [FINAL ANSWER] - The best answer for the mother
   [DISCLAIMER] - Medical disclaimer

{dataset.get_disclaimer()}
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

        if final:
            state["final_decision"] = final
            yield {"type": "final", "message": final}
        else:
            yield {"type": "error", "message": "Judge failed to produce a response"}

    # ─────────────── ERROR HANDLING ───────────────
    except CancelledError:
        logger.warning("Client disconnected")
        return

    except GeneratorExit:
        logger.warning("Generator closed")
        return

    except Exception as e:
        logger.exception("Error in debate protocol")
        yield {"type": "error", "message": str(e)}