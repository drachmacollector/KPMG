import os
import hashlib
import tempfile
import pymupdf as fitz  # PyMuPDF
import cv2
from PIL import Image, ImageOps

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


# cv2 rotation codes for 90-degree increments (clockwise angles)
_CV_ROTATE = {
    0:   None,                          # no rotation
    90:  cv2.ROTATE_90_CLOCKWISE,
    180: cv2.ROTATE_180,
    270: cv2.ROTATE_90_COUNTERCLOCKWISE,
}


def _find_best_rotation(image_path: str) -> int:
    """
    Determine the orientation of the image by running PaddleOCR (GPU) at
    four candidate angles (0, 90, 180, 270 degrees clockwise) and selecting
    the angle that yields the highest avg_confidence.  Line count is used
    as a tiebreaker.

    Returns the clockwise rotation angle (int) to apply so that text is upright.
    Returns 0 if no rotation is needed or if OCR cannot decide.
    """
    # Lazy import to avoid a circular dependency at module load time
    # (ocr_engine imports nothing from document_processor).
    from ocr_engine import ocr_image

    img = cv2.imread(image_path)
    if img is None:
        return 0

    best_angle      = 0
    best_avg_conf   = -1.0
    best_line_count = 0

    tmp_dir = tempfile.gettempdir()
    tmp_path = os.path.join(tmp_dir, "_rotation_probe.png")

    for angle, cv_code in _CV_ROTATE.items():
        rotated = cv2.rotate(img, cv_code) if cv_code is not None else img
        cv2.imwrite(tmp_path, rotated)

        metrics = ocr_image(tmp_path)
        avg_conf   = metrics["avg_confidence"]
        line_count = metrics["line_count"]

        print(f"  [Rotation] {angle:3d}° → avg_conf={avg_conf:.4f}  lines={line_count}")

        if (avg_conf > best_avg_conf or
                (avg_conf == best_avg_conf and line_count > best_line_count)):
            best_avg_conf   = avg_conf
            best_line_count = line_count
            best_angle      = angle

    try:
        os.remove(tmp_path)
    except OSError:
        pass

    return best_angle


def normalize_orientation(image_path):
    """
    Correct page orientation using a two-stage approach:

    Stage 1 — EXIF rotation     (handles mobile photos tagged sideways)
    Stage 2 — PaddleOCR sweep   (4-angle confidence probe on GPU, replaces
                                  Tesseract OSD which rejected too many docs)

    The corrected image is saved back to image_path in-place so that
    PaddleOCR always receives an upright page.
    """

    # --- Stage 1: EXIF ---
    exif_changed = _apply_exif_rotation(image_path)
    if exif_changed:
        print(f"  [EXIF] Applied EXIF rotation to {os.path.basename(image_path)}")

    # --- Stage 2: PaddleOCR brute-force rotation sweep ---
    angle = _find_best_rotation(image_path)

    if angle == 0:
        print(f"  [Rotation] Best angle is 0° — no rotation needed.")
        return

    img = cv2.imread(image_path)
    if img is None:
        return

    rotated = cv2.rotate(img, _CV_ROTATE[angle])
    cv2.imwrite(image_path, rotated)
    print(f"  [Rotation] Applied {angle}° CW rotation to {os.path.basename(image_path)}")

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