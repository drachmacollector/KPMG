import easyocr
import torch

print("Loading EasyOCR model...")

print("Torch version:", torch.__version__)
print("CUDA available:", torch.cuda.is_available())

if torch.cuda.is_available():
    print("GPU:", torch.cuda.get_device_name(0))
else:
    print("CUDA not available!")

reader = easyocr.Reader(
    ['en'],
    gpu=torch.cuda.is_available()
)

print("EasyOCR ready.")

def ocr_image(image_path):

    results = reader.readtext(
        image_path,
        detail=0,
        paragraph=True
    )

    return "\n".join(results)