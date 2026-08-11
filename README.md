# MeterVision (v0.1 prototype)

AI-powered extraction of the numeric reading from a photograph of a gas,
water, or electricity meter. Given a real-world photo (blurry, tilted,
glare, poor lighting, cropped, cluttered with unrelated printed text), the
system locates the meter's digit-window reading display and returns
structured, validated JSON — the reading itself, plus (separately) the
meter's serial number if it's legibly printed nearby. The two are never
allowed to be confused with each other; see "How results are judged" below.

This is **not** a generic OCR tool: the vision prompt and the application-
side validation are specifically designed to distinguish the reading
display from other numbers printed on the meter body, while still
capturing useful metadata like the serial number as its own field.

## Pipeline

```
USER IMAGE
    -> IMAGE QUALITY / PREPROCESSING   (vision/preprocessing.py, OpenCV)
    -> VISION AI (Gemini)              (providers/gemini_provider.py)
    -> STRICT JSON PARSING             (vision/detection.py)
    -> APPLICATION-SIDE VALIDATION     (vision/validation.py)
    -> CONFIDENCE-GATED STATUS         (accepted / needs_review / rejected)
    -> STRUCTURED RESULT               (models/meter_result.py)
```

## Project structure

```
app.py                     Streamlit UI
config/settings.py         Env-driven configuration (no hardcoded secrets)
providers/base.py          VisionProvider interface + typed provider errors
providers/gemini_provider.py  Gemini (google-genai SDK) implementation
vision/preprocessing.py    OpenCV preprocessing variants (resize, contrast,
                            brightness, sharpen, denoise, glare reduction,
                            deskew, best-effort perspective correction)
vision/prompts.py          The meter-reading extraction prompt
vision/detection.py        Pipeline orchestration + response parsing
vision/validation.py       Application-side validation & status assignment
models/meter_result.py     Pydantic result models
tests/                     Unit tests (parsing + validation)
sample_images/             Local test images (gitignored contents)
```

## Setup

### 1. Environment note (this machine)

This system ships Python 3.12 **without pip or ensurepip**, so a normal
`python3 -m venv` will fail. The working setup used here:

```bash
python3 -m venv .venv --without-pip
curl -sS https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
.venv/bin/python3 /tmp/get-pip.py
.venv/bin/python3 -m pip install -r requirements.txt
```

If your machine already has a normal Python + pip, just do the usual:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure your API key

```bash
cp .env.example .env
```

Edit `.env` and set:

```
GEMINI_API_KEY=your_key_here
```

Get a key at https://aistudio.google.com/apikey. **Never commit `.env`** —
it's already in `.gitignore`. The key is read only via
`config/settings.py` (using `python-dotenv`); it is never hardcoded,
logged, or shown in the UI.

### 3. Run the app

```bash
.venv/bin/streamlit run app.py
```

Open the printed local URL (typically http://localhost:8501).

### 4. Run the tests

```bash
.venv/bin/python3 -m pytest tests/ -v
```

## How results are judged

The vision model returns strict JSON including its own `confidence` and
`image_quality` self-assessment — but that self-report is **never trusted
blindly**. `vision/validation.py` independently checks:

- was a meter detected at all, and was the display located
- is there a reading, and is it present in both `raw_digits` and `reading`
- do the characters form a valid numeric structure (digits + optional
  single decimal point)
- do `reading`'s digits match `raw_digits` once the decimal point is
  removed (catches inconsistent formatting)
- is the digit count within a plausible range for a meter display
  (guards against accidentally reading a long serial number instead)
- is the model's confidence within `[0, 1]`, and at or above
  `CONFIDENCE_THRESHOLD` (default `0.85`, configurable via `.env`)
- did the model itself flag `needs_retake` or rate `image_quality` as
  `"poor"`
- if a `serial_number` was also returned, is it identical to `raw_digits`
  — if so, the model almost certainly confused the reading display with
  the serial number, and the result is forced to `needs_review` even if
  confidence was high

Based on these checks, each result gets one of three statuses:

- **accepted** — passed every check and met the confidence threshold
- **needs_review** — a meter/display was found but something about the
  reading, its format, or confidence/quality means a human should check it
- **rejected** — no meter was detected in the image at all

## Manual testing procedure

Since real-world photo quality varies, test the UI (`streamlit run app.py`)
against each of these cases and confirm the behavior described:

| Case | How to produce it | Expected behavior |
|---|---|---|
| Clear image | Straight-on, well-lit, in-focus photo of the full meter | `meter_detected`/`display_detected` = YES, a plausible reading, high confidence, status **accepted** (if >= threshold) |
| Blurry image | Take the photo while moving the camera, or heavily downscale/upscale | Lower confidence; likely **needs_review** with a blur-related reason, or a correct reading if still legible |
| Tilted image | Photograph the meter at a rotated angle (10-30°) | Deskew preprocessing should help; if still unreadable, status **needs_review** with a clear reason rather than a wrong guess |
| Dark image | Photograph in low light / shadow | Brightness/contrast-enhanced variant is sent to the model; if still too dark, expect **needs_review**, `image_quality: "poor"` |
| Glare | Use direct flash/sunlight on the glass cover so part of the display is blown out | Glare-reduction variant is sent; if glare still hides digits, expect `raw_digits`/`reading` = null and a glare-specific reason, never a fabricated digit |
| Partial/cropped meter | Frame the photo so part of the digit display is cut off | Expect `display_detected` possibly false, or a reason noting the display is incomplete; never a guessed missing digit |
| Unrelated numbers nearby | Include the serial number / spec plate clearly in frame along with the display | The extracted `reading` should come from the digit-window display, not the serial/spec number — check `raw_digits` length and value against what's actually in the display windows, not the plate. If a serial number is legible, it should also show up separately in `serial_number`, distinct from `raw_digits` |

For each case, also check the **"Raw structured result (debug)"** expander
in the UI to inspect the full JSON (`meter_detected`, `display_detected`,
`raw_digits`, `reading`, `unit`, `confidence`, `image_quality`,
`needs_retake`, `reason`) and the validation notes shown for
non-accepted results.

## Design notes / what's deliberately NOT implemented yet

Per the v0.1 scope, the following are intentionally out of scope for now
but the architecture leaves room for them:

- automatic meter bounding-box / display-region detection (currently the
  full image + light preprocessing is sent to the vision model, which does
  its own localization)
- camera capture / live camera guidance
- custom-trained digit recognition model
- database storage, user accounts, REST API, mobile app

Adding a second vision provider only requires implementing
`providers/base.VisionProvider` and wiring it into `config.settings` /
`app.get_provider()` — no changes needed to preprocessing, validation, or
the UI.

## Error handling

The pipeline is designed to fail gracefully rather than crash:

- invalid/corrupted/unsupported image files are rejected before any
  processing (`vision/preprocessing.validate_image_upload`)
- oversized images are rejected with a clear size-limit message
- a missing `GEMINI_API_KEY` produces a friendly configuration error, not
  a stack trace
- provider-level failures (auth, rate limit, timeout, malformed/empty
  response) are caught and mapped to typed errors in
  `providers/base.py`, then surfaced as a "needs_review" result or a
  clear UI error rather than propagating raw SDK exceptions
- a malformed or schema-violating JSON response from the model falls back
  to a conservative "needs retake" result instead of guessing
