# maternal_knowledge_base.py (in E:\MHCMAS\)
import json
from pathlib import Path
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

class MaternalKnowledgeBase:
    def __init__(self, data_path: str = "data"):
        """
        Loads the Mother dataset and builds a TF-IDF search index.
        "Data folder is at root level: E:/MHCMAS/data/"
        """
        # Get the directory where THIS file is located (root directory)
        root_dir = Path(__file__).parent
        
        # Data folder is at the same level
        data_dir = root_dir / data_path
        
        # Try different possible filenames (in order of preference)
        possible_filenames = [
            "mother_question_and_answer_pairs_dataset.json",
            "mother_question_and_answer_pairs_dataset",
            "mother_question_and_answer_pairs_data.json",
            "mother_question_and_answer_pairs_data",
        ]
        
        qa_file = None
        for filename in possible_filenames:
            test_path = data_dir / filename
            if test_path.exists():
                qa_file = test_path
                print(f"✅ Found dataset at: {qa_file}")
                break
        
        if qa_file is None:
            print(f"❌ ERROR: Could not find dataset file in {data_dir}")
            print(f"   Root directory: {root_dir}")
            print(f"   Data directory: {data_dir}")
            print(f"   Files in data dir: {list(data_dir.glob('*')) if data_dir.exists() else 'data folder not found'}")
            self.qa_pairs = []
            self.questions = []
            self.answers = []
            return
        
        # Load the JSON file
        try:
            with open(qa_file, 'r', encoding='utf-8') as f:
                self.qa_pairs = json.load(f)
        except json.JSONDecodeError as e:
            print(f"❌ ERROR: Failed to parse JSON: {e}")
            self.qa_pairs = []
            self.questions = []
            self.answers = []
            return
        
        # Build search index
        self.questions = [item["question"] for item in self.qa_pairs]
        self.answers = [item["answer"] for item in self.qa_pairs]
        
        # Create TF-IDF vectorizer and index
        self.vectorizer = TfidfVectorizer().fit(self.questions)
        self.question_vectors = self.vectorizer.transform(self.questions)
        
        print(f"✅ Loaded {len(self.qa_pairs)} validated Q&A pairs (TF-IDF index ready)")
    
    def retrieve(self, user_query: str, threshold: float = 0.3) -> dict:
        """
        Finds the best matching answer using TF-IDF cosine similarity.
        Returns: {"found": bool, "answer": str, "confidence": float, "matched_question": str}
        """
        if not self.qa_pairs:
            return {"found": False, "answer": None, "confidence": 0, "matched_question": None}
        
        # Convert query to vector and calculate similarity
        query_vec = self.vectorizer.transform([user_query])
        similarities = cosine_similarity(query_vec, self.question_vectors).flatten()
        best_idx = np.argmax(similarities)
        best_score = similarities[best_idx]
        
        if best_score >= threshold:
            return {
                "found": True,
                "answer": self.answers[best_idx],
                "confidence": float(best_score),
                "matched_question": self.questions[best_idx]
            }
        else:
            return {
                "found": False,
                "answer": None,
                "confidence": float(best_score),
                "matched_question": None
            }
    
    # Keep the old method name for backward compatibility
    def find_best_match(self, user_question: str) -> dict:
        """
        Alias for retrieve() - maintains compatibility with existing code.
        """
        return self.retrieve(user_question)
    
    def get_disclaimer(self) -> str:
        """Returns the required medical disclaimer."""
        return "⚠️ This information comes from a clinically validated dataset but does not replace professional medical advice. Please consult a healthcare provider."


# Singleton instance
_kb_instance = None

def get_knowledge_base():
    """Returns the singleton instance of MaternalKnowledgeBase"""
    global _kb_instance
    if _kb_instance is None:
        _kb_instance = MaternalKnowledgeBase()
    return _kb_instance