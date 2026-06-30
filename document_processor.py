import os
import hashlib
import fitz  # PyMuPDF
import cv2
from PIL import Image

# ---------------------------------------------------------
# SHA256
# ---------------------------------------------------------
def calculate_sha256(filepath):
    
    # Returns SHA256 hash of a file.
    # Used to detect duplicate uploads

    sha = hashlib.sha256()

    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(8192)

            if not chunk:
                break

            sha.update(chunk)

    return sha.hexdigest()

# ---------------------------------------------------------
# IMAGE ORIENTATION
# ---------------------------------------------------------
def normalize_orientation(image_path):

    img = cv2.imread(image_path)

    if img is None:
        return

    h, w = img.shape[:2]

    if w > h:
        img = cv2.rotate(
            img,
            cv2.ROTATE_90_CLOCKWISE
        )

        cv2.imwrite(
            image_path,
            img
        )
# ---------------------------------------------------------
# PDF -> PNG
# ---------------------------------------------------------
def pdf_to_images(pdf_path, output_folder, prefix):

    os.makedirs(output_folder, exist_ok=True)

    doc = fitz.open(pdf_path)

    image_paths = []

    for page_num in range(len(doc)):

        page = doc.load_page(page_num)

        pix = page.get_pixmap(
            dpi=300,
            alpha=False
        )

        output_path = os.path.join(
            output_folder,
            f"{prefix}{page_num+1:03d}.png"
        )

        pix.save(output_path)

        normalize_orientation(output_path)

        image_paths.append(output_path)

    doc.close()

    return image_paths
# ---------------------------------------------------------
# IMAGE -> PNG
# ---------------------------------------------------------
def image_to_png(image_path, output_folder, prefix):

    os.makedirs(output_folder, exist_ok=True)

    img = Image.open(image_path)

    output_path = os.path.join(
        output_folder,
        f"{prefix}001.png"
    )

    img.save(output_path)

    normalize_orientation(output_path)

    return [output_path]
# ---------------------------------------------------------
# AUTO NORMALIZATION
# ---------------------------------------------------------
def normalize_document(filepath, output_folder, document_name):

    extension = os.path.splitext(filepath)[1].lower()

    if extension == ".pdf":

        return pdf_to_images(
            filepath,
            output_folder,
            f"{document_name}_page"
        )

    elif extension in [".jpg", ".jpeg", ".png"]:

        return image_to_png(
            filepath,
            output_folder,
            f"{document_name}_page"
        )

    else:
            print(f"⚠️ Warning: Unsupported or missing file extension '{extension}'. Skipping.")
            return []