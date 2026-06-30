import easyocr

print("Loading EasyOCR model... (first run may take 20-60 seconds)")

reader = easyocr.Reader(
    ['en'],
    gpu=True     # we'll enable GPU later
)

print("EasyOCR ready.")

def ocr_image(image_path):

    results = reader.readtext(
        image_path,
        detail=0,
        paragraph=True
    )

    return "\n".join(results)