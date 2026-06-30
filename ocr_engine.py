import os
import site
import glob

# Ensure all NVIDIA bin directories (cuDNN, cuBLAS, etc.) are in PATH
site_packages = site.getsitepackages()
if site_packages:
    nvidia_path = os.path.join(site_packages[0], 'nvidia')
    if os.path.exists(nvidia_path):
        for lib_dir in glob.glob(os.path.join(nvidia_path, '*', 'bin')):
            os.environ['PATH'] = lib_dir + os.pathsep + os.environ.get('PATH', '')
            if hasattr(os, 'add_dll_directory'):
                os.add_dll_directory(lib_dir)

import paddle
from paddleocr import PaddleOCR

print("Loading PaddleOCR model...")

cuda_available = paddle.device.is_compiled_with_cuda()
print(f"CUDA Available: {cuda_available}")

if cuda_available:
    print("Compiled with CUDA: True")
    # Determine device and name
    current_device = paddle.device.get_device()
    print(f"Current Device: {current_device}")
    try:
        # gpu_id will be like 'gpu:0'
        if 'gpu' in current_device:
            gpu_id = int(current_device.split(':')[1])
            gpu_name = paddle.device.cuda.get_device_name(gpu_id)
            print(f"GPU Name: {gpu_name}")
    except Exception:
        pass
else:
    print("Compiled with CUDA: False")

# Initialize globally so we don't reload the model on every page.
# Using standard parameters for orientation classification and high accuracy.
ocr = PaddleOCR(use_angle_cls=True, lang='en', use_gpu=cuda_available)

print("PaddleOCR ready.")

def ocr_image(image_path):
    try:
        # Perform OCR
        result = ocr.ocr(image_path, cls=True)
        
        if not result or not result[0]:
            return ""
        
        lines = []
        # result[0] contains a list of lines for the image
        for line in result[0]:
            if line and len(line) > 1:
                text = line[1][0]
                lines.append(text)
                
        return "\n".join(lines)
    except Exception as e:
        print(f"PaddleOCR Error on {image_path}: {e}")
        return ""