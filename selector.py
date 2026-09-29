
class Selection:
    """
    Wraps the raw selection result (tuple, list, lambda)
    and provides helper methods for expansion and analysis.
    """

    def __init__(self, raw):
        self.raw = raw  # tuple, list, or lambda

    # ---------------------------------------------------------
    # Convert to Python slice (if applicable)
    # ---------------------------------------------------------
    def to_slice(self, **kwargs):
        if isinstance(self.raw, tuple) and len(self.raw) == 2:
            start, end = self.raw
            return slice(start, end)
        raise TypeError("Selection is not a slice-style range")

    # ---------------------------------------------------------
    # Expand to explicit list of indices (requires total)
    # ---------------------------------------------------------
    def to_list(self, total, **kwargs):
        if total is None:
            raise ValueError("to_list(total=...) requires total")

        # Range-style tuple
        if isinstance(self.raw, tuple):
            start, end = self.raw
            return list(range(
                start if start is not None else 0,
                end if end is not None else total
            ))

        # Explicit list
        if isinstance(self.raw, list):
            return [i for i in self.raw if 0 <= i < total]

        # Lambda mask
        if callable(self.raw):
            return [i for i in range(total) if self.raw(i)]

        raise TypeError("Unsupported selection type")

    # ---------------------------------------------------------
    # Boolean mask
    # ---------------------------------------------------------
    def to_mask(self, total, **kwargs):
        lst = self.to_list(total)
        mask = [False] * total
        for i in lst:
            mask[i] = True
        return mask

    # ---------------------------------------------------------
    # Check if index is included
    # ---------------------------------------------------------
    def contains(self, idx, total=None, **kwargs):
        if isinstance(self.raw, tuple):
            start, end = self.raw
            if start is None:
                start = 0
            if end is None:
                end = total
            return start <= idx < end

        if isinstance(self.raw, list):
            return idx in self.raw

        if callable(self.raw):
            return self.raw(idx)

        raise TypeError("Unsupported selection type")

    # ---------------------------------------------------------
    # Invert selection (requires total)
    # ---------------------------------------------------------
    def invert(self, total, **kwargs):
        full = set(range(total))
        selected = set(self.to_list(total))
        return Selection(sorted(full - selected))

    # ---------------------------------------------------------
    # Union with another selection
    # ---------------------------------------------------------
    def union(self, other, total, **kwargs):
        a = set(self.to_list(total))
        b = set(other.to_list(total))
        return Selection(sorted(a | b))

    # ---------------------------------------------------------
    # Intersection with another selection
    # ---------------------------------------------------------
    def intersect(self, other, total, **kwargs):
        a = set(self.to_list(total))
        b = set(other.to_list(total))
        return Selection(sorted(a & b))

    # ---------------------------------------------------------
    # Explain the selection in human terms
    # ---------------------------------------------------------
    def explain(self, **kwargs):
        raw = self.raw

        if isinstance(raw, tuple):
            start, end = raw
            if start is None and end is not None:
                return f"till page {end}"
            if start is not None and end is None:
                return f"from page {start+1} onwards"
            return f"pages {start+1} thru {end}"

        if isinstance(raw, list):
            pages = [i+1 for i in raw]
            return "pages " + ", ".join(map(str, pages))

        if callable(raw):
            # crude detection
            return "odd pages" if raw(0) and not raw(1) else "even pages"

        return "unknown selection"

    # ---------------------------------------------------------
    # Apply to pandas DataFrame
    # ---------------------------------------------------------
    def apply(self, df, **kwargs):
        mask = self.to_mask(len(df))
        return df.loc[mask]

    # ---------------------------------------------------------
    # Apply to PyMuPDF / fitz document
    # ---------------------------------------------------------
    def apply_to_pages(self, doc, **kwargs):
        pages = self.to_list(doc.page_count)
        return [doc.load_page(p) for p in pages]

    def __repr__(self):
        return f"Selection({self.raw})"


# ======================================================================
# Selector — the DSL engine
# ======================================================================

class Selector:
    def __call__(self, *args, **kwargs):
        return self.as_range(*args, **kwargs)

    # ---------------------------------------------------------
    # Main entry point
    # ---------------------------------------------------------
    def as_range(self, *args, zero_based=True, total=None):
        # Keyword / DSL expressions
        if len(args) == 1 and isinstance(args[0], str):
            raw = self._parse_keyword(args[0], zero_based, total)
            return Selection(raw)

        # Numeric / tuple / list
        start, end = self._extract_numeric(args)

        # Zero-based conversion
        start, end = self._convert(start, end, zero_based)

        # Validation
        self._validate(start, end)

        return Selection((start, end))

    # ---------------------------------------------------------
    # Extract numeric forms
    # ---------------------------------------------------------
    def _extract_numeric(self, args):
        if len(args) == 1:
            var = args[0]

            if isinstance(var, int):
                return var, var + 1

            if isinstance(var, (tuple, list)) and len(var) == 2:
                return var[0], var[1]

            raise TypeError(f"Invalid argument: {var}")

        elif len(args) == 2:
            return args[0], args[1]

        raise TypeError(f"Invalid arguments: {args}")

    # ---------------------------------------------------------
    # Zero-based conversion (only positive ints)
    # ---------------------------------------------------------
    def _convert(self, start, end, zero_based):
        def cv(n):
            if n is None:
                return None
            if isinstance(n, int) and n > 0:
                return n - 1 if zero_based else n
            return n  # negative or None unchanged

        return cv(start), cv(end)

    # ---------------------------------------------------------
    # Validation
    # ---------------------------------------------------------
    def _validate(self, start, end):
        if isinstance(start, int) and isinstance(end, int):
            if end <= start:
                raise ValueError(f"Invalid range: end ({end}) must be > start ({start})")

    # ---------------------------------------------------------
    # Keyword / DSL parser
    # ---------------------------------------------------------
    def _parse_keyword(self, text, zero_based, total):
        t = text.strip().lower()

        # -------------------------
        # Odd / Even pages
        # -------------------------
        if t == "odd pages":
            return lambda idx: (idx + 1) % 2 == 1

        if t == "even pages":
            return lambda idx: (idx + 1) % 2 == 0

        # -------------------------
        # Comma-separated list
        # -------------------------
        if "," in t:
            nums = [int(x.strip()) for x in t.split(",")]
            return [(n - 1) for n in nums]

        # -------------------------
        # first / last
        # -------------------------
        if t == "first":
            return (0 if zero_based else 1, 1 if zero_based else 2)

        if t == "last":
            return (-1, None)

        # first N
        if t.startswith("first "):
            n = int(t.split()[1])
            return (0, n)

        # last N
        if t.startswith("last "):
            n = int(t.split()[1])
            return (-n, None)

        # -------------------------
        # except <n>
        # -------------------------
        if t.startswith("except "):
            n = int(t.split()[1])
            return (n, None)

        # except last <n>
        if t.startswith("except last "):
            n = int(t.split()[2])
            return (None, -n)

        # -------------------------
        # <n> onwards
        # -------------------------
        if t.endswith(" onwards"):
            n = int(t.split()[0])
            return (n - 1, None)

        # -------------------------
        # till <n>
        # -------------------------
        if t.startswith("till "):
            n = int(t.split()[1])
            return (None, n - 1)

        # -------------------------
        # <n> thru <m>
        # -------------------------
        if " thru " in t:
            a, b = t.split(" thru ")
            a, b = int(a), int(b)
            return (a - 1, b)

        # -------------------------
        # middle <n>  (requires total)
        # -------------------------
        if t.startswith("middle "):
            if total is None:
                raise ValueError("middle <n> requires total=")

            n = int(t.split()[1])
            half = n // 2

            mid = total // 2
            start = mid - half
            end = start + n

            return (start, end)

        raise ValueError(f"Unrecognized range expression: {text}")


def select(*args, total=None, zero_based=True, **kwargs):
    """
    Factory function with smart mode detection and getattr dispatch.
    Exposes all public Selection methods automatically.
    """
    mode = "selection"
    if args and isinstance(args[-1], str):
        candidate = args[-1]
        if candidate in ("selection", "raw"):
            mode = candidate
            args = args[:-1]
        elif hasattr(Selection, candidate) and not candidate.startswith("_"):
            mode = candidate
            args = args[:-1]
        # Otherwise: treat as DSL expression (do nothing)

    sel = Selector().as_range(*args, zero_based=zero_based, total=total)
    if mode == "selection":
        return sel
    if mode == "raw":
        return sel.raw

    # getattr dispatch for ANY Selection method
    if hasattr(sel, mode):
        method = getattr(sel, mode)
        return method(total=total, **kwargs)

    raise ValueError(f"Unknown mode or method: {mode}")


def to_range(*args, mode='tuple', n_items=None, zero_base=True, transform=None, **kwargs):
    """Convert flexible range arguments to various range representations.

    Accepts int, (start, stop), (start, stop, step), or a list/tuple/set
    of those values, plus an optional trailing string to set mode.
    """
    if args and isinstance(args[-1], str) and len(args) > 1:
        mode, args = args[-1], args[:-1]

    if args and isinstance(args[0], str):
        result = parse_keyword(args[0], zero_based=zero_base, total=n_items)
        if callable(result) or isinstance(result, list):
            return result
        return to_range(*result, mode=mode, n_items=n_items, zero_base=zero_base, transform=transform)

    if len(args) == 1 and isinstance(args[0], int):
        sl = slice(args[0], args[0] + 1)
    elif len(args) == 2 and isinstance(args[0], int) and args[1] is None:
        sl = slice(args[0], None, None)
    elif len(args) == 3 and isinstance(args[0], int) and args[1] is None and isinstance(args[2], int):
        sl = slice(args[0], None, args[2])
    elif isinstance(args[0], (list, tuple, set)):
        sl = slice(*args[0])
    else:
        sl = slice(*args)

    if n_items is not None:
        start, stop, step = sl.indices(n_items)
    else:
        start = sl.start if sl.start is not None else 0
        stop = sl.stop
        step = sl.step if sl.step is not None else 1

    if not zero_base:
        start = start + 1 if start is not None else None
        stop = stop + 1 if stop is not None else None

    if mode in (None, 'slice'):
        return sl
    if mode == 'raw':
        return (start, stop, sl.step)
    if stop is None:
        raise ValueError("Open-ended slice (stop=None) requires n_items.")

    res = range(start, stop, step)
    if transform in ('mask', 'invert'):
        if n_items is None:
            raise ValueError(f"transform={transform!r} requires n_items.")
        indices = list(res)
    
        if transform == 'mask':
            mask = [False] * n_items
            for i in indices:
                mask[i] = True
            res = mask
    
        if transform == 'invert':
            res = sorted(set(range(n_items)) - set(indices))

    if mode == 'list':
        result = list(res)
    elif mode == 'tuple':
        result = tuple(res)
    elif mode == 'set':
        result = set(res)
    else:
        result = res
        
    return result    
    
def parse_keyword(text, zero_based=True, total=None):
    t = text.strip().lower().replace ("  ", " ")

    if t in ("odd", "odds", "odd pages"):
        return (lambda idx: idx % 2 == 1) if zero_based else (lambda idx: idx % 2 == 0)
    if t in ("even", "evens", "even pages"):
        return (lambda idx: idx % 2 == 0) if zero_based else (lambda idx: idx % 2 == 1)

    if "," in t:
        nums = [int(x.strip()) for x in t.split(",")]
        return [n - 1 for n in nums] if zero_based else nums

    if t == "first":
        return (0 if zero_based else 1, 1 if zero_based else 2)

    if t == "last":
        return (-1, None)

    if t.startswith("first "):
        n = int(t.split()[1])
        return (0, n)

    if t.startswith("last "):
        n = int(t.split()[1])
        if total is not None:
            return (total - n, total)
        return (-n, None)
        
    if t.startswith("except "):
        n = int(t.split()[1])
        return (n, None)

    if t.startswith("except last "):
        n = int(t.split()[2])
        return (None, -n)

    if t.endswith(" onwards"):
        n = int(t.split()[0])
        return (n - 1, None)

    if t.startswith("till "):
        n = int(t.split()[1])
        return (None, n - 1)

    if " thru " in t:
        a, b = t.split(" thru ")
        a, b = int(a), int(b)
        return (a - 1, b)

    if t.startswith("middle "):
        if total is None:
            raise ValueError("middle <n> requires total=")

        n = int(t.split()[1])
        half = n // 2

        mid = total // 2
        start = mid - half
        end = start + n

        return (start, end)

    raise ValueError(f"Unrecognized range expression: {text}")
