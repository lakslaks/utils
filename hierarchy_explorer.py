"""
hierarchy_explorer.py

A lightweight utility for loading, exploring, querying, composing, and diffing
hierarchical data structures (nested dict/list "trees").

Supported inputs:
- Python dict / list (used as-is)
- File path: .yaml/.yml, .json, .ini
- String payload: YAML/JSON (and INI if fmt="ini")

Core features:
- Walk keys (including list indices)
- Flatten to path -> scalar mapping
- Get values via dotted paths (supports quoted keys containing dots)
- Smart lookup by partial key / regex
- Deep merge and sequential composition
- Human-readable diff report

Notes:
- Paths use `sep` (default ".") and list indices are numeric segments.
- Keys that contain the separator can be addressed by quoting them:
  e.g., explorer.get_value("a.'b.c'.d")
"""

from __future__ import annotations

# Standard library
import configparser
import json
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional, Sequence, Union

# Third‑party
from ruamel.yaml import YAML

JsonLike = Union[Dict[str, Any], List[Any]]
Source = Union[str, JsonLike]

@dataclass(frozen=True)
class SmartGetDebug:
    """Optional structured debug response for `smart_get(..., debug=True)`."""

    query: str
    resolved_key: str
    optimistic: bool
    keys_only: bool
    result: Any


class HierarchyExplorer:
    """
    Explore and operate on hierarchical data structures (nested dict/list trees).

    Args:
        src: A dict/list, file path, or YAML/JSON/INI string.
        optimize_read: If True, precompute a flattened mapping for faster searches.
        sep: Path separator used for key navigation (default ".").
        fmt: Force a format when `src` is a string (e.g., "ini", "yaml", "json").
        get: "smart" uses `smart_get`, otherwise uses `get_value` for `self.get`.
    """

    def __init__(
        self,
        src: Optional[Source] = None, optimize_read: bool = True,
        sep: str = ".", fmt: Optional[Literal["ini", "yaml", "json"]] = None,
        get: Optional[Literal["smart", "value"]] = None,
    ) -> None:
        self.yaml = YAML(typ="safe")
        self.sep = sep
        self._inp: Optional[Source] = src
        self._fmt = fmt
        self._data: Optional[JsonLike] = None
        self._optimize = optimize_read
        self.kv_pair: Optional[Dict[str, Any]] = None

        if src is not None:
            self._data = self._load(self._inp)
            if self._optimize:
                self.kv_pair = self.flatten()

        self.get = self.smart_get if get == "smart" else self.get_value

    def __repr__(self) -> str:
        return repr(self._data)

    def __str__(self) -> str:
        return str(self.kv_pair or self.data)

    def __getitem__(self, key: str) -> Any:
        return self.get_value(key)

    @property
    def source(self) -> Optional[Source]:
        """Original input source passed to the explorer (path/string/object)."""
        return self._inp

    @property
    def data(self) -> Optional[JsonLike]:
        """Loaded hierarchical data (dict/list)."""
        return self._data

    @property
    def size(self) -> Any:
        """Approximate size of the explorer and loaded data in bytes."""
        return self.get_sizeof()

    # ----------------------------- traversal helpers -----------------------------

    def _walk(self, data: Any, prefix: str = "") -> List[str]:
        """Return a list of all reachable path keys in a nested dict/list tree."""
        keys: List[str] = []
        if isinstance(data, dict):
            for k, v in data.items():
                p = f"{prefix}{self.sep}{k}" if prefix else str(k)
                keys.append(p)
                keys.extend(self._walk(v, p))
        elif isinstance(data, list):
            for i, v in enumerate(data):
                p = f"{prefix}{self.sep}{i}" if prefix else str(i)
                keys.append(p)
                keys.extend(self._walk(v, p))
        return keys

    def _flatten(self, data: Any, prefix: str = "") -> Dict[str, Any]:
        """
        Flatten a nested dict/list tree into a mapping of "path" -> scalar values.

        Only leaf/scalar values are emitted; container nodes are not included.
        """
        flat: Dict[str, Any] = {}
        if isinstance(data, dict):
            for k, v in data.items():
                p = f"{prefix}{self.sep}{k}" if prefix else str(k)
                if isinstance(v, (dict, list)):
                    flat.update(self._flatten(v, p))
                else:
                    flat[p] = v
        elif isinstance(data, list):
            for i, v in enumerate(data):
                p = f"{prefix}{self.sep}{i}" if prefix else str(i)
                if isinstance(v, (dict, list)):
                    flat.update(self._flatten(v, p))
                else:
                    flat[p] = v
        return flat

    # ------------------------------ load / merge --------------------------------

    def _load(self, inp: Optional[Source]) -> JsonLike:
        """
        Load hierarchical data from an object, file path, or text payload.

        Returns:
            A dict or list loaded from the input.
        """
        if inp is None:
            raise ValueError("No input provided")

        if isinstance(inp, (dict, list)):
            return inp

        if isinstance(inp, str) and os.path.isfile(inp):
            ext = os.path.splitext(inp)[1].lower()
            with open(inp, "r", encoding="utf-8") as f:
                if self._fmt == "ini" or ext == ".ini":
                    cp = configparser.ConfigParser()
                    cp.read_file(f)
                    return {s: dict(cp[s]) for s in cp.sections()}
                if self._fmt == "yaml" or ext in (".yaml", ".yml"):
                    loaded = self.yaml.load(f)
                    return loaded if loaded is not None else {}
                if self._fmt == "json" or ext == ".json":
                    return json.load(f)
                raise ValueError(f"Unsupported file type: {ext}")

        # String payload
        if self._fmt == "ini":
            cp = configparser.ConfigParser()
            cp.read_string(inp)
            return {s: dict(cp[s]) for s in cp.sections()}

        # Prefer YAML, fallback to JSON
        try:
            loaded = self.yaml.load(inp)
            return loaded if loaded is not None else {}
        except Exception:
            return json.loads(inp)

    def _deep_merge(self, base: Any, override: Any) -> Any:
        """
        Recursively merge `override` into `base`.

        - dict + dict: merge keys recursively
        - list + list: merge index-wise (extend if override longer)
        - otherwise: override wins
        """
        if isinstance(base, dict) and isinstance(override, dict):
            for k, v in override.items():
                base[k] = self._deep_merge(base.get(k), v) if k in base else v
            return base

        if isinstance(base, list) and isinstance(override, list):
            for i, v in enumerate(override):
                if i < len(base):
                    base[i] = self._deep_merge(base[i], v)
                else:
                    base.append(v)
            return base

        return override

    def reload(self) -> None:
        """Reload data from the original source (only valid if `src` was provided)."""
        if self._inp is None:
            raise ValueError("No source provided to reload")
        self._data = self._load(self._inp)
        if self._optimize:
            self.kv_pair = self.flatten()

    def flatten(self, inp: Optional[Source] = None) -> Dict[str, Any]:
        """Return a flattened mapping (path -> scalar) for `inp` or current data."""
        data = self._load(inp) if inp is not None else self._data
        if data is None:
            raise ValueError("No data loaded")
        return self._flatten(data)

    def append(self, delta: Source) -> JsonLike:
        """
        append `delta` into `baseline` and set the result as the explorer data.

        Supports two delta styles:
        1) Hierarchical dict/list (deep merged)
        2) "Flat patch" dict where keys are path strings containing the separator

        Example flat patch:
            {"a.b": 1, "x.0.y": "z"}
        """
        return self.update (self.data, delta)

    
    def update(self, baseline: Source, delta: Source) -> JsonLike:
        """
        Merge `delta` into `baseline` and set the result as the explorer data.

        Supports two delta styles:
        1) Hierarchical dict/list (deep merged)
        2) "Flat patch" dict where keys are path strings containing the separator

        Example flat patch:
            {"a.b": 1, "x.0.y": "z"}
        """
        base = self._load(baseline)
        upd = self._load(delta)

        if (
            isinstance(upd, dict)
            and all(isinstance(k, str) for k in upd.keys())
            and any(self.sep in k for k in upd.keys())
        ):
            # Apply as path patches
            for path, val in upd.items():
                parts = path.split(self.sep)
                target: Any = base
                for seg in parts[:-1]:
                    target = self._ensure_child_container(target, seg)
                self._assign_leaf(target, parts[-1], val)
        else:
            base = self._deep_merge(base, upd)

        self._data = base
        if self._optimize:
            self.kv_pair = self.flatten()
        return self._data

    def _ensure_child_container(self, target: Any, seg: str) -> Any:
        """
        Ensure the next container exists for an intermediate path segment.

        Fix: handles numeric segments reliably by creating/expanding lists when needed,
        instead of assuming the current container is already a list.
        """
        if seg.isdigit():
            idx = int(seg)
            if not isinstance(target, list):
                # If target is None or dict but we need list semantics, replace with list.
                # This is a deliberate, predictable rule for numeric path segments.
                target_list: List[Any] = []
                # If target was a dict with data, we cannot sensibly preserve it here.
                # Caller-controlled patches should avoid such conflicting shapes.
                target = target_list
            while len(target) <= idx:
                target.append({})
            return target[idx]

        if not isinstance(target, dict):
            target = {}
        if seg not in target or not isinstance(target[seg], (dict, list)):
            target[seg] = {}
        return target[seg]

    def _assign_leaf(self, target: Any, seg: str, val: Any) -> None:
        """Assign a leaf value under `target` for the final segment `seg`."""
        if seg.isdigit():
            idx = int(seg)
            if not isinstance(target, list):
                raise TypeError(f"Cannot assign numeric segment '{seg}' into non-list container")
            while len(target) <= idx:
                target.append({})
            target[idx] = val
            return

        if not isinstance(target, dict):
            raise TypeError(f"Cannot assign key '{seg}' into non-dict container")
        target[seg] = val

    def compose(self, files: Sequence[Source]) -> JsonLike:
        """
        Sequentially deep-merge multiple sources into a runtime config/tree.

        The first element is the baseline; each subsequent element overrides.
        """
        if not files:
            raise ValueError("No files provided")
        runtime = self._load(files[0])
        for f in files[1:]:
            runtime = self._deep_merge(runtime, self._load(f))
        self._data = runtime
        if self._optimize:
            self.kv_pair = self.flatten()
        return self._data

    # ------------------------------ section utils --------------------------------

    @staticmethod
    def load_section(source: str, stringify: bool = False, **kwargs: Any) -> Dict[str, Union[List[str], str]]:
        """
        Load INI-like sections as raw lines, optionally as a formatted string.

        This is useful for "partial parsing" of config files where strict INI
        parsing isn't desired, or where sections contain arbitrary content.

        Args:
            source: Path to the text file.
            stringify: If True, each section is returned as a string.
            **kwargs: Passed to `stringify()` when stringify=True.
        """
        cache: Dict[str, List[str]] = {}
        with open(source, encoding="utf-8") as f:
            current: Optional[str] = None
            for raw_line in f:
                line = raw_line.rstrip("\n")
                if not line.strip():
                    continue
                if line.startswith("[") and line.endswith("]"):
                    current = line.strip()[1:-1]
                    cache[current] = []
                elif current:
                    cache[current].append(line)

        if stringify:
            return {k: self.stringify(v, **kwargs) for k, v in cache.items()}
        return cache

    def stringify(
        self,
        lst_lines: Sequence[str], replace: Optional[Dict[str, str]] = None,
        padding: str = "  ", sep: str = "\n",
        prefix: str = "", suffix: str = "",
        replace_strict: bool = False,
        **_: Any,
    ) -> str:
        """
        Convert a list of lines into a formatted string with optional replacements.

        Args:
            lst_lines: The lines to join.
            replace: Optional mapping of pattern -> replacement.
            padding: Prefix each joined line with this padding (via join filler).
            sep: Separator between lines.
            prefix: Optional prefix for the entire string.
            suffix: Optional suffix for the entire string.
            replace_strict: If True, replacement keys are treated as whole words.
        """
        filler = f"{sep}{padding}"
        eff_prefix = padding if prefix in ("default", "line_padding") else prefix
        s = eff_prefix + filler.join(lst_lines)

        if replace and isinstance(replace, dict):
            for k, v in replace.items():
                pat, sub = (rf"\b{k}\b", rf"{v}") if replace_strict else (k, v)
                s = re.sub(pat, sub, s)
        return s + suffix

    # ------------------------------ persistence ----------------------------------

    def save(self, tgt: str, src: Optional[Source] = None, fmt: Literal["json", "yaml", "txt"] = "json") -> None:
        """
        Save a hierarchical structure to disk.

        fmt="txt" writes the flattened mapping as `key=value` lines.
        """
        data = self._data if src is None else self._load(src)

        if fmt == "json":
            with open(tgt, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return

        if fmt == "yaml":
            yaml = YAML()
            yaml.default_flow_style = False
            yaml.indent(mapping=2, sequence=4, offset=2)
            with open(tgt, "w", encoding="utf-8") as f:
                yaml.dump(data, f)
            return

        if fmt == "txt":
            flat = self._flatten(data)
            with open(tgt, "w", encoding="utf-8") as f:
                for k, v in flat.items():
                    f.write(f"{k}={v}\n")
            return

        raise ValueError(f"Unsupported fmt: {fmt}")

    # ------------------------------ diff / report --------------------------------

    def diffrep(
        self,
        comparator: Source, baseline: Optional[Source] = None,
        filter_results: Optional[Union[str, Sequence[str]]] = None,
        sep: str = ".",
    ) -> List[str]:
        """
        Compare two hierarchical dict datasets (baseline vs comparator).

        Returns:
            A list of diff lines in baseline key order.

        Filter Symbols:
          == k: v                 (match)
          <> k: baseline # value  (values differ)
          <= k: v                 (missing key in comparator)
          => k: v                 (additional key in comparator)

        Notes:
            - Currently, diff is dict-focused to preserve key order; lists are treated
              as leaf values (reported as changed) if encountered at a compared node.
        """
        if baseline is None:
            if self._data is None:
                raise ValueError("No baseline data available")
            base_obj: Any = self._data
        else:
            base_obj = self._load(baseline)

        comp_obj: Any = self._load(comparator)

        if not isinstance(base_obj, dict) or not isinstance(comp_obj, dict):
            raise TypeError("diffrep currently supports dict baselines/comparators only")

        def _diff_dict(base: Dict[str, Any], inc: Dict[str, Any], prefix: str = "") -> List[str]:
            lines: List[str] = []
            base_keys = list(base.keys())  # preserve baseline order
            extra_keys = [k for k in inc.keys() if k not in base]

            for k in base_keys:
                path = f"{prefix}{sep}{k}" if prefix else k
                if k not in inc:
                    lines.append(f"<= {path}: {base[k]}")
                    continue

                bval, ival = base[k], inc[k]
                if isinstance(bval, dict) and isinstance(ival, dict):
                    lines.extend(_diff_dict(bval, ival, prefix=path))
                else:
                    lines.append(f"== {path}: {bval}" if bval == ival else f"<> {path}: {bval} # {ival}")

            for k in extra_keys:
                path = f"{prefix}{sep}{k}" if prefix else k
                lines.append(f"=> {path}: {inc[k]}")

            return lines

        lines = _diff_dict(base_obj, comp_obj)

        if filter_results:
            tokens = filter_results.split(",") if isinstance(filter_results, str) else list(filter_results)
            tokens = [t.strip() for t in tokens]
            lines = [ln for ln in lines if ln[:2] in tokens]

        return lines

    # ------------------------------ memory sizing --------------------------------

    def get_sizeof(self, obj: Any = None, enhanced_results: bool = False) -> Any:
        """
        Return approximate memory size.

        Args:
            obj: Optional input object. If None, sizes of self and self.data are returned.
            enhanced_results: If True and `obj` provided, return a dict with metadata.

        Note:
            Uses pympler if available, otherwise falls back to sys.getsizeof.
        """
        try:
            from pympler.asizeof import asizeof as sizer  # type: ignore
            method = "pympler (enhanced)"
        except Exception:
            from sys import getsizeof as sizer  # type: ignore
            method = "sys (default)"

        if obj is None:
            return {"method": method, "obj": f"{sizer(self):,} bytes", "data": f"{sizer(self.data):,} bytes"}

        return sizer(obj) if not enhanced_results else {"method": method, "input object": f"{sizer(obj):,} bytes"}

    # ------------------------------- key access ----------------------------------

    def get_keys(
        self,
        path: Optional[str] = None,
        inp: Optional[Source] = None,
        start: Optional[str] = None,
        reload: bool = False,
    ) -> List[str]:
        """
        Return all reachable path keys under `start` and/or `path`.

        Args:
            path: Navigate from the resolved starting node further down.
            inp: Optional alternative input source to load.
            start: Path used to choose a starting sub-tree.
            reload: If True, reload from original source before exploring.
        """
        if reload:
            self.reload()
        data: Any = self._load(inp) if inp is not None else self._data
        if data is None:
            raise ValueError("No data loaded")

        node: Any = data
        for p in (start.split(self.sep) if start else []):
            node = node[int(p)] if p.isdigit() else node[p]
        for p in (path.split(self.sep) if path else []):
            node = node[int(p)] if p.isdigit() else node[p]

        return self._walk(node)

    def smart_get(self, key: str, optimistic: bool = True, **kwargs: Any) -> Any:
        """
        Flexible lookup by partial key name or regex over flattened paths.

        Behavior:
        - If direct path lookup works (get_value), return it.
        - Else search flattened paths for matches and return:
          optimistic=True: return the shallowest resolved subtree/value
          optimistic=False: return a dict of all matches (path -> value)

        Special key forms:
        - '^abc' : prefer matches that begin with abc (or contain '.abc')
        - 'abc$' : prefer matches that end with abc (or contain 'abc.')
        - regex=True : treat the key as a regex pattern (otherwise escaped)

        kwargs:
            keys_only: If True, return only keys at the resolved subtree (if dict).
            debug: If True, return a dict-like debug payload.
            regex: If True, treat `key` as regex (do not escape).
        """
        keys_only = bool(kwargs.get("keys_only", False))
        debug = bool(kwargs.get("debug", False))
        regex_mode = bool(kwargs.get("regex", False))

        # Fast path: direct lookup
        if not any([keys_only, debug, regex_mode]):
            res = self.get_value(key, default={})
            if res:
                return res

        # Ensure we have a flattened map
        flat = self.kv_pair if (self._optimize and self.kv_pair is not None) else self.flatten()

        # Build regex pattern
        if key.startswith("^"):
            pattern = rf"(?:^{re.escape(key[1:])}|\.{re.escape(key[1:])})" if not regex_mode else rf"(?:^{key[1:]}|\.{key[1:]})"
        elif key.endswith("$"):
            pattern = rf"(?:{re.escape(key[:-1])}$|{re.escape(key[:-1])}\.)" if not regex_mode else rf"(?:{key[:-1]}$|{key[:-1]}\.)"
        else:
            pattern = key if regex_mode else re.escape(key)

        regex = re.compile(pattern)
        matches = [k for k in flat.keys() if regex.search(k)]
        if not matches:
            return None

        resolved_key: Optional[str] = None

        if optimistic:
            m = regex.search(matches[0])
            n = matches[0].find(self.sep, m.end()) if m else -1
            resolved_key = matches[0] if n == -1 else matches[0][:n]
            resolved_value = self.get_value(resolved_key)

            if keys_only and isinstance(resolved_value, dict):
                result: Any = list(resolved_value.keys())
            else:
                result = resolved_value
        else:
            resolved_key = "NA"
            if keys_only:
                # When returning multiple matches and keys_only, return keys of each subtree if dict.
                result = {
                    k: (list(v.keys()) if isinstance(v, dict) else v)
                    for k in matches
                    for v in [self.get_value(k)]
                }
            else:
                result = {k: self.get_value(k) for k in matches}

        if debug:
            return {
                "query": key,
                "resolved_key": resolved_key or "NA",
                "optimistic": optimistic,
                "keys_only": keys_only,
                "result": result,
            }
        return result

    def sget (self, key: str, **kwargs: Any) -> Any:
        return self.smart_get (key, **kwargs)

    sget.__doc__ = smart_get.__doc__

    def get_value(self, path: str, src: Optional[Source] = None, default: Any = None, **_: Any) -> Any:
        """
        Fetch a value by path, supporting quoted key segments that contain the separator.

        Example:
            path="a.'b.c'.d"  -> accesses data["a"]["b.c"]["d"]
        """
        data: Any = self._data if src is None else self._load(src)
        if data is None:
            raise ValueError("No data loaded")

        # Split on sep, but ignore separators inside quotes.
        pattern = rf"{re.escape(self.sep)}(?=(?:[^'\"]*['\"][^'\"]*['\"])*[^'\"]*$)"
        try:
            for part in re.split(pattern, str(path)):
                if re.match(r"^(['\"])(.*)\1$", part):
                    part = part[1:-1]

                if part.isdigit():
                    idx = int(part)
                    if not isinstance(data, list) or idx >= len(data):
                        return default
                    data = data[idx]
                else:
                    if not isinstance(data, dict) or part not in data:
                        return default
                    data = data[part]
            return data
        except (KeyError, IndexError, TypeError):
            return default

    def search(self, keystr: str, ret_type: Literal["keys", "dict"] = "keys", inp: Optional[Source] = None) -> Any:
        """
        Search flattened paths by regex pattern.

        Args:
            keystr: Regex pattern to search within flattened keys.
            ret_type: "keys" returns list of matching paths; "dict" returns path->value.
            inp: Optional input to search (otherwise uses cached flatten if enabled).
        """
        data = self._load(inp) if inp is not None else (self.kv_pair if self._optimize else self.flatten())
        if not isinstance(data, dict):
            raise ValueError("No data loaded or non-dict flatten source")

        matches = [k for k in data.keys() if re.search(keystr, k)]
        return {k: data[k] for k in matches} if ret_type == "dict" else matches
    
    class DotDict(dict):
        """Dict subclass with recursive dot-access, preserving dict behaviour."""
        def __getattr__(self, key):
            try:
                val = self[key]
                return HierarchyExplorer.DotDict(val) if isinstance(val, dict) else val
            except KeyError:
                raise AttributeError(key)
        def __dir__(self):
            return list(self.keys())                
    
    def as_dict(self, obj=None) -> "HierarchyExplorer.DotDict":
        """Recursively convert dicts and lists to DotDict."""
        obj = obj if obj is not None else self.data
        if isinstance(obj, dict):
            return HierarchyExplorer.DotDict({k: self.as_dict(v) for k, v in obj.items()})
        if isinstance(obj, list):
            return [self.as_dict(i) for i in obj]
        return obj
    
ConfigExplorer = HierarchyExplorer
TreeExplorer   = HierarchyExplorer
DictExplorer   = HierarchyExplorer

