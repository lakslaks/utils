from IPython.display import display, HTML
import inspect, html
import pyperclip

def get_api_docs(obj, methods=True, classes=False, private=False, dunder=False, include_signature=False):
    rows = []

    # Case 1: obj itself is a function
    if inspect.isfunction(obj) or inspect.ismethod(obj):
        sig = get_method_sig(obj, to_clipboard=False) if include_signature else ""
        rows.append({
            "type": "function",
            "name": obj.__name__,
            "doc": inspect.getdoc(obj) or "None",
            "sig": sig
        })
        return rows

    # Case 2: class or module
    for name, member in inspect.getmembers(obj):

        # visibility filtering
        if name.startswith("__") and name.endswith("__"):
            if not dunder:
                continue
        elif name.startswith("_"):
            if not private:
                continue

        # functions / methods
        if methods and (inspect.isfunction(member) or inspect.ismethod(member)):
            sig = get_method_sig(member, to_clipboard=False) if include_signature else ""
            rows.append({
                "type": "function",
                "name": name,
                "doc": inspect.getdoc(member) or "None",
                "sig": sig
            })
            continue

        # classes
        if classes and inspect.isclass(member):
            rows.append({
                "type": "class",
                "name": name,
                "doc": inspect.getdoc(member) or "None",
                "sig": ""  # optional: could include __init__ signature
            })
            continue

    return rows

def render_api_docs(rows):
    html_rows = []

    for r in rows:
        sig_html = f"{html.escape(r['sig'])}" if r["sig"] else ""
        html_rows.append(
            f"<tr style='text-align:left; vertical-align:top;'>"
            f"<td style='width:10%; text-align:left; vertical-align:top;'>{html.escape(r['type'])}</td>"
            f"<td style='width:10%; text-align:left; vertical-align:top;'>{html.escape(r['name'])}</td>"
            f"<td style='width:80%; text-align:left; vertical-align:top;'>{sig_html}<br>>>{html.escape(r['doc'])}</td>"
            f"</tr>"
        )

    table = (
        "<table style='width:80%; margin:auto; border-collapse:collapse;' border='1'>"
        "<thead>"
        "<tr>"
        "<th style='text-align:center; width:10%;'>Type</th>"
        "<th style='text-align:center; width:10%;'>Name</th>"
        "<th style='text-align:center; width:80%;'>Docstring</th>"
        "</tr>"
        "</thead>"
        "<tbody>"
        + "".join(html_rows) +
        "</tbody></table>"
    )

    return table

def get_docs(obj, methods=True, classes=False, private=False, dunder=False, include_signature=False):
    rows = get_api_docs(
        obj,
        methods=methods,
        classes=classes,
        private=private,
        dunder=dunder,
        include_signature=include_signature
    )
    return render_api_docs(rows)

def get_methods(obj, methods=True, classes=False, private=False, dunder=False):
    results = []
    for name, member in inspect.getmembers(obj):
        if name.startswith("__") and name.endswith("__"):
            if not dunder:
                continue
        elif name.startswith("_"):
            if not private:
                continue

        if methods and (inspect.isfunction(member) or inspect.ismethod(member)):
            results.append(("method", name))
            continue
        if classes and inspect.isclass(member):
            results.append(("class", name))
            continue
            
    if not all ([classes, private, dunder]):
        results = [i[1] for i in results]
        
    return results

def get_method_sig(func, to_clipboard=True, include_defaults=True):
    sig = inspect.signature(func)
    params = []
    for name, p in sig.parameters.items():
        # Remove type hints
        if include_defaults and p.default is not inspect._empty:
            params.append(f"{name}={p.default!r}")
        else:
            params.append(name)
    if to_clipboard: pyperclip.copy (f"{func.__name__} ({', '.join(params)})")
    return f"{func.__name__} ({', '.join(params)})"
