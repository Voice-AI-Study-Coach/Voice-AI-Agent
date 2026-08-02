import os
import easyocr
import cv2
import json
INPUT_DIR = r"C:\Users\HP\Downloads\Voice-AI-Agent\ocr-testing\images"       # folder containing page_1.png, page_2.png, ... from PyMuPDF step
OUTPUT_DIR = r"C:\Users\HP\Downloads\Voice-AI-Agent\ocr-testing\ocr_results"

os.makedirs(OUTPUT_DIR, exist_ok=True)
 
# Load the OCR reader once (avoids reloading model per page)
# gpu=False so it runs without CUDA. Set gpu=True if you have a working GPU setup.
reader = easyocr.Reader(['en'], gpu=False)
 
 
def process_page(image_path, page_num):
    image = cv2.imread(image_path)
 
    # detail=1 gives bounding box + text + confidence per detected line
    results = reader.readtext(image_path, detail=1)
 
    print(f"\n=== Page {page_num} ===")
    lines = []
    for (bbox, text, confidence) in results:
        # bbox is 4 corner points: [top-left, top-right, bottom-right, bottom-left]
        x_coords = [point[0] for point in bbox]
        y_coords = [point[1] for point in bbox]
        x_min, x_max = float(min(x_coords)), float(max(x_coords))
        y_min, y_max = float(min(y_coords)), float(max(y_coords))
        confidence = float(confidence)
 
        print(f"Text: {text.strip()[:60]} | Confidence: {confidence:.2f} | BBox: ({x_min:.0f},{y_min:.0f})-({x_max:.0f},{y_max:.0f})")
 
        lines.append({
            "text": text,
            "confidence": confidence,
            "x_min": x_min, "y_min": y_min,
            "x_max": x_max, "y_max": y_max
        })
 
        # draw box on image for visual check
        cv2.rectangle(image, (int(x_min), int(y_min)), (int(x_max), int(y_max)), (0, 255, 0), 2)
 
    # save visualized output so you can see detected lines on the page
    out_path = os.path.join(OUTPUT_DIR, f"page_{page_num}_boxes.png")
    cv2.imwrite(out_path, image)
 
    # save the actual line data (text + bbox + confidence) as JSON --
    # this is the file the clustering script reads, NOT the .png
    json_path = os.path.join(OUTPUT_DIR, f"page_{page_num}_lines.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(lines, f, indent=2, ensure_ascii=False)
 
    return lines
 
 
if __name__ == "__main__":
    total_pages = len([f for f in os.listdir(INPUT_DIR) if f.startswith("page_")])
 
    all_pages_lines = {}
    for i in range(1, total_pages + 1):
        file_path = os.path.join(INPUT_DIR, f"page_{i}.png")
        if not os.path.exists(file_path):
            print(f"Warning: {file_path} not found. Skipping.")
            continue
 
        lines = process_page(file_path, i)
        all_pages_lines[i] = lines
 
    print(f"\nDone. Visualized boxes saved to '{OUTPUT_DIR}/'")