import json


def cluster_lines_into_blocks(lines, max_vertical_gap=25, max_horizontal_offset=100):
    """
    Groups individual text lines (from EasyOCR) into blocks based on proximity.

    Two lines are merged into the same block if:
      - the vertical gap between them is small (they're close together = likely same paragraph/section)
      - their horizontal starting position (x_min) is roughly aligned (not a totally different column)

    A large vertical gap signals a new block (e.g., a blank line, new heading, new topic).

    Args:
        lines: list of dicts with keys x_min, y_min, x_max, y_max, text (from EasyOCR output)
        max_vertical_gap: max pixel gap between consecutive lines to still count as same block
        max_horizontal_offset: max allowed difference in x_min to still count as aligned

    Returns:
        list of blocks, each block is a dict with merged bounding box + combined text + member lines
    """
    if not lines:
        return []

    # sort lines by reading order: top to bottom, then left to right
    sorted_lines = sorted(lines, key=lambda l: (l["y_min"], l["x_min"]))

    blocks = []
    current_block_lines = [sorted_lines[0]]

    for prev_line, curr_line in zip(sorted_lines, sorted_lines[1:]):
        vertical_gap = curr_line["y_min"] - prev_line["y_max"]
        horizontal_offset = abs(curr_line["x_min"] - prev_line["x_min"])

        same_block = (vertical_gap <= max_vertical_gap) and (horizontal_offset <= max_horizontal_offset)

        if same_block:
            current_block_lines.append(curr_line)
        else:
            blocks.append(_finalize_block(current_block_lines))
            current_block_lines = [curr_line]

    # add the last block
    blocks.append(_finalize_block(current_block_lines))

    return blocks


def _finalize_block(block_lines):
    """Merges a list of line dicts into a single block dict with combined text and bounding box."""
    x_min = min(l["x_min"] for l in block_lines)
    y_min = min(l["y_min"] for l in block_lines)
    x_max = max(l["x_max"] for l in block_lines)
    y_max = max(l["y_max"] for l in block_lines)

    combined_text = "\n".join(l["text"].strip() for l in block_lines)
    avg_confidence = sum(l["confidence"] for l in block_lines) / len(block_lines)

    return {
        "text": combined_text,
        "x_min": x_min, "y_min": y_min,
        "x_max": x_max, "y_max": y_max,
        "line_count": len(block_lines),
        "avg_confidence": round(avg_confidence, 3),
        "lines": block_lines
    }


if __name__ == "__main__":
    import os
    import re

    OCR_RESULTS_DIR = r"C:\Users\HP\Downloads\Voice-AI-Agent\ocr-testing\ocr_results"

    # find all files matching page_N_lines.json in the folder
    line_files = [
        f for f in os.listdir(OCR_RESULTS_DIR)
        if re.match(r"page_\d+_lines\.json$", f)
    ]

    if not line_files:
        print(f"No page_N_lines.json files found in {OCR_RESULTS_DIR}")
    else:
        # sort by page number so pages are processed in order
        line_files.sort(key=lambda f: int(re.search(r"\d+", f).group()))

        for filename in line_files:
            page_num = int(re.search(r"\d+", filename).group())
            input_path = os.path.join(OCR_RESULTS_DIR, filename)
            output_path = os.path.join(OCR_RESULTS_DIR, f"page_{page_num}_blocks.json")

            with open(input_path, "r", encoding="utf-8") as f:
                lines = json.load(f)

            blocks = cluster_lines_into_blocks(lines)

            print(f"\n=== Page {page_num} ===")
            print(f"Grouped {len(lines)} lines into {len(blocks)} blocks:")
            for i, block in enumerate(blocks, 1):
                print(f"--- Block {i} ({block['line_count']} lines) ---")
                print(block["text"])
                print(f"BBox: ({block['x_min']:.0f},{block['y_min']:.0f})-({block['x_max']:.0f},{block['y_max']:.0f})")

            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(blocks, f, indent=2)

            print(f"Saved {len(blocks)} blocks to {output_path}")

        print(f"\nDone. Processed {len(line_files)} page(s).")