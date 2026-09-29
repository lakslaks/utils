"""
Filename: iterutils.py
Author: Laks Laks
Version: 0.1
Last Updated: 2027‑02‑26

Utility helpers for normalization, selection, and return‑value post‑processing.

This module provides:
- to_list          : Normalize strings, lists, and tuples into list form.
- flatten          : Expand mixed iterables and scalars into a single sequence.
- get_argmax       : Retrieve the maximum element or its associated index/key.
- get_argmin       : Retrieve the minimum element or its associated index/key.
- itereval         : Decorator for consistent post‑processing (sorting,
                     transforms, type coercion).
- transform        : Apply one or more functions to values or iterables.
- to_distribution  : Convert iterable into probability-like distribution using
                     simple normalization or softmax

All public helpers are designed to be composable, predictable, and override‑friendly.
Internal helpers are intentionally lightweight and explicit in behavior.
"""

from typing import Literal, Callable, Iterable, TypeVar, Union, Optional, Any, Tuple, Dict, List
from functools import wraps
from collections.abc import Iterable as ABCIterable
import numpy as np

T = TypeVar("T")

def itereval(
    func: Optional[Callable] = None,
    *,
    sort: Optional[Literal["asc", "desc"]] = None,
    elem_transforms: Optional[Union[Callable[[T], T], Iterable[Callable[[T], T]]]] = None,
    iter_transforms: Optional[Union[Callable[[T], T], Iterable[Callable[[T], T]]]] = None,
    return_type: Optional[Callable[[Iterable[T]], Iterable[T]]] = None,
) -> Callable:
    """
    Decorator that post‑processes a function’s return value using optional
    sorting, element‑level transforms, iterable‑level transforms, and type
    coercion. Call‑time keyword arguments override decorator defaults.

    Behavior
    --------
    • If the wrapped function returns ``None``, the value is returned unchanged.

    • If the return value is a ``dict`` and ``elem_transforms`` is provided,
      the decorator applies the element‑level transforms **only to the dict’s
      values**, preserving keys. No sorting, iterable‑level transforms, or
      type coercion are applied to dicts.

    • For all non‑dict iterables:
        - ``sort`` (``"asc"`` or ``"desc"``) sorts the iterable.
        - ``elem_transforms`` applies element‑wise transforms to each item.
        - ``iter_transforms`` applies whole‑iterable transforms sequentially.
        - ``return_type`` (or the original type if omitted) is used to
          reconstruct the final output when possible.

    • Call‑time overrides (``sort=``, ``elem_transforms=``, etc.) take
      precedence over decorator‑level defaults.

    Returns
    -------
    Callable
        A wrapped function whose output is post‑processed according to the
        specified rules.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # call-time overrides

            rt = kwargs.pop("return_type", return_type)
            st = kwargs.pop("sort", sort)
            et = kwargs.pop("elem_transforms", elem_transforms)
            it = kwargs.pop("iter_transforms", iter_transforms)

            res = func(*args, **kwargs)
            if res is None: 
                return res
                
            if isinstance(res, dict) and et:
                return {k: _elem_transforms(v, et) for k, v in res.items()}
                
            orig_type = type(res)
            if st: res = sorted(res, key=lambda x: (x is None, x), reverse=(st == "desc"))
            if et: res = _elem_transforms(res, et)
            if it: res = _iter_transforms(res, it)
                
            final_type = rt or orig_type
            try:
                return final_type(res)
            except Exception:
                return res
        return wrapper
    return decorator(func) if func else decorator

def _iter_transforms(value: Any, pipeline: Optional[
        Union[
            Callable[[Any], Any],
            Tuple[Callable[[Any], Any], Dict[str, Any]],
            Iterable[Union[
                Callable[[Any], Any],
                Tuple[Callable[[Any], Any], Dict[str, Any]]
            ]]
        ]]) -> Any:
    """
    Apply one or more iterable‑level transforms to a value. Each transform may be
    either a callable applied directly to the entire iterable, or a tuple of the
    form `(func, params)` where `params` is a dict of keyword arguments passed to
    `func`. Transforms are applied sequentially in the order provided.

    Parameters
    ----------
    value : Any
        The value or iterable to transform.
    transforms : callable | (callable, dict) | iterable of these, optional
        One or more whole‑iterable transforms. A tuple `(func, params)` applies
        `func(value, **params)`.

    Returns
    -------
    Any
        The transformed value after all iterable‑level transforms have been
        applied.
    """
    if not pipeline: return value
    fns = pipeline if isinstance(pipeline, (list, tuple)) else [pipeline]
    for fn in fns:
        if isinstance(fn, tuple):
            func, params = fn
            value = func(value, **params)
        else:
            value = fn(value)
    return value

def _elem_transforms(
    value: Any,
    pipeline: Optional[Union[Callable[[Any], Any], Iterable[Union[
                    Callable[[Any], Any], tuple
        # (func, args, kwargs) OR (func, kwargs)
                ]]]] = None,
    inplace: bool = False,) -> Any:
    """
    Apply one or more transform functions to a value or iterable. Supports
    in‑place mutation for lists and preserves the original return type when
    possible.
    
    Note: Strings and bytes are treated as scalars, not iterables.
    """    
    if not pipeline:
        return value

    steps = pipeline if isinstance(pipeline, (list, tuple)) else [pipeline]

    is_iter = lambda x: hasattr(x, "__iter__") and not isinstance(x, (str, bytes, dict))
    original_type = type(value)

    if inplace and isinstance(value, list):
        res = value
    elif is_iter(value):
        res = list(value)
    else:
        res = value

    for step in steps:

        if callable(step): # --- callable
            apply = step
        
        elif isinstance(step, tuple) and len(step) == 2: # --- (func, kwargs) ---
            func, kwargs = step
            apply = lambda x, f=func, kw=kwargs: f(x, **kw)

        elif isinstance(step, tuple) and len(step) == 3: # --- (func, args, kwargs) ---
            func, args, kwargs = step
            apply = lambda x, f=func, a=args, kw=kwargs: f(x, *a, **kw)

        else:
            raise ValueError(f"Invalid transform step: {step}")

        if is_iter(res):
            for i in range(len(res)):
                res[i] = apply(res[i])
        else:
            res = apply(res)

    try:
        return original_type(res) if is_iter(value) else res
    except Exception:
        return res
       
@itereval
def to_list(var: Any, sep: str = ",") -> list:
    """
    Convert a value into a list.
    • Strings are split using `sep`.
    • Lists and tuples are copied.
    • All other values are wrapped in a single‑element list.
    • Sorting is applied if requested.
    """
    if isinstance(var, str):
        out = var.split(sep)
    elif isinstance(var, (list, tuple)):
        out = list(var)
    else:
        out = [var]
    return out

    
@itereval
def flatten(*args: Any) -> Any:
    """
    Flatten one or more values into a single iterable. If a single argument is
    provided, it is returned unchanged. If no arguments are provided, returns
    None. Iterables (excluding strings and bytes) are expanded; non‑iterables
    are appended as scalar values. This function is wrapped by `@itereval`
    """
    if (arg_len := len(args)) < 2: 
        return None if arg_len == 0 else args[0]
    is_iter = lambda x: hasattr(x, "__iter__") and not isinstance(x, (str, bytes))
    out_type = type(args[0]) if is_iter(args[0]) else list
    flat = []
    for x in args:
        flat.extend(x) if is_iter(x) else flat.append(x)
    try:
        return out_type(flat)
    except Exception:
        return flat

@itereval(sort=None)
def get_argmax(obj: Any, return_type: str = "value", **kwargs: Any) -> Any:
    """
    Return the maximum element or its associated index/key from `obj`, using
    `_argext` for selection logic. `return_type` controls whether the value,
    index/key, pair, or selected field is returned. Wrapped by `@itereval`.
    """
    return _argext (obj, return_type, reverse=False, **kwargs)

@itereval(sort=None)
def get_argmin(obj: Any, return_type: str = "value", **kwargs: Any) -> Any:
    """
    Return the minimum element or its associated index/key from `obj`, using
    `_argext` for selection logic. `return_type` controls the returned form.
    Wrapped by `@itereval`.
    """
    return _argext (obj, return_type, reverse=True, **kwargs)
   
def _argext(
    obj: Any,
    return_type: Literal['key', 'value', 'item', 'pair', 'selected'] = 'value',
    *,
    selector: Optional[Union[str, Callable[..., Any]]] = None,
    default: Any = None,
    topk: int = 1,
    reverse: bool = False,
    **kwargs: Any
) -> Any:
    """
    Internal helper implementing the core logic for `argmax` and `argmin`.
    Supports dicts, lists, tuples, and scalars by selecting elements based on
    a key function derived from `selector`. Returns the top‑k elements or their
    associated indices/keys depending on `return_type`.

    Notes:
    - Strings and bytes are treated as scalars.
    - Dicts support auto‑selector for dict‑of‑dicts.
    - Lists of dicts require an explicit selector.
    """
    if isinstance(obj, (str, int, float, bool)): # Normalize scalars
        obj = [obj]

    reverse = not reverse
    
    # Normalize selector
    if selector is None:
        if isinstance(obj, dict):
            # Auto-selector only for dict-of-dicts
            first_key = next(iter(obj))
            first_elem = obj[first_key]

            if isinstance(first_elem, dict) and first_elem:
                selector = next(iter(first_elem))
                key_fn = lambda x: x[selector]
            else:
                key_fn = lambda x: x

        elif isinstance(obj, (list, tuple)) and obj and isinstance(obj[0], dict):
            raise ValueError("Selector required for list of dicts")

        else:
            key_fn = lambda x: x

    elif callable(selector):
        key_fn = lambda x: selector(x, **kwargs)

    else:
        key_fn = lambda x: x[selector]

    if isinstance(obj, dict): # Dict case
        if not obj:
            return default

        cache = {k: key_fn(obj[k]) for k in obj}
        keys = sorted(cache, key=cache.get, reverse=reverse)[:topk]

        if topk == 1:
            k = keys[0]
            return {"key": k, "value": obj[k], "item": obj[k], "pair": (k, obj[k]), "selected": cache[k]}.get(return_type, k)

        if return_type == "key":
            return keys
        if return_type == "value":
            return [obj[k] for k in keys]
        if return_type == "item":
            return [obj[k] for k in keys]
        if return_type == "pair":
            return [(k, obj[k]) for k in keys]
        if return_type == 'selected':
            return [cache[k] for k in keys]
        return keys

    if isinstance(obj, (list, tuple)): # List / tuple case
        if not obj:
            return default

        cache = [(key_fn(x), i) for i, x in enumerate(obj)]
        cache.sort(reverse=reverse)
        cache = cache[:topk]

        if topk == 1:
            val, idx = cache[0]
            return {"index": idx, "value": obj[idx], "item": obj[idx], "pair": (idx, obj[idx]), "selected": val}.get(return_type, idx)

        idxs = [idx for _, idx in cache]
        if return_type == "index":
            return idxs
        if return_type == "value":
            return [obj[i] for i in idxs]
        if return_type == "item":
            return [obj[i] for i in idxs]
        if return_type == "pair":
            return [(i, obj[i]) for i in idxs]
        if return_type == "selected":
            return [val for val, idx in cache]
        return idxs

    raise TypeError("argext expects dict, list, tuple, or scalar")


@itereval
def to_distribution(
    values: Iterable[Union[int, float]],
    mode: Literal["normalize", "softmax"] = "normalize",
    power2raise: Optional[Union[int, float, Literal["EULER", "default"]]] = "default",
) -> List[float]:
    """
    Convert an iterable of numbers into a probability-like distribution using
    either simple normalization or softmax.

    Parameters
    ----------
    values : iterable of float
        Input numbers to transform.
    mode : {"normalize", "softmax"}, default "normalize"
        - "normalize": divide each value by the sum of all values.
        - "softmax": apply base**(x - max(x)) for numerical stability, then normalize.
    power2raise : int | float | {"EULER", "default"}, optional
        Base used for exponentiation in softmax mode.
        - "default" or "EULER": uses 2.718281828459045 (Euler's number)
        - numeric value: uses that number as the exponential base

    Returns
    -------
    list of float
        A list of transformed values that sum to 1.
    """ 
    vals = list(values)
    if not vals: return []
    if not all(isinstance(v, (int, float)) for v in vals):
        raise TypeError("All values must be int or float")

    ret_type = type(values)
    
    if mode == "normalize":
        s = sum(vals)
        norm = [v / s for v in vals]
    elif mode == "softmax":
        base = 2.718281828459045 if power2raise in ("EULER", "default", None) else float(power2raise)
        m = max(vals)
        exps = [pow(base, v - m) for v in vals]
        s = sum(exps)
        norm = [e / s for e in exps]
    else:
        raise ValueError(f"Unknown mode: {mode}")

    return ret_type(norm)

def iterexec(
    func: Callable | None = None,
    *,
    tuple_is_autonomic: bool = False,
    iterables_are_atomic: bool = False,
) -> Callable:
    """Lift a scalar function over dicts, iterables, and ndarrays.
    tuple_is_autonomic=True treats tuples as atomic; iterables_are_atomic=True treats all iterables as atomic."""

    def is_iterable(x: Any) -> bool:
        return (
            isinstance(x, Iterable)
            and not isinstance(x, (str, bytes, dict))
            and not callable(x)
            and not (tuple_is_autonomic and isinstance(x, tuple))
        )

    def decorate(f: Callable) -> Callable:

        @wraps(f)
        def wrapper(
            src: Any,
            *args: Any,
            elem_transforms: Any = None,
            iter_transforms: Any = None,
            **kwargs: Any,
        ) -> Any:

            def apply(y: Any) -> Any:
                out = _elem_transforms(y, pipeline=elem_transforms) if elem_transforms else y
                return _iter_transforms(out, pipeline=iter_transforms) if iter_transforms else out

            if elem_transforms is None and iter_transforms is None and not isinstance(src, (dict, np.ndarray)) and not is_iterable(src):
                return f(src, *args, **kwargs)

            if isinstance(src, dict):
                out = {k: wrapper(v, *args, elem_transforms=elem_transforms, **kwargs) for k, v in src.items()}
                return _iter_transforms(out, pipeline=iter_transforms) if iter_transforms else out

            if not iterables_are_atomic and is_iterable(src):
                out = [wrapper(v, *args, elem_transforms=elem_transforms, **kwargs) for v in src]
                return _iter_transforms(out, pipeline=iter_transforms) if iter_transforms else out

            if isinstance(src, np.ndarray):
                try:
                    return apply(f(src, *args, **kwargs))
                except (TypeError, ValueError):
                    return _iter_transforms(
                        np.vectorize(lambda x: _elem_transforms(f(x, *args, **kwargs), pipeline=elem_transforms))(src),
                        pipeline=iter_transforms,
                    ) if iter_transforms else np.vectorize(
                        lambda x: _elem_transforms(f(x, *args, **kwargs), pipeline=elem_transforms)
                    )(src)

            y = f(src, *args, **kwargs)
            if isinstance(y, dict):
                out = {
                    k: ([_elem_transforms(e, pipeline=elem_transforms) for e in v]
                        if isinstance(v, (np.ndarray,)) or is_iterable(v)
                        else _elem_transforms(v, pipeline=elem_transforms))
                    for k, v in y.items()
                }
                return _iter_transforms(out, pipeline=iter_transforms) if iter_transforms else out

            return apply(y)

        return wrapper

    return decorate(func) if func else decorate

def iterexec_working(
    func: Callable | None = None,
    *,
    tuple_is_autonomic: bool = False,
    iterables_are_atomic: bool = False
) -> Callable:
    """
    Lift a scalar function over dicts, iterables, and ndarrays, with optional
    element- and whole-iter transforms. Scalars with no transforms use a fast path.

    tuple_is_autonomic=True   → tuples treated as atomic (not lifted)
    iterables_are_atomic=True → all iterables treated as atomic (not lifted)
    """

    def decorate(f: Callable) -> Callable:

        def is_iterable(x: Any) -> bool:
            return (
                isinstance(x, Iterable)
                and not isinstance(x, (str, bytes, dict))
                and not callable(x)
                and not (tuple_is_autonomic and isinstance(x, tuple))
            )

        def process_returned_dict(
            y: Dict[Any, Any],
            elem_transforms: Any
        ) -> Dict[Any, Any]:
            out = {}
            for k, v in y.items():
                if isinstance(v, dict):
                    out[k] = process_returned_dict(v, elem_transforms)
                elif isinstance(v, np.ndarray) or is_iterable(v):
                    out[k] = [
                        _elem_transforms(e, pipeline=elem_transforms)
                        for e in v
                    ]
                else:
                    out[k] = _elem_transforms(v, pipeline=elem_transforms)
            return out

        @wraps(f)
        def wrapper(
            src: Any,
            *args: Any,
            elem_transforms: Any = None,
            iter_transforms: Any = None,
            **kwargs: Any
        ) -> Any:

            # --- FAST PATH: scalar + no transforms ---
            if (
                elem_transforms is None
                and iter_transforms is None
                and not isinstance(src, (dict, np.ndarray))
                and not is_iterable(src)
            ):
                return f(src, *args, **kwargs)

            # --- DICT FIRST ---
            if isinstance(src, dict):
                out = {
                    k: wrapper(
                        v, *args,
                        elem_transforms=elem_transforms,
                        iter_transforms=None,
                        **kwargs
                    )
                    for k, v in src.items()
                }
                return _iter_transforms(out, pipeline=iter_transforms)

            # --- ITERABLE NEXT (only if not atomic) ---
            if not iterables_are_atomic and is_iterable(src):
                out = [
                    wrapper(
                        v, *args,
                        elem_transforms=elem_transforms,
                        iter_transforms=None,
                        **kwargs
                    )
                    for v in src
                ]
                return _iter_transforms(out, pipeline=iter_transforms)

            # --- NDARRAY NEXT ---
            if isinstance(src, np.ndarray):
                try:
                    y = f(src, *args, **kwargs)
                    y = _elem_transforms(y, pipeline=elem_transforms)
                except Exception:
                    y = np.vectorize(
                        lambda x: _elem_transforms(f(x, *args, **kwargs),
                                                   pipeline=elem_transforms)
                    )(src)
                return _iter_transforms(y, pipeline=iter_transforms)

            # --- SCALAR FALLBACK ---
            y = f(src, *args, **kwargs)

            if isinstance(y, dict):
                out = process_returned_dict(y, elem_transforms)
                return _iter_transforms(out, pipeline=iter_transforms)

            y = _elem_transforms(y, pipeline=elem_transforms)
            return _iter_transforms(y, pipeline=iter_transforms)

        return wrapper

    return decorate(func) if func else decorate
    
@itereval
def dsl(src, **kwargs):
    return src

def simulate_scenarios(scenarios: Dict):
    (key, val), = scenarios.items()
    if isinstance(val, ABCIterable) and not isinstance(val, (str, bytes)):
        values = list(val)
    else:
        values = [val]

    def decorator(func):
        def wrapper(*args, **kwargs):
            results = []  # ✅ renamed from scenarios
            for v in values:
                call_kwargs = {**kwargs, key: v}
                raw = func(*args, **call_kwargs)
                if isinstance(raw, list) and all(isinstance(r, dict) for r in raw):
                    for r in raw:
                        results.append({
                            "params": {**r["params"], key: v},
                            "result": r["result"]  # ✅ fixed brace
                        })
                else:
                    results.append({
                        "params": {key: v},
                        "result": raw
                    })
            return results
        return wrapper
    return decorator


def simulate(func: Callable, *args, scenarios: Dict = None, **kwargs):
    if scenarios is None:
        return func(*args, **kwargs)

    func_name = func.__name__
    print(f"\nExecuting: {func_name}")
    if args:      print(f"  Fixed args:    {args}")
    if kwargs:    print(f"  Fixed kwargs:  {kwargs}")
    if scenarios: print(f"  with Scenarios: {scenarios}")
    print()

    wrapped = func
    for k, v in scenarios.items():
        wrapped = simulate_scenarios({k: v})(wrapped)
    try:
        return wrapped(*args, **kwargs)
    except TypeError as e:
        if "multiple values for argument" in str(e):
            conflict = str(e).split("'")[1]
            raise TypeError(
                f"Conflict in '{func_name}': '{conflict}' was passed as both a "
                f"fixed kwarg and a scenario key. Remove it from one or the other."
            ) from None
        raise


def splitlist(inp: Union[tuple, list, ABCIterable, dict], target: int = None, threshold: int = None) -> list:
    """Splits an iterable into equal chunks. Use threshold to cap chunk size,
    target to set number of chunks. Returns input unchanged if neither is provided."""

    items = list(inp.items()) if isinstance(inp, dict) else list(inp)
    n = len(items)

    if n == 0 or (target is None and threshold is None):
        return inp

    chunk_size = threshold if threshold is not None else n // target
    return ngrams(items, chunk_size, step='compute')


def ngrams(inp: Union[str, tuple, list, ABCIterable], n: int, split: str = 'auto', step: Union[int, str] = 'default', keep_tail: bool = True) -> list:
    """Generates n-grams from a string or iterable. Split: 'auto'|'words'|'chars'.
    Step: 'default'/'nlp'=1, 'rag'=n//2, 'compute'=n, or any int.
    keep_tail=True appends true orphan for compute, back-padded tail for rag/nlp."""

    step_map = {'default': 1, 'nlp': 1, 'rag': max(1, n // 2), 'compute': n}
    step = step_map.get(step, step) if isinstance(step, str) else step

    def _ngram(tokens: list, join: bool = False) -> list:
        result = [tokens[i:i + n] for i in range(0, len(tokens) - n + 1, step)]
        if keep_tail:
            if step >= n:
                orphan = tokens[len(result) * step:]
                if orphan:
                    result.append(orphan)
            else:
                tail = tokens[len(tokens) - n:]
                if tail != (result[-1] if result else []):
                    result.append(tail)
        return [" ".join(w) for w in result] if join else result

    if not isinstance(inp, str):
        items = list(inp.items()) if isinstance(inp, dict) else list(inp)
        return _ngram(items)

    mode = split if split != 'auto' else ('words' if ' ' in inp else 'chars')
    tokens = inp.split() if mode == 'words' else list(inp)
    return _ngram(tokens, join=(mode == 'words'))

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

