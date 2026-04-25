# test_kb.py (in E:\MHCMAS\)
from maternal_knowledge_base import get_knowledge_base

def test_knowledge_base():
    print("=" * 60)
    print("Testing Mother Dataset Knowledge Base (TF-IDF Version)")
    print("=" * 60)
    
    kb = get_knowledge_base()
    
    # Check if data loaded successfully
    if not kb.qa_pairs:
        print("❌ No data loaded! Check your data folder.")
        print("\n💡 Tip: Make sure your JSON file is in E:\\MHCMAS\\data\\")
        return
    
    test_questions = [
        "Why do I feel tired and weak?",
        "My feet are swollen, what causes this?",
        "Can I drink coffee while pregnant?",
        "What foods should I eat?",
        "Is exercise safe during pregnancy?",
    ]
    
    print("\n📊 TF-IDF Similarity Matching Test")
    print("-" * 40)
    
    for question in test_questions:
        print(f"\n📝 User asked: {question}")
        result = kb.retrieve(question)
        
        if result["found"]:
            print(f"   ✅ MATCH FOUND (confidence: {result['confidence']:.3f})")
            print(f"   📌 Matched question: {result['matched_question']}")
            print(f"   💡 Answer preview: {result['answer'][:120]}...")
        else:
            print(f"   ❌ No match found (confidence: {result['confidence']:.3f})")
    
    print("\n" + "=" * 60)
    print(f"📊 Disclaimer: {kb.get_disclaimer()}")
    print("=" * 60)

if __name__ == "__main__":
    test_knowledge_base()