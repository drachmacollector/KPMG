import os
import logging as py_logging
from logger_config import logger
from tqdm import tqdm

# Suppress Paddle C++ and Python logging
os.environ["GLOG_minloglevel"] = "2"
import logging as py_logging
ppocr_logger = py_logging.getLogger('ppocr')
ppocr_logger.setLevel(py_logging.ERROR)
ppocr_logger.propagate = False
for h in ppocr_logger.handlers[:]:
    ppocr_logger.removeHandler(h)
ppocr_logger.addHandler(py_logging.NullHandler())

# Force protobuf pure-Python implementation so that PaddlePaddle's older
# protobuf requirement and google-genai's newer requirement don't collide
# at the C++ extension layer.  Must be set before any protobuf import.
os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"

import site
import glob

# Ensure all NVIDIA bin directories (cuDNN, cuBLAS, etc.) are in PATH
try:
    for sp in site.getsitepackages():
        nvidia_path = os.path.join(sp, 'nvidia')
        if os.path.exists(nvidia_path):
            for lib_dir in glob.glob(os.path.join(nvidia_path, '*', 'bin')):
                os.environ['PATH'] = lib_dir + os.pathsep + os.environ.get('PATH', '')
                if hasattr(os, 'add_dll_directory'):
                    os.add_dll_directory(lib_dir)
except AttributeError:
    pass

import paddle
from paddleocr import PaddleOCR

cuda_available = paddle.device.is_compiled_with_cuda()
gpu_info = "CPU Only"
if cuda_available:
    current_device = paddle.device.get_device()
    try:
        if 'gpu' in current_device:
            gpu_id = int(current_device.split(':')[1])
            gpu_name = paddle.device.cuda.get_device_name(gpu_id)
            gpu_info = f"{gpu_name} (CUDA Enabled)"
    except Exception:
        gpu_info = "CUDA Enabled"

logger.debug(f"[*] GPU: {gpu_info}")

# Initialize globally so we don't reload the model on every page.
# use_angle_cls=True enables PaddleOCR's built-in 0°/180° text-line classifier.
# 90°/270° rotation is handled upstream in document_processor.py via the
# brute-force 4-angle confidence sweep (_find_best_rotation).
import contextlib
import io

with tqdm(total=1, desc="Loading PaddleOCR", bar_format="{l_bar}{bar:20}|", colour="#FF69B4") as pbar:
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        ocr = PaddleOCR(
            use_angle_cls=True,
            lang="en",
            use_gpu=cuda_available,
            show_log=False,
        )
    pbar.update(1)

logger.debug("[*] PaddleOCR Ready")


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
        logger.error(f"PaddleOCR Error on {image_path}: {e}")
        return empty_result