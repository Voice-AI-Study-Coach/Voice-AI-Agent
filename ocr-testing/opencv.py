import os
import cv2
import numpy as np

INPUT_DIR = r"C:\Users\HP\Downloads\Voice-AI-Agent\ocr-testing\images"       # folder containing page_1.png, page_2.png, ... from PyMuPDF step
OUTPUT_DIR = r"C:\Users\HP\Downloads\Voice-AI-Agent\ocr-testing\opencv_results"

os.makedirs(OUTPUT_DIR, exist_ok=True)


def detect_underlines(gray_image, min_line_length_ratio=0.15):
    """
    Detects long horizontal lines (underlines under headings).
    Returns a list of (x_min, y, x_max, y) line segments.
    """
    edges = cv2.Canny(gray_image, 50, 150, apertureSize=3)

    width = gray_image.shape[1]
    min_line_length = int(width * min_line_length_ratio)

    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 180,
        threshold=100,
        minLineLength=min_line_length,
        maxLineGap=10
    )

    underlines = []
    if lines is not None:
        for line in lines:
            x1, y1, x2, y2 = line[0]
            # keep only near-horizontal lines (small vertical difference)
            if abs(y2 - y1) < 5 and abs(x2 - x1) > min_line_length:
                underlines.append((min(x1, x2), y1, max(x1, x2), y2))

    return underlines


def detect_boxes(gray_image, min_area=2000):
    """
    Detects rectangular bordered regions (like 'Example' boxes).
    Returns a list of (x, y, w, h) bounding rectangles.
    """
    # threshold to get binary image, then find contours
    _, thresh = cv2.threshold(gray_image, 200, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(thresh, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    boxes = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < min_area:
            continue

        peri = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.02 * peri, True)

        # a rectangle-ish shape has 4 corners
        if len(approx) == 4:
            x, y, w, h = cv2.boundingRect(approx)
            # filter out shapes that are too thin to be a real box (avoid stray lines)
            if w > 30 and h > 30:
                boxes.append((x, y, w, h))

    return boxes


def process_page(image_path, page_num):
    image = cv2.imread(image_path)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    underlines = detect_underlines(gray)
    boxes = detect_boxes(gray)

    print(f"\n=== Page {page_num} ===")
    print(f"Detected {len(underlines)} underline(s), {len(boxes)} box(es)")

    visual = image.copy()

    for (x1, y1, x2, y2) in underlines:
        cv2.line(visual, (x1, y1), (x2, y2), (0, 0, 255), 3)  # red for underlines
        print(f"Underline at y={y1}, x-range=({x1}-{x2})")

    for (x, y, w, h) in boxes:
        cv2.rectangle(visual, (x, y), (x + w, y + h), (255, 0, 0), 3)  # blue for boxes
        print(f"Box at x={x}, y={y}, w={w}, h={h}")

    out_path = os.path.join(OUTPUT_DIR, f"page_{page_num}_structure.png")
    cv2.imwrite(out_path, visual)

    return {"underlines": underlines, "boxes": boxes}


if __name__ == "__main__":
    total_pages = len([f for f in os.listdir(INPUT_DIR) if f.startswith("page_")])

    all_pages_structure = {}
    for i in range(1, total_pages + 1):
        file_path = os.path.join(INPUT_DIR, f"page_{i}.png")
        if not os.path.exists(file_path):
            print(f"Warning: {file_path} not found. Skipping.")
            continue

        structure = process_page(file_path, i)
        all_pages_structure[i] = structure

    print(f"\nDone. Visualized structure saved to '{OUTPUT_DIR}/'")