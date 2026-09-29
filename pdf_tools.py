import fitz
import os
import shutil
import tempfile
import glob
import win32com.client
import io
from PIL import Image


class PDFTools:
    """Utilities for assembling, editing, and converting PDF documents.

    Can be used as a context manager by passing a path on construction or via
    the alternate PDFTools.open(path) constructor. The document is saved
    atomically on clean exit.
    """

    def __init__(self, path: str | None = None) -> None:
        """Optionally open a PDF document on construction for use as a context manager."""
        self._src_path: str | None = None
        self._doc: fitz.Document | None = None

        if path is not None:
            self._src_path = os.path.abspath(path)
            self._doc = fitz.open(path)

    @classmethod
    def open(cls, path: str) -> "PDFTools":
        """Alternate constructor that opens a PDF for use as a context manager."""
        return cls(path)

    def __enter__(self) -> "PDFTools":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._doc is not None:
            if exc_type is None and self._src_path is not None:
                self._atomic_save(self._doc, self._src_path)
            self._doc.close()
            self._doc = None
        return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _atomic_save(doc: fitz.Document, dest_path: str) -> None:
        """Write doc to dest_path via a temp file to ensure an atomic replace."""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp_path = tmp.name
        doc.save(tmp_path)
        shutil.move(tmp_path, dest_path)

    @staticmethod
    def _insert_label(dst: fitz.Document, label: str) -> None:
        """Append a centred label divider page to dst."""
        divider = dst.new_page()
        text = label.strip()
        font_size = 36
        rect = divider.rect
        text_width = fitz.get_text_length(text, fontsize=font_size)
        x = (rect.width - text_width) / 2
        y = rect.height / 2
        divider.insert_text(
            (x, y), text, fontsize=font_size, fontname="helv", color=(0, 0, 0)
        )

    def _require_context(self) -> fitz.Document:
        """Return the active document or raise if no document is loaded."""
        if self._doc is None:
            raise RuntimeError(
                "This method requires an open document — "
                "use PDFTools('path') or PDFTools.open('path')."
            )
        return self._doc

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def extract(
        self,
        start_page: int,
        n_pages: int,
        src_path: str | None = None,
        dest_path: str | None = None,
        label: str | None = None,
    ) -> None:
        """Append a page range from a PDF into another, optionally preceded by a divider page.

        Falls back to the open document if src_path is not given. dest_path
        defaults to src_path with an '_extracted' suffix. The write is atomic.
        """
        if src_path is None:
            src = self._require_context()
            src_path = self._src_path
            owns_src = False
        else:
            src = fitz.open(src_path)
            owns_src = True

        if dest_path is None:
            base, ext = os.path.splitext(src_path)
            dest_path = f"{base}_extracted{ext}"

        dst = fitz.open(dest_path) if os.path.exists(dest_path) else fitz.open()

        if label:
            self._insert_label(dst, label)

        for i in range(start_page - 1, start_page - 1 + n_pages):
            dst.insert_pdf(src, from_page=i, to_page=i)

        self._atomic_save(dst, dest_path)
        dst.close()
        if owns_src:
            src.close()

    def append_to(self, other_path: str, label: str | None = None) -> None:
        """Append all pages of the open document to another PDF.

        If other_path does not exist it is created. An optional centred label
        divider is inserted before the appended pages.
        """
        doc = self._require_context()

        dst = fitz.open(other_path) if os.path.exists(other_path) else fitz.open()

        if label:
            self._insert_label(dst, label)

        dst.insert_pdf(doc)
        self._atomic_save(dst, other_path)
        dst.close()

    def delete_from(self, start_page: int, n_pages: int) -> None:
        """Delete a range of pages from the open document in-place.

        Pages are 1-indexed. Changes are written to disk when the context exits.
        """
        doc = self._require_context()
        doc.delete_pages(from_page=start_page - 1, to_page=start_page - 1 + n_pages - 1)

    def get_metadata(self) -> dict:
        """Return the PDF metadata dict of the open document.

        Keys include title, author, subject, keywords, creator, producer,
        creationDate, and modDate.
        """
        return self._require_context().metadata

    def summarise(self) -> str:
        """Return an AI-generated summary of the open document's text content.

        Not yet implemented.
        """
        raise NotImplementedError

    def peek(
        self,
        page_number: int,
        output: str = "text",
        size: int | None = None,
    ) -> str | Image.Image:
        """Preview a single page as truncated text or a PIL Image.
    
        page_number is 1-indexed. For text, size is the maximum number of
        characters returned. For image, size is a percentage (1–100) of page
        height to crop; full width is always preserved.
        """
        doc = self._require_context()
        page = doc[page_number - 1]
    
        if output == "text":
            text = page.get_text()
            return text[:size] if size is not None else text
    
        if output == "image":
            clip = None
            if size is not None:
                rect = page.rect
                clip = fitz.Rect(0, 0, rect.width, rect.height * (size / 100))
            pixmap = page.get_pixmap(clip=clip)
            return Image.open(io.BytesIO(pixmap.tobytes("png")))
    
        raise ValueError(f"output must be 'text' or 'image', got {output!r}")
        
    # ------------------------------------------------------------------
    # Conversion
    # ------------------------------------------------------------------

    def to_docx(
        self,
        src_path: str | None = None,
        dest_path: str | None = None,
        visible: bool = False,
    ) -> None:
        """Convert a PDF to a Word document using the Word COM automation API.

        Falls back to the open document if src_path is not given. dest_path
        defaults to src_path with a .docx extension. Requires Microsoft Word on
        Windows. Word is always quit cleanly regardless of errors.
        """
        if src_path is None:
            self._require_context()
            src_path = self._src_path
        else:
            src_path = os.path.abspath(src_path)

        if dest_path is None:
            base, _ = os.path.splitext(src_path)
            dest_path = f"{base}.docx"
        else:
            dest_path = os.path.abspath(dest_path)

        word = win32com.client.Dispatch("Word.Application")
        word.Visible = visible
        word.DisplayAlerts = 0 

        try:
            doc = word.Documents.Open(src_path)
            doc.SaveAs2(dest_path, FileFormat=16)  # 16 = wdFormatDocumentDefault
            doc.Close()
        finally:
            word.Quit()

    # ------------------------------------------------------------------
    # Batch
    # ------------------------------------------------------------------

    def batch(
        self,
        operation: str,
        folder: str | None = None,
        pattern: str = "*.pdf",
        recursive: bool = False,
        **kwargs,
    ) -> list[str]:
        """Apply extract or to_docx to every file in a folder matching a glob pattern.

        Falls back to the directory of the open document if folder is not given.
        Failures are collected and re-raised together after all files are attempted.
        Returns a list of output paths produced.
        """
        if operation not in ("extract", "to_docx"):
            raise ValueError(f"operation must be 'extract' or 'to_docx', got {operation!r}")

        if folder is None:
            self._require_context()
            folder = os.path.dirname(self._src_path)

        glob_root = os.path.join(folder, "**", pattern) if recursive else os.path.join(folder, pattern)
        matches = glob.glob(glob_root, recursive=recursive)

        fn = getattr(self, operation)
        outputs: list[str] = []
        errors: list[str] = []

        for src in matches:
            try:
                fn(src, **kwargs)

                if operation == "to_docx":
                    base, _ = os.path.splitext(src)
                    outputs.append(kwargs.get("dest_path") or f"{base}.docx")
                else:
                    base, ext = os.path.splitext(src)
                    outputs.append(kwargs.get("dest_path") or f"{base}_extracted{ext}")

            except Exception as e:
                errors.append(f"{src}: {e}")

        if errors:
            raise RuntimeError("Batch completed with errors:\n" + "\n".join(errors))

        return outputs