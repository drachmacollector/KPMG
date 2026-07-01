import os
import site
import glob

# Ensure all NVIDIA bin directories (cuDNN, cuBLAS, etc.) are in PATH
try:
    site_packages = site.getsitepackages()
    if site_packages:
        nvidia_path = os.path.join(site_packages[0], 'nvidia')
        if os.path.exists(nvidia_path):
            for lib_dir in glob.glob(os.path.join(nvidia_path, '*', 'bin')):
                os.environ['PATH'] = lib_dir + os.pathsep + os.environ.get('PATH', '')
                if hasattr(os, 'add_dll_directory'):
                    os.add_dll_directory(lib_dir)
except AttributeError:
    pass

import paddle
from paddleocr import PaddleOCR

print("Loading PaddleOCR model...")

cuda_available = paddle.device.is_compiled_with_cuda()
print(f"CUDA Available: {cuda_available}")

if cuda_available:
    print("Compiled with CUDA: True ✅")
    current_device = paddle.device.get_device()
    print(f"Current Device: {current_device}")
    try:
        if 'gpu' in current_device:
            gpu_id = int(current_device.split(':')[1])
            gpu_name = paddle.device.cuda.get_device_name(gpu_id)
            print(f"GPU Name: {gpu_name} 🔥")
    except Exception:
        pass
else:
    print("Compiled with CUDA: False")

# Initialize globally so we don't reload the model on every page.
# use_angle_cls=True enables PaddleOCR's built-in 0°/180° classifier.
# 90°/270° rotation is handled upstream in document_processor.py via Tesseract OSD.
ocr = PaddleOCR(
    use_angle_cls=True,
    lang="en",
    use_gpu=cuda_available,
    show_log=False,
)
print("PaddleOCR ready.")


def ocr_image(image_path):
    """
    Run PaddleOCR on an image and return a dict with:

      text           - All detected lines joined by newlines (str)
      avg_confidence - Mean per-line confidence score (float 0–1)
      min_confidence - Worst single-line confidence score (float 0–1)
      high_conf_ratio- Fraction of lines with confidence >= 0.80 (float 0–1)
      line_count     - Total number of text lines detected (int)

    Returns a dict with text="" and all metrics = 0.0 / 0 on failure.
    """
    empty_result = {
        "text": "",
        "avg_confidence": 0.0,
        "min_confidence": 0.0,
        "high_conf_ratio": 0.0,
        "line_count": 0,
    }

    try:
        result = ocr.ocr(image_path, cls=True)

        if not result or not result[0]:
            return empty_result

        lines = []
        confidences = []

        for line in result[0]:
            if line and len(line) > 1:
                text = line[1][0]
                conf = float(line[1][1])   # PaddleOCR confidence score 0–1
                lines.append(text)
                confidences.append(conf)

        if not lines:
            return empty_result

        HIGH_CONF_THRESHOLD = 0.80
        high_conf_count = sum(1 for c in confidences if c >= HIGH_CONF_THRESHOLD)

        return {
            "text": "\n".join(lines),
            "avg_confidence":  round(sum(confidences) / len(confidences), 4),
            "min_confidence":  round(min(confidences), 4),
            "high_conf_ratio": round(high_conf_count / len(confidences), 4),
            "line_count":      len(lines),
        }

    except Exception as e:
        print(f"PaddleOCR Error on {image_path}: {e}")
        return empty_result