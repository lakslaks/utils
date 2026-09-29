#stringutils.py
import re, html, json, ast
from functools import reduce
from urllib.parse import urlparse
import pyperclip
from typing import Literal, Callable, Iterable, TypeVar, Union, Optional, Any, Tuple, Dict, List

def sanitize_text (text: str):
    text = html.unescape(text)
    text = text.replace('\xa0', ' ')
    text = re.sub (r'\u200b|\u200a|\u200c\ufeff|\&nbsp;', ' ', text)
    text = re.sub(r'[\t\r\n]+', ' ', text)
    text = text.replace('—', ' - ')
    text = re.sub(r'[“”]', '"', text)
    text = re.sub(r"[‘’]", "'", text)
    text = re.sub(r'\s{2,}', ' ', text)
    return text.strip()

def html2text(content:str):
    text = content['body'] if isinstance(content, dict) and 'body' in content else content
    if not text: return ''
    text = re.sub(r'<!--.*?-->', r'', text, flags=re.DOTALL)
    text = re.sub(r'<(script|style)[^>]*>.*?</\1>', r'', text, flags=re.DOTALL|re.IGNORECASE)
    text = re.sub(r'<\s*(br|p)\s*/?>', r'\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', r'', text)
    text = re.sub(r'\s+', r' ', text).strip()
    return sanitize_text(text)
    
def strip_hyperlink (string:str, replace:str = None):
    pat = r'\bhttps?://[^\s]+'
    replace = replace or r''
    return re.sub(pat, replace, string)

def clean_text (text:str, include_hyperlinks:bool = False):
    if not text: return ''
    text = sanitize_text (text)
    if not include_hyperlinks:
        text = strip_hyperlink (text)
    return text	

def sanitize_content(
    text: str,
    strip_html: bool = True,
    strip_hyperlinks: bool = True,
    dict_key: str = None,
) -> str:
    """Normalize and clean text or HTML content."""

    if not text:
        return ''
    
    if strip_html:
        text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
        text = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<\s*(br|p)\s*/?>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'<[^>]+>', '', text)

    text = html.unescape(text)
    text = re.sub(r'[\xa0\u200b\u200a\u200c\ufeff]|&nbsp;', ' ', text)
    text = re.sub(r'[""]', '"', text)
    text = re.sub(r"[\'']", "'", text)
    text = text.replace('—', ' - ')
    text = re.sub(r'[\t\r\n]+', ' ', text)

    if strip_hyperlinks:
        text = re.sub(r'\bhttps?://\S+', '', text)

    return re.sub(r'\s{2,}', ' ', text).strip()

def extract_raw_email_address (address:str) -> str:
    if address.strip() != '' and "@" in address:
        match = re.search(r'<([^>]+)>', address)
        if match:
            address = match.group(1)
    return address

def extract_domain(address: str) -> str | None:
    try:
        # Extract email inside angle brackets if present
        if "<" in address and ">" in address:
            address = extract_raw_email_address(address)

        # If it's a URL, parse it
        if address.startswith(("http://", "https://", "mailto:")):
            parsed = urlparse(address)
            host = parsed.netloc or parsed.path   # mailto:user@domain
            domain = host.split("@")[-1]
        else:
            # Otherwise treat as email-like
            domain = address.split("@")[-1]

        # Extract final domain segment
        match = re.search(
            r'([^.@]+\.(?:[a-zA-Z]{2,}|[a-zA-Z]+\.[a-zA-Z]{2}))$',
            domain,
            re.IGNORECASE
        )
        return match.group(1) if match else None

    except Exception:
        return None    

def nested_get(data:Dict, path:str, sep="."):
    path = path.split(sep) if isinstance(path, (str, int)) else path
    def access(current, key):
        try:
            # Convert numeric keys to int for list indexing
            key = int(key) if isinstance(current, list) and str(key).isdigit() else key
            return current[key]
        except (KeyError, IndexError, TypeError, ValueError):
            return None
    try:
        return reduce(lambda acc, k: access(acc, k), path, data)
    except Exception:
        return None

def nget(data:Dict, path:str, sep="."):
    return nested_get (data, path, sep)
    
def jsonify (content:str):
    try:
        return json.loads (content), True
    except Exception as e:
        return content, False

def copy2clip(var: Any):
    _ = pyperclip.copy (var)
    return

def paste(var: Any):
    try:
        raw_text = pyperclip.paste()
        return ast.literal_eval(raw_text)
    except (ValueError, SyntaxError):
        return raw_text

def scour(pats: Union[str, List, Dict], content: Union[str, int], flags: bool = None):

    if flags is None:
        flags = re.DOTALL | re.M

    if isinstance(content, int): 
        content = str(content) 
    elif not isinstance(content, str):
        raise TypeError ("content must be str or int")

    if isinstance(pats, str):
        result = [re.findall(pats, content, flags)]
    elif isinstance(pats, (list, tuple)):
        result = [re.findall(pattern, content, flags) for pattern in pats]
    elif isinstance(pats, dict):
        result = {label: re.findall(pattern, content, flags)
                  for label, pattern in pats.items()}
    else:       
        raise TypeError ("patterns must be str, list, tuple, or dict")

    return result[0] if isinstance(result, list) and len(result) == 1 else result


def scrub(pats: Dict, content: str, flags: bool = None):
    
    if flags is None:
        flags = re.DOTALL | re.M

    if not isinstance(pats, dict):
        raise TypeError("Replace mode requires dict {pattern: repl}")
        
    if isinstance(content, int): 
        content = str(content) 
    elif not isinstance(content, str):
        raise TypeError ("content must be str or int")
        
    res = content
    for pattern, repl in pats.items():
        res = re.sub(pattern, repl, res, flags=flags)
    return res
