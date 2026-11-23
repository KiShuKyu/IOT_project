import re
import math
import json


STOP_WORDS = {
    "a", "an", "the", "and", "or", "but", "to", "of", "in", "on",
    "at", "for", "with", "from", "is", "are", "was", "were", "be",
    "it", "this", "that", "these", "those", "i", "me", "my", "we",
    "our", "you", "your", "he", "she", "they", "them", "his", "her",
    "what", "when", "where", "who", "why", "how", "did", "do", "does",
    "have", "has", "had", "about", "as", "by", "into", "if", "then",
    "than", "can", "could", "would", "should", "will", "just"
}


def tokenize(text):
    """Convert text into searchable tokens."""
    words = re.findall(r"[a-z0-9_+#.-]+", str(text).lower())

    return [
        word
        for word in words
        if len(word) > 1 and word not in STOP_WORDS
    ]


def get_item_text(item):
    """Combine searchable fields of a memory."""
    details = item.get("details") or {}

    return (
        str(item.get("title", "")) + " "
        + str(item.get("content", "")) + " "
        + json.dumps(details, ensure_ascii=False)
    )


def rank_memories(question, memories, limit=10):
    """
    Rank saved memories against a question using a BM25-style score.

    Title matches receive additional weight.
    Returns the most relevant memories, highest score first.
    """

    query_tokens = set(tokenize(question))

    if not query_tokens or not memories:
        return []

    documents = [
        tokenize(get_item_text(memory))
        for memory in memories
    ]

    # How many documents contain each word?
    document_frequency = {}

    for document in documents:
        for word in set(document):
            document_frequency[word] = (
                document_frequency.get(word, 0) + 1
            )

    total_documents = len(documents)
    scored_memories = []

    for memory, document in zip(memories, documents):

        if not document:
            continue

        term_frequency = {}

        for word in document:
            term_frequency[word] = (
                term_frequency.get(word, 0) + 1
            )

        score = 0.0

        # BM25-style scoring
        for word in query_tokens:

            if word not in term_frequency:
                continue

            df = document_frequency.get(word, 0)

            idf = math.log(
                1 + (total_documents - df + 0.5)
                / (df + 0.5)
            )

            tf = term_frequency[word]
            document_length = len(document)

            k1 = 1.5
            b = 0.75
            average_length = 80

            score += idf * (
                (tf * (k1 + 1))
                / (
                    tf + k1 * (
                        1 - b + b * document_length / average_length
                    )
                )
            )

        # Give matches in the title extra importance
        title_tokens = set(
            tokenize(memory.get("title", ""))
        )

        score += 2.0 * len(query_tokens & title_tokens)

        if score > 0:
            scored_memories.append((score, memory))

    scored_memories.sort(
        key=lambda result: result[0],
        reverse=True
    )

    return [
        memory
        for score, memory in scored_memories[:limit]
    ]


if __name__ == "__main__":

    sample_memories = [
        {
            "id": 1,
            "kind": "idea",
            "title": "Resume Analyzer",
            "content": "Build a Django resume analyzer with AI-powered skill matching.",
            "details": {"technology": ["Django", "Gemini"]}
        },
        {
            "id": 2,
            "kind": "task",
            "title": "Buy groceries",
            "content": "Buy milk, bread, and eggs.",
            "details": {}
        },
        {
            "id": 3,
            "kind": "memory",
            "title": "Internship preparation",
            "content": "Prepare a full-stack developer resume and practice interviews.",
            "details": {}
        }
    ]

    question = "What features did I plan for my resume analyzer?"

    results = rank_memories(question, sample_memories)

    print("\nQuestion:", question)
    print("\nRetrieved memories:")

    for memory in results:
        print(f"- [{memory['kind']}] {memory['title']}")
        print(f"  {memory['content']}")