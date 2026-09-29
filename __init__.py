"""
Public API for the iterutils package.

This namespace re‑exports the primary utility functions:
- to_list          : Normalize strings, lists, and tuples into list form.
- flatten          : Expand mixed iterables and scalars into a single sequence.
- get_argmax       : Retrieve the maximum element or its associated index/key.
- get_argmin       : Retrieve the minimum element or its associated index/key.
- sanitize_return  : Decorator for consistent post‑processing (sorting,
                     transforms, type coercion).
- transform        : Apply one or more functions to values or iterables.
- to_distribution  : Convert iterable into probability-like distribution using
                     simple normalization or softmax

Importing from the package root provides a stable, convenient interface.
"""

from .iterutils import (
    _elem_transforms, _iter_transforms, 
    to_list, to_range, flatten, to_distribution,
    get_argmax, get_argmin, 
    iterexec, itereval, dsl)
from .hierarchy_explorer import (HierarchyExplorer, ConfigExplorer, TreeExplorer, DictExplorer)
from .gibberish_detector import GibberishDetector

__all__ = [
    #from iterutils
    '_elem_transforms', '_iter_transforms',
    'to_list', 'to_range', 'flatten', 'to_distribution',
    'get_argmax', 'get_argmin',  
    'iterexec', 'itereval', 'dsl',
    
    #from hirearchy_explorer
    'HierarchyExplorer', 'ConfigExplorer', 'TreeExplorer', 'DictExplorer',

    'GibberishDetector',
]


