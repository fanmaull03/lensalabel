"""Script analisis bounding box dan reading order sorting untuk melengkung_005.jpeg dan foto pembanding datar_002.jpeg."""

from pathlib import Path
import cv2
import numpy as np
import easyocr
import json

REPO_ROOT = Path(r"d:\Kulyeah\SKRIPSI\project\lensalabel")
DEBUG_OUT = REPO_ROOT / "dataset" / "debug_output"
DEBUG_OUT.mkdir(parents=True, exist_ok=True)

# Import pipeline preprocessing
import sys
sys.path.insert(0, str(REPO_ROOT / "backend"))
from app.preprocessing.pipeline import preprocess
from app.ocr.reader import _downscale, MAX_OCR_WIDTH, sort_reading_order

def analyze_photo(photo_name: str, category: str = "melengkung"):
    photo_path = REPO_ROOT / "dataset" / "raw_photos" / category / photo_name
    img = cv2.imread(str(photo_path))
    if img is None:
        raise FileNotFoundError(f"Cannot read {photo_path}")

    # Production pipeline: preprocess -> downscale -> EasyOCR detail=1
    prep = preprocess(img)
    ocr_img = _downscale(prep, MAX_OCR_WIDTH)
    
    reader = easyocr.Reader(["id", "en"], gpu=False)
    raw_results = reader.readtext(ocr_img, detail=1)
    
    # Let's also prepare visualization on ocr_img (RGB converted for drawing)
    vis_img = cv2.cvtColor(ocr_img, cv2.COLOR_GRAY2BGR) if len(ocr_img.shape) == 2 else ocr_img.copy()
    
    # Draw raw bounding boxes with index (1-based)
    print(f"\n=======================================================")
    print(f"ANALISIS: {photo_name} (Total deteksi EasyOCR: {len(raw_results)})")
    print(f"Dimensi citra OCR: {ocr_img.shape[1]}x{ocr_img.shape[0]} px")
    print(f"=======================================================")
    
    detection_data = []
    
    for idx, (bbox, text, conf) in enumerate(raw_results, start=1):
        pts = np.array(bbox, dtype=np.int32)
        xs = [p[0] for p in bbox]
        ys = [p[1] for p in bbox]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        center_y = sum(ys) / len(ys)
        center_x = sum(xs) / len(xs)
        height = max_y - min_y
        width = max_x - min_x
        
        detection_data.append({
            "id": idx,
            "text": text,
            "conf": float(conf),
            "bbox": [[int(p[0]), int(p[1])] for p in bbox],
            "min_x": int(min_x),
            "max_x": int(max_x),
            "min_y": int(min_y),
            "max_y": int(max_y),
            "center_x": float(center_x),
            "center_y": float(center_y),
            "width": int(width),
            "height": int(height),
        })
        
        # Draw polygon
        cv2.polylines(vis_img, [pts], isClosed=True, color=(0, 255, 0), thickness=2)
        # Put label box
        label = f"#{idx}: {text} ({conf:.2f})"
        # Position label above or at top-left
        cv2.putText(vis_img, f"#{idx}", (int(min_x), max(15, int(min_y) - 5)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2, cv2.LINE_AA)

    vis_out_path = DEBUG_OUT / f"{Path(photo_name).stem}_easyocr_boxes.png"
    cv2.imwrite(str(vis_out_path), vis_img)
    print(f"Visualisasi disimpan ke: {vis_out_path}")
    
    return detection_data, raw_results, ocr_img.shape

if __name__ == "__main__":
    det_005, raw_005, shape_005 = analyze_photo("melengkung_005.jpeg", "melengkung")
    
    # Save raw detection data to json for exact inspection
    with open(DEBUG_OUT / "melengkung_005_detections.json", "w", encoding="utf-8") as f:
        json.dump(det_005, f, indent=2, ensure_ascii=False)
        
    print("\nDeteksi EasyOCR mentah (sebelum sorting):")
    for d in det_005:
        print(f"#{d['id']:02d} [X: {d['min_x']:4d}..{d['max_x']:4d}, Y: {d['min_y']:4d}..{d['max_y']:4d}, H: {d['height']:2d}, W: {d['width']:3d}] | Conf: {d['conf']:.2f} | \"{d['text']}\"")
        
    # Analyze datar_002 for normal X gap distribution
    det_datar, raw_datar, shape_datar = analyze_photo("datar_002.jpeg", "datar")
    with open(DEBUG_OUT / "datar_002_detections.json", "w", encoding="utf-8") as f:
        json.dump(det_datar, f, indent=2, ensure_ascii=False)
