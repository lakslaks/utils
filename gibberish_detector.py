import re
import math
from collections import Counter
import unicodedata


_ENGLISH_FREQ: dict[str, float] = {
    'a': .082, 'b': .015, 'c': .028, 'd': .043, 'e': .127, 'f': .022,
    'g': .020, 'h': .061, 'i': .070, 'j': .002, 'k': .008, 'l': .040,
    'm': .024, 'n': .067, 'o': .075, 'p': .019, 'q': .001, 'r': .060,
    's': .063, 't': .091, 'u': .028, 'v': .010, 'w': .023, 'x': .001,
    'y': .020, 'z': .001,
}

_KEYBOARD_RUNS: list[str] = [
    "qwertyuiop", "poiuytrewq",
    "asdfghjkl",  "lkjhgfdsa",
    "zxcvbnm",    "mnbvcxz",
    "1234567890", "0987654321",
    "abcdefghijklmnopqrstuvwxyz", "zyxwvutsrqponmlkjihgfedcba",
]

_VOWELS: frozenset[str] = frozenset('aeiouAEIOU')


class GibberishDetector:
    """Detects garbage/mash input in a single field, a list of values, or a form dict.

    All three entry points return a consistent result structure so callers
    can handle them uniformly. Per-field results always include a 'gibberish'
    bool, a 'reason' string or None, and the original 'value'.

    Form-level detection adds cross-field signals (keyboard adjacency across
    fields, uniform entropy, duplicate values) on top of per-field checks.
    Normalisation strips noise characters and Unicode lookalikes before all
    comparisons, preventing salting/injection workarounds.

    Usage:
        detector = GibberishDetector()

        detector.is_gibberish("asdfqwer")
        detector.is_gibberish(["asdf", "qwer", "zxcv"])
        detector.is_gibberish({"name": "asdf", "city": "qwer", "job": "zxcv"})
    """

    def __init__(
        self,
        min_run_length: int = 4,
        per_field_entropy_threshold: float = 6.5,
        form_entropy_threshold: float = 5.8,
        min_flagged_ratio: float = 0.5,
        min_consonant_run: int = 6,
        min_repetition: int = 4,
        max_duplicate_fields: int = 2,
    ) -> None:
        self.min_run_length = min_run_length
        self.per_field_entropy_threshold = per_field_entropy_threshold
        self.form_entropy_threshold = form_entropy_threshold
        self.min_flagged_ratio = min_flagged_ratio
        self.min_consonant_run = min_consonant_run
        self.min_repetition = min_repetition
        self.max_duplicate_fields = max_duplicate_fields
        self.last_result: dict | None = None          # ← stores last is_gibberish output
    
    
    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_gibberish(self, input_data: str | list | dict) -> dict:
        """Dispatches to the appropriate checker based on input type.
    
        Result is stored in self.last_result for subsequent summarise() calls.
        """
        if isinstance(input_data, str):
            result = self.check_field(input_data)
        elif isinstance(input_data, list):
            result = self.check_fields(input_data)
        elif isinstance(input_data, dict):
            result = self.check_form(input_data)
        else:
            raise TypeError(
                f"Expected str, list, or dict — got {type(input_data).__name__!r}"
            )
        self.last_result = result
        return result
    
    
    def check_field(self, value: str) -> dict:
        """Check a single field value.

        Returns {'gibberish': bool, 'reason': str | None, 'value': str}.
        """
        reason = self._field_reason(value, self.per_field_entropy_threshold)
        return {'gibberish': reason is not None, 'reason': reason, 'value': value}

    def check_fields(self, values: list[str]) -> dict:
        """Check an ordered collection of field values without named keys.

        Returns an overall verdict plus a per-index breakdown.
        """
        named = {str(i): v for i, v in enumerate(values)}
        result = self._check_named(named)
        result['fields'] = {int(k): v for k, v in result['fields'].items()}
        return result

    def check_form(self, fields: dict[str, str]) -> dict:
        """Check a dict of field-name → value pairs.

        Returns {'gibberish': bool, 'reason': str | None,
                 'fields': {name: {gibberish, reason, value}}}.
        """
        return self._check_named(fields)

    # ------------------------------------------------------------------
    # Normalisation
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise(value: str) -> str:
        """Strips noise characters and Unicode lookalikes before comparisons.

        Applies NFKD normalisation to catch lookalike characters (е → e),
        then removes everything that is not a plain ASCII letter.
        """
        nfkd = unicodedata.normalize('NFKD', value.strip().lower())
        return re.sub(r'[^a-z]', '', nfkd)

    # ------------------------------------------------------------------
    # Core single-field logic
    # ------------------------------------------------------------------
    def _extract_local(self, value: str) -> str:
        """For email-shaped input, returns only the local part before @."""
        if re.match(r'^[^@\s]+@[^@\s]+$', value.strip()):
            return value.strip().split('@')[0]
        return value
    
    def _field_reason(self, text: str, entropy_threshold: float) -> str | None:
        if not isinstance(text, str) or not text.strip():
            return None
    
        # For emails, analyse the local part — the domain skews all checks
        analysed = self._extract_local(text)
    
        lower = analysed.strip().lower()
        no_spaces = ''.join(lower.split())
        normalised = self._normalise(analysed)
        alpha_chars = [c for c in lower if c.isalpha()]
        is_ascii_alpha = all(c.isascii() for c in alpha_chars)
    
        if len(normalised) >= self.min_run_length:
            for i in range(len(normalised) - self.min_run_length + 1):
                sub = normalised[i:i + self.min_run_length]
                if any(sub in pattern for pattern in _KEYBOARD_RUNS):
                    return 'keyboard_run'
    
        if re.search(rf'(.)\1{{{self.min_repetition},}}', no_spaces):
            return 'repeated_chars'
    
        # Lower the alpha threshold for short inputs
        min_alpha = 3 if len(normalised) <= 5 else 4
        if is_ascii_alpha and len(alpha_chars) >= min_alpha:
            if not any(c in _VOWELS for c in alpha_chars):
                return 'no_vowels'
    
        if is_ascii_alpha:
            if re.search(rf'[^aeiou\W\d_]{{{self.min_consonant_run},}}', lower):
                return 'consonant_run'
    
        # Lower the alpha threshold for cross-entropy too
        min_entropy_alpha = 4 if len(normalised) <= 5 else 6
        if is_ascii_alpha and len(alpha_chars) >= min_entropy_alpha:
            if self._cross_entropy(analysed) > entropy_threshold:
                return 'low_entropy'
    
        return None
        
    # ------------------------------------------------------------------
    # Cross-field logic
    # ------------------------------------------------------------------

    def _check_named(self, fields: dict[str, str]) -> dict:
        """Core implementation shared by check_fields and check_form."""
        if not fields:
            return {'gibberish': False, 'reason': None, 'fields': {}}

        field_results: dict = {}
        hard_flags = 0
        soft_flags = 0

        for name, value in fields.items():
            hard_reason = self._field_reason(value, self.per_field_entropy_threshold)
            soft_reason = (
                self._field_reason(value, self.form_entropy_threshold)
                if hard_reason is None else None
            )
            field_results[name] = {
                'value': value,
                'gibberish': hard_reason is not None,
                'reason': hard_reason,
                'soft_flag': soft_reason is not None,
            }
            if hard_reason:
                hard_flags += 1
            elif soft_reason:
                soft_flags += 1

        if hard_flags:
            return {'gibberish': True, 'reason': 'hard_flag', 'fields': field_results}

        flagged_ratio = (hard_flags + soft_flags) / len(fields)
        if flagged_ratio >= self.min_flagged_ratio:
            return {
                'gibberish': True,
                'reason': 'pattern_across_fields',
                'fields': field_results,
            }

        if self._keyboard_adjacent_across_fields(fields):
            return {
                'gibberish': True,
                'reason': 'keyboard_adjacency_across_fields',
                'fields': field_results,
            }

        if self._duplicate_values_across_fields(fields):
            return {
                'gibberish': True,
                'reason': 'duplicate_values_across_fields',
                'fields': field_results,
            }

        return {'gibberish': False, 'reason': None, 'fields': field_results}

    def _keyboard_adjacent_across_fields(self, fields: dict[str, str]) -> bool:
        """Returns True if leading chars across fields form a keyboard run after normalisation."""
        leads = ''.join(
            self._normalise(v)[:3]
            for v in fields.values()
            if isinstance(v, str) and v.strip()
        )
        if len(leads) < self.min_run_length:
            return False
        for i in range(len(leads) - self.min_run_length + 1):
            if any(leads[i:i + self.min_run_length] in p for p in _KEYBOARD_RUNS):
                return True
        return False

    def _duplicate_values_across_fields(self, fields: dict[str, str]) -> bool:
        """Returns True if any normalised value appears in more than max_duplicate_fields fields."""
        normalised = [
            self._normalise(v)
            for v in fields.values()
            if isinstance(v, str) and v.strip()
        ]
        counts = Counter(normalised)
        return any(count > self.max_duplicate_fields for count in counts.values())

    # ------------------------------------------------------------------
    # Entropy helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _entropy(text: str) -> float:
        """Shannon entropy of a string."""
        n = len(text)
        return -sum((c / n) * math.log2(c / n) for c in Counter(text).values())

    @staticmethod
    def _cross_entropy(text: str) -> float:
        """Surprisal of text relative to English letter frequencies."""
        letters = [c for c in text.lower() if c.isalpha()]
        if not letters:
            return 0.0
        return -sum(
            math.log2(_ENGLISH_FREQ.get(c, 0.001)) for c in letters
        ) / len(letters)


    def summarise(self, result: dict | None = None, show: str = 'failed') -> dict:
        """Extracts passed or failed fields from a gibberish check result.
    
        If result is not provided, uses the last result from is_gibberish().
    
        Args:
            result: A result dict from any check_* method. Defaults to last_result.
            show: 'failed' returns only gibberish fields (default).
                  'passed' returns only clean fields.
                  'all' returns both with their status.
        """
        target = result if result is not None else self.last_result
        if target is None:
            raise RuntimeError("No result available — call is_gibberish() first.")
    
        if show not in ('failed', 'passed', 'all'):
            raise ValueError(f"show must be 'failed', 'passed', or 'all' — got {show!r}")
    
        if 'fields' not in target:
            matched = (
                (show in ('all', 'failed') and target['gibberish']) or
                (show == 'passed' and not target['gibberish'])
            )
            return {target['value']: target['gibberish']} if matched else {}
    
        fields = target['fields']
    
        if show == 'failed':
            filtered = {k: v['value'] for k, v in fields.items() if v['gibberish'] or v.get('soft_flag')}
        elif show == 'passed':
            filtered = {k: v['value'] for k, v in fields.items() if not v['gibberish'] and not v.get('soft_flag')}
        else:
            filtered = {k: v['value'] for k, v in fields.items()}
    
        return filtered