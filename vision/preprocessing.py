"""Image preprocessing for MeterVision.

Produces several complementary enhanced variants of the input image without
ever mutating the original bytes. Real-world meter photos are frequently
blurry, tilted, poorly lit, or affected by glare, so a handful of cheap,
targeted variants tend to be more robust than one "perfect" transform.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image as PILImage

from config import settings


@dataclass
class PreprocessedImage:
    label: str
    image: np.ndarray  # BGR uint8
    description: str

    def encode_jpeg(self, quality: int = 92) -> bytes:
        ok, buf = cv2.imencode(".jpg", self.image, [cv2.IMWRITE_JPEG_QUALITY, quality])
        if not ok:
            raise ValueError(f"Failed to encode preprocessed image variant '{self.label}'.")
        return buf.tobytes()


def validate_image_upload(image_bytes: bytes) -> None:
    """Raise ValueError with a user-facing message if the uploaded file is
    unusable, without touching OpenCV. Meant to run before any processing."""
    if not image_bytes:
        raise ValueError("The uploaded file is empty.")

    size_mb = len(image_bytes) / (1024 * 1024)
    if size_mb > settings.MAX_UPLOAD_SIZE_MB:
        raise ValueError(
            f"Image is {size_mb:.1f} MB, which exceeds the "
            f"{settings.MAX_UPLOAD_SIZE_MB:.0f} MB limit."
        )

    try:
        with PILImage.open(io.BytesIO(image_bytes)) as img:
            img.verify()
            fmt = (img.format or "").upper()
    except Exception as exc:  # noqa: BLE001 - any Pillow failure means unusable image
        raise ValueError(
            f"Could not read the image file — it may be corrupted or an "
            f"unsupported format ({exc})."
        ) from exc

    if fmt not in settings.SUPPORTED_IMAGE_FORMATS:
        raise ValueError(
            f"Unsupported image format '{fmt}'. Supported formats: "
            f"{', '.join(sorted(settings.SUPPORTED_IMAGE_FORMATS))}."
        )


def decode_image(image_bytes: bytes) -> np.ndarray:
    array = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Could not decode image data — unsupported or corrupted file.")
    return image


def resize_max_dimension(image: np.ndarray, max_dimension: int | None = None) -> np.ndarray:
    max_dimension = max_dimension or settings.MAX_IMAGE_DIMENSION_PX
    height, width = image.shape[:2]
    longest = max(height, width)
    if longest <= max_dimension:
        return image.copy()
    scale = max_dimension / longest
    new_size = (int(width * scale), int(height * scale))
    interpolation = cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC
    return cv2.resize(image, new_size, interpolation=interpolation)


def to_gray(image: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def enhance_contrast(image: np.ndarray) -> np.ndarray:
    """CLAHE-based local contrast enhancement on the luminance channel only,
    so hue (e.g. red fractional digits) is preserved."""
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    l_channel = clahe.apply(l_channel)
    merged = cv2.merge((l_channel, a_channel, b_channel))
    return cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)


def adjust_brightness(image: np.ndarray, target_mean: float = 130.0) -> np.ndarray:
    """Gamma-correct the image toward a target mean brightness."""
    gray = to_gray(image)
    current_mean = float(gray.mean())
    if current_mean <= 1:
        return image.copy()
    gamma = np.log(target_mean / 255.0 + 1e-6) / np.log(current_mean / 255.0 + 1e-6)
    gamma = float(np.clip(gamma, 0.3, 3.0))
    inv_gamma = 1.0 / gamma
    table = np.array([((i / 255.0) ** inv_gamma) * 255 for i in range(256)]).astype("uint8")
    return cv2.LUT(image, table)


def denoise(image: np.ndarray) -> np.ndarray:
    return cv2.fastNlMeansDenoisingColored(
        image, None, h=7, hColor=7, templateWindowSize=7, searchWindowSize=21
    )


def sharpen(image: np.ndarray) -> np.ndarray:
    blurred = cv2.GaussianBlur(image, (0, 0), sigmaX=3)
    return cv2.addWeighted(image, 1.5, blurred, -0.5, 0)


def reduce_glare(image: np.ndarray) -> np.ndarray:
    """Suppress small blown-out specular highlights (glare) by detecting
    near-white saturated regions and inpainting them from surrounding pixels."""
    gray = to_gray(image)
    _, glare_mask = cv2.threshold(gray, 235, 255, cv2.THRESH_BINARY)
    glare_mask = cv2.dilate(glare_mask, np.ones((5, 5), np.uint8), iterations=1)
    if cv2.countNonZero(glare_mask) == 0:
        return image.copy()
    return cv2.inpaint(image, glare_mask, inpaintRadius=5, flags=cv2.INPAINT_TELEA)


def deskew(image: np.ndarray) -> np.ndarray:
    """Estimate and correct small rotational skew from the dominant near-
    horizontal edge angle (typically the digit-window bezel edges). Falls
    back to the original image if no reliable angle is found."""
    gray = to_gray(image)
    edges = cv2.Canny(gray, 50, 150)
    min_len = max(20, min(image.shape[:2]) // 4)
    lines = cv2.HoughLinesP(
        edges, 1, np.pi / 180, threshold=80, minLineLength=min_len, maxLineGap=10
    )
    if lines is None or len(lines) == 0:
        return image.copy()

    angles = []
    for line in lines:
        # cv2.HoughLinesP output shape varies by OpenCV build: (N, 1, 4) in
        # some versions, (N, 4) in others. np.reshape handles both.
        x1, y1, x2, y2 = np.reshape(line, -1)
        angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
        if angle > 45:
            angle -= 90
        elif angle < -45:
            angle += 90
        if abs(angle) < 30:
            angles.append(angle)

    if not angles:
        return image.copy()

    median_angle = float(np.median(angles))
    if abs(median_angle) < 0.5:
        return image.copy()

    height, width = image.shape[:2]
    center = (width / 2, height / 2)
    rotation_matrix = cv2.getRotationMatrix2D(center, median_angle, 1.0)
    return cv2.warpAffine(
        image,
        rotation_matrix,
        (width, height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )


def correct_perspective(image: np.ndarray) -> np.ndarray:
    """Best-effort perspective correction: finds the largest roughly-
    rectangular contour (assumed to be the meter face or display bezel) and
    warps it to a front-on rectangle. This is a lightweight heuristic, not
    real object detection — it returns the original image unchanged if no
    confident quadrilateral is found."""
    gray = to_gray(image)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)

    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return image.copy()

    image_area = image.shape[0] * image.shape[1]
    best_quad = None
    best_area = 0.0

    for contour in contours:
        perimeter = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
        if len(approx) != 4:
            continue
        area = cv2.contourArea(approx)
        if area < 0.15 * image_area or area > 0.95 * image_area:
            continue
        if area > best_area:
            best_area = area
            best_quad = approx

    if best_quad is None:
        return image.copy()

    points = best_quad.reshape(4, 2).astype("float32")
    ordered = _order_quad_points(points)
    top_left, top_right, bottom_right, bottom_left = ordered

    width_top = np.linalg.norm(top_right - top_left)
    width_bottom = np.linalg.norm(bottom_right - bottom_left)
    height_left = np.linalg.norm(bottom_left - top_left)
    height_right = np.linalg.norm(bottom_right - top_right)

    target_width = int(max(width_top, width_bottom))
    target_height = int(max(height_left, height_right))
    if target_width < 20 or target_height < 20:
        return image.copy()

    destination = np.array(
        [
            [0, 0],
            [target_width - 1, 0],
            [target_width - 1, target_height - 1],
            [0, target_height - 1],
        ],
        dtype="float32",
    )
    matrix = cv2.getPerspectiveTransform(ordered, destination)
    return cv2.warpPerspective(image, matrix, (target_width, target_height))


def _order_quad_points(points: np.ndarray) -> np.ndarray:
    ordered = np.zeros((4, 2), dtype="float32")
    total = points.sum(axis=1)
    ordered[0] = points[np.argmin(total)]  # top-left
    ordered[2] = points[np.argmax(total)]  # bottom-right
    diff = np.diff(points, axis=1)
    ordered[1] = points[np.argmin(diff)]  # top-right
    ordered[3] = points[np.argmax(diff)]  # bottom-left
    return ordered


def build_preprocessed_variants(image_bytes: bytes) -> list[PreprocessedImage]:
    """Build a small set of complementary preprocessing variants from the
    original image bytes. The original is never modified in place — every
    step below works on copies. Deliberately kept small (not every
    permutation of every filter) to keep vision-API payload size and cost
    reasonable.
    """
    original = decode_image(image_bytes)
    resized = resize_max_dimension(original)

    variants: list[PreprocessedImage] = [
        PreprocessedImage("original", resized, "Resized original, no other changes"),
    ]

    enhanced = enhance_contrast(resized)
    enhanced = adjust_brightness(enhanced)
    enhanced = sharpen(enhanced)
    variants.append(
        PreprocessedImage("enhanced", enhanced, "Contrast/brightness enhanced + sharpened")
    )

    deglared = reduce_glare(resized)
    deglared = enhance_contrast(deglared)
    deglared = denoise(deglared)
    variants.append(
        PreprocessedImage("deglared", deglared, "Glare-suppressed, denoised, contrast enhanced")
    )

    aligned = deskew(resized)
    aligned = correct_perspective(aligned)
    if aligned.shape != resized.shape or not np.array_equal(aligned, resized):
        variants.append(PreprocessedImage("aligned", aligned, "Rotation/perspective corrected"))

    return variants
