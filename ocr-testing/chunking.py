import os
import re
import json
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

OCR_RESULTS_DIR = r"C:\Users\HP\Downloads\Voice-AI-Agent\ocr-testing\ocr_results"

# Load the embedding model once (small, fast, good enough for this task)
model = SentenceTransformer("all-MiniLM-L6-v2")


def group_blocks_into_topics(blocks, similarity_threshold=0.4):
    """
    Groups a sequence of text blocks into topic-coherent chunks using
    semantic similarity between consecutive blocks.

    If the similarity between a block and the next one drops below the
    threshold, that marks a topic boundary -> a new chunk starts.

    Args:
        blocks: list of block dicts (from cluster_blocks.py output), in reading order
        similarity_threshold: cosine similarity cutoff (0-1). Lower = more likely
                               to merge blocks into the same topic; higher = more
                               likely to split into separate topics.

    Returns:
        list of topic chunks, each a dict with combined text + member blocks
    """
    if not blocks:
        return []

    texts = [b["text"] for b in blocks]
    embeddings = model.encode(texts)

    topics = []
    current_topic_blocks = [blocks[0]]

    for i in range(1, len(blocks)):
        sim = cosine_similarity(
            [embeddings[i - 1]],
            [embeddings[i]]
        )[0][0]

        if sim >= similarity_threshold:
            # similar enough to previous block -> same topic
            current_topic_blocks.append(blocks[i])
        else:
            # topic shift detected -> close current topic, start a new one
            topics.append(_finalize_topic(current_topic_blocks))
            current_topic_blocks = [blocks[i]]

    topics.append(_finalize_topic(current_topic_blocks))

    return topics


def _finalize_topic(topic_blocks):
    """Merges a list of block dicts into a single topic-chunk dict."""
    x_min = min(b["x_min"] for b in topic_blocks)
    y_min = min(b["y_min"] for b in topic_blocks)
    x_max = max(b["x_max"] for b in topic_blocks)
    y_max = max(b["y_max"] for b in topic_blocks)

    combined_text = "\n\n".join(b["text"] for b in topic_blocks)

    return {
        "topic_text": combined_text,
        "x_min": x_min, "y_min": y_min,
        "x_max": x_max, "y_max": y_max,
        "block_count": len(topic_blocks),
        "blocks": topic_blocks
    }


if __name__ == "__main__":
    block_files = [
        f for f in os.listdir(OCR_RESULTS_DIR)
        if re.match(r"page_\d+_blocks\.json$", f)
    ]

    if not block_files:
        print(f"No page_N_blocks.json files found in {OCR_RESULTS_DIR}")
    else:
        block_files.sort(key=lambda f: int(re.search(r"\d+", f).group()))

        for filename in block_files:
            page_num = int(re.search(r"\d+", filename).group())
            input_path = os.path.join(OCR_RESULTS_DIR, filename)
            output_path = os.path.join(OCR_RESULTS_DIR, f"page_{page_num}_topics.json")

            with open(input_path, "r", encoding="utf-8") as f:
                blocks = json.load(f)

            topics = group_blocks_into_topics(blocks)

            print(f"\n=== Page {page_num} ===")
            print(f"Grouped {len(blocks)} blocks into {len(topics)} topic chunk(s):")
            for i, topic in enumerate(topics, 1):
                preview = topic["topic_text"].replace("\n", " ")[:80]
                print(f"--- Topic {i} ({topic['block_count']} blocks) ---")
                print(preview)

            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(topics, f, indent=2)

            print(f"Saved {len(topics)} topic chunk(s) to {output_path}")

        print(f"\nDone. Processed {len(block_files)} page(s).")