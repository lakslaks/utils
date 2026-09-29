#img2text.py

from __future__ import annotations

from typing import Any, Optional, Union, Literal, Dict
import os

import pytesseract
from PIL import Image, ImageGrab
import numpy as np


def to_text(source: Union[None, str, "Image.Image", "Any"] = None,
        *, tesseract_cmd: Optional[str] = r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        lang: str = "eng", config: str = "", grab: Literal["auto", "clipboard"] = "auto",
        return_mode: Literal["text", "data"] = "text", data_output: Literal["dict", "tsv"] = "dict",) -> Union[str, Dict[str, Any]]:
    """OCR utility (pytesseract)""
    Parameters
    ----------
    source:
        None, filepath, PIL image, or numpy array.
    tesseract_cmd:
        Path to tesseract.exe (Windows) if not in PATH.
    lang:
        Tesseract language code(s), e.g. "eng", "eng+equ".
    config:
        Extra tesseract config string (e.g. "--psm 6 --oem 3").
    grab:
        "auto" or "clipboard". If source is None, clipboard will be used.
    return_mode:
        "text" for plain text, "data" for structured output (boxes/confidence etc.).
    data_output:
        When return_mode="data": "dict" uses image_to_data(..., output_type=DICT),
        "tsv" returns the raw TSV string.

    Returns
    -------
    str | dict
        OCR text or structured OCR data.
    """
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    img: Optional[Image.Image] = None

    if source is None: # 1) Resolve source -> PIL Image
        if grab in ("auto", "clipboard"):
            clip = ImageGrab.grabclipboard()
            if isinstance(clip, Image.Image):
                img = clip
            elif isinstance(clip, list) and clip: # clipboard may contain a file path list
                img = Image.open(clip[0])
            else:
                raise ValueError("No image found in clipboard.")
        else:
            raise ValueError("source is None but grab is not set to clipboard/auto.")
    elif isinstance(source, str):
        if not os.path.exists(source):
            raise FileNotFoundError(f"Image path not found: {source}")
        img = Image.open(source)
    elif isinstance(source, Image.Image):
        img = source
    else: # likely numpy array (or array-like)
        try:
            if isinstance(source, np.ndarray):
                img = Image.fromarray(source)
            else:
                img = Image.fromarray(source)  # last resort: try PIL conversion if possible
        except Exception as e:
            raise ValueError("Unsupported input type. Provide None (clipboard), file path, PIL Image, or numpy array.") from e

    if img is None:
        raise ValueError("Unable to resolve source into an image.")

    if img.mode not in ("RGB", "L"): # Optional: normalize mode (helps avoid odd OCR on RGBA)
        img = img.convert("RGB")

    if return_mode == "text": # OCR
        return pytesseract.image_to_string(img, lang=lang, config=config)

    if data_output == "tsv": # "data"
        return pytesseract.image_to_data(img, lang=lang, config=config)

    # dict output
    return pytesseract.image_to_data(img, lang=lang, config=config, output_type=pytesseract.Output.DICT)

if __name__ == '__main__' :
    #clipboard
    print (to_text())