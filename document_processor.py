import os
import hashlib
import tempfile
import pymupdf as fitz  # PyMuPDF
import cv2
from PIL import Image, ImageOps
from logger_config import logger

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
        logger.debug(f"[EXIF] Could not apply EXIF rotation on {image_path}: {e}")
        return False


# cv2 rotation codes for 90-degree increments (clockwise angles)
_CV_ROTATE = {
    0:   None,                          # no rotation
    90:  cv2.ROTATE_90_CLOCKWISE,
    180: cv2.ROTATE_180,
    270: cv2.ROTATE_90_COUNTERCLOCKWISE,
}


# If the upright (0°) OCR pass is already this confident, skip the 4-angle
# sweep entirely.  Most scanned/PDF pages are upright, so this avoids three
# extra full OCR passes per page (the main cost on CPU-only machines).
UPRIGHT_CONFIDENCE_OK = 0.85
UPRIGHT_MIN_LINES = 5

# Rotation probes run on a downscaled copy; orientation is obvious at this size.
PROBE_MAX_SIDE = 1600


def _downscale(img, max_side):
    h, w = img.shape[:2]
    longest = max(h, w)
    if longest <= max_side:
        return img
    scale = max_side / float(longest)
    return cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)


def _find_best_rotation(image_path: str) -> int:
    """
    Determine the orientation of the image by running PaddleOCR at four
    candidate angles (0, 90, 180, 270 degrees clockwise) and selecting the
    angle that yields the highest avg_confidence.  Line count is used as a
    tiebreaker.

    Fast path: if the 0° probe is already confident (>= UPRIGHT_CONFIDENCE_OK
    with at least UPRIGHT_MIN_LINES lines), the other angles are skipped.

    Returns the clockwise rotation angle (int) to apply so that text is upright.
    Returns 0 if no rotation is needed or if OCR cannot decide.
    """
    # Lazy import to avoid a circular dependency at module load time
    # (ocr_engine imports nothing from document_processor).
    from ocr_engine import ocr_image

    img = cv2.imread(image_path)
    if img is None:
        return 0
    img = _downscale(img, PROBE_MAX_SIDE)

    best_angle      = 0
    best_avg_conf   = -1.0
    best_line_count = 0

    fd, tmp_path = tempfile.mkstemp(prefix="_rotation_probe_", suffix=".png")
    os.close(fd)

    try:
        for angle, cv_code in _CV_ROTATE.items():
            rotated = cv2.rotate(img, cv_code) if cv_code is not None else img
            cv2.imwrite(tmp_path, rotated)

            metrics = ocr_image(tmp_path)
            avg_conf   = metrics["avg_confidence"]
            line_count = metrics["line_count"]

            logger.debug(f"[Rotation] {angle:3d}° → avg_conf={avg_conf:.4f}  lines={line_count}")

            if (avg_conf > best_avg_conf or
                    (avg_conf == best_avg_conf and line_count > best_line_count)):
                best_avg_conf   = avg_conf
                best_line_count = line_count
                best_angle      = angle

            if angle == 0 and avg_conf >= UPRIGHT_CONFIDENCE_OK and line_count >= UPRIGHT_MIN_LINES:
                logger.debug("[Rotation] Upright page is confident — skipping rotation sweep.")
                break
    finally:
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
        logger.debug(f"[EXIF] Applied EXIF rotation to {os.path.basename(image_path)}")

    # --- Stage 2: PaddleOCR brute-force rotation sweep ---
    angle = _find_best_rotation(image_path)

    if angle == 0:
        logger.debug("[Rotation] Best angle is 0° — no rotation needed.")
        return

    img = cv2.imread(image_path)
    if img is None:
        return

    rotated = cv2.rotate(img, _CV_ROTATE[angle])
    cv2.imwrite(image_path, rotated)
    logger.debug(f"[Rotation] Applied {angle}° CW rotation to {os.path.basename(image_path)}")

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
# Very large phone photos (12+ MP) make OCR slow without improving accuracy.
MAX_IMAGE_SIDE = 3000


def image_to_png(image_path, output_folder, prefix):

    os.makedirs(output_folder, exist_ok=True)

    output_path = os.path.join(
        output_folder,
        f"{prefix}001.png"
    )

    with Image.open(image_path) as img:
        # Apply the EXIF orientation BEFORE saving as PNG — PNG output drops
        # the EXIF tag, so doing it afterwards would be a no-op.
        img = ImageOps.exif_transpose(img)
        # CMYK / palette / LA images cannot always be written as PNG and
        # confuse OCR; normalise to RGB.
        if img.mode != "RGB":
            img = img.convert("RGB")
        if max(img.size) > MAX_IMAGE_SIDE:
            img.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE), Image.LANCZOS)
        img.save(output_path)

    normalize_orientation(output_path)

    return [output_path]

# ---------------------------------------------------------
# AUTO NORMALIZATION
# ---------------------------------------------------------
def sniff_extension(filepath):
    """
    Detect a document's real type from its first bytes.
    Returns ".pdf", ".jpg", ".png", ".webp" or "" if unknown.
    Portal URLs do not always carry a reliable file extension.
    """
    try:
        with open(filepath, "rb") as f:
            head = f.read(16)
    except OSError:
        return ""
    if head.startswith(b"%PDF"):
        return ".pdf"
    if head.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return ".webp"
    return ""


def normalize_document(filepath, output_folder, document_name):

    extension = sniff_extension(filepath) or os.path.splitext(filepath)[1].lower()

    if extension == ".pdf":

        return pdf_to_images(
            filepath,
            output_folder,
            f"{document_name}_page"
        )

    elif extension in [".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"]:

        return image_to_png(
            filepath,
            output_folder,
            f"{document_name}_page"
        )

    else:
        logger.warning(f"Unsupported or missing file type '{extension}' for {os.path.basename(filepath)}. Skipping.")
        return []
