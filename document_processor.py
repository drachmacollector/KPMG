import os
import hashlib
import fitz  # PyMuPDF
import cv2
from PIL import Image, ImageOps

# Tesseract OSD for 90°/270° rotation detection
import pytesseract
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

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
def _apply_exif_rotation(image_path):
    """
    Apply EXIF orientation tag to correct mobile photos taken sideways.
    Overwrites the file in-place.  Returns True if a rotation was applied.
    """
    try:
        img = Image.open(image_path)
        # ImageOps.exif_transpose reads the EXIF Orientation tag and
        # physically rotates/flips the pixel data, then strips the tag.
        corrected = ImageOps.exif_transpose(img)
        if corrected is not img:           # only overwrite if something changed
            corrected.save(image_path)
            return True
        return False
    except Exception as e:
        print(f"  [EXIF] Could not apply EXIF rotation on {image_path}: {e}")
        return False


def _detect_rotation_angle_osd(image_path):
    """
    Use Tesseract OSD (Orientation and Script Detection) to find the dominant
    text orientation of the image.

    Returns the degrees to rotate counter-clockwise so text is upright, or 0
    if OSD fails / is uncertain.

    Tesseract OSD 'Rotate' field is the angle the image must be rotated
    counter-clockwise to make the text upright.
    """
    try:
        osd = pytesseract.image_to_osd(
            image_path,
            output_type=pytesseract.Output.DICT,
            config="--psm 0 -c min_characters_to_try=5"
        )
        angle = osd.get("rotate", 0)          # degrees CCW to correct
        orientation_conf = osd.get("orientation_conf", 0.0)

        print(f"  [OSD] angle={angle}°  orientation_conf={orientation_conf:.2f}")

        # Only trust OSD when it has reasonable confidence
        if orientation_conf < 2.0:
            print(f"  [OSD] Low confidence ({orientation_conf:.2f}), skipping rotation.")
            return 0

        return int(angle)
    except Exception as e:
        print(f"  [OSD] OSD failed on {image_path}: {e}")
        return 0


def normalize_orientation(image_path):
    """
    Correct page orientation using a two-stage approach:

    Stage 1 — EXIF rotation  (handles mobile photos tagged sideways)
    Stage 2 — Tesseract OSD  (handles 90° / 270° rotations not in EXIF)

    The corrected image is saved back to image_path in-place so that
    PaddleOCR always receives an upright page.
    """

    # --- Stage 1: EXIF ---
    exif_changed = _apply_exif_rotation(image_path)
    if exif_changed:
        print(f"  [EXIF] Applied EXIF rotation to {os.path.basename(image_path)}")

    # --- Stage 2: Tesseract OSD ---
    angle = _detect_rotation_angle_osd(image_path)

    if angle == 0:
        return  # already upright

    # Map OSD CCW angle to OpenCV rotation constant
    # OSD "rotate" = degrees the image must be rotated CCW to correct
    # cv2.rotate uses CW conventions, so we invert:
    cv_rotation_map = {
        90:  cv2.ROTATE_90_COUNTERCLOCKWISE,   # OSD says rotate 90 CCW  → image is 90 CW rotated
        180: cv2.ROTATE_180,
        270: cv2.ROTATE_90_CLOCKWISE,          # OSD says rotate 270 CCW → image is 90 CCW rotated
    }

    cv_code = cv_rotation_map.get(angle)
    if cv_code is None:
        print(f"  [OSD] Unexpected angle {angle}°, skipping.")
        return

    img = cv2.imread(image_path)
    if img is None:
        return

    rotated = cv2.rotate(img, cv_code)
    cv2.imwrite(image_path, rotated)
    print(f"  [OSD] Rotated {angle}° CCW → {os.path.basename(image_path)}")

# ---------------------------------------------------------
# PDF -> PNG
# ---------------------------------------------------------
def pdf_to_images(pdf_path, output_folder, prefix):

    os.makedirs(output_folder, exist_ok=True)

    doc = fitz.open(pdf_path)

    image_paths = []

    for page_num in range(len(doc)):

        page = doc.load_page(page_num)

        # PyMuPDF honours the /Rotate PDF entry when rendering,
        # so pages are already upright after get_pixmap().
        pix = page.get_pixmap(
            dpi=300,
            alpha=False
        )

        output_path = os.path.join(
            output_folder,
            f"{prefix}{page_num+1:03d}.png"
        )

        pix.save(output_path)

        # Apply orientation correction (EXIF + OSD) to handle any
        # remaining rotation that PyMuPDF didn't fix.
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