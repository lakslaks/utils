import re, rstr
from ruamel.yaml import YAML
from copy import deepcopy

class Scrubber:
    def __init__(self, rules=None, yaml_path=None, aliases=None, templates=None, flags=None, default_mask = "MASKED"):
        self.rules = rules or []
        self.aliases = aliases or {}
        self.templates = templates or {}
        self.default_mask = default_mask or ""
        if yaml_path:
            yaml = YAML(typ="safe")
            with open(yaml_path, "r", encoding="utf-8") as f:
                config = yaml.load(f)
    
            self.aliases = config.get("aliases", {})
            rules = config.get("rules", [])
            self.templates = config.get("templates", {})
    
        self.flags = flags if flags is not None else (re.DOTALL | re.M)
        self.rules = self._validate_and_prepare_rules(rules)

    # ---------------------------------------------------------
    # VALIDATION + REGEX COMPILATION
    # ---------------------------------------------------------
    def _validate_and_prepare_rules(self, rules):
        if not rules:
            return
        seen = set()
        prepared = []
    
        for rule in rules:
            name = rule.get("name")
            pattern = rule.get("pattern")
    
            if not name or not pattern:
                raise ValueError(f"Rule missing required fields: {rule}")
    
            if name in seen:
                raise ValueError(f"Duplicate rule name: {name}")
            seen.add(name)
    
            # --- ALIAS EXPANSION ---
            for alias_name, alias_list in self.aliases.items():
                token = f"{{{{{alias_name}}}}}"
                if token in pattern:
                    union = "(?:" + "|".join(alias_list) + ")"  # remove re.escape here
                    pattern = pattern.replace(token, union)
    
            # --- COMPILE PATTERN ---
            try:
                compiled = re.compile(pattern, self.flags)
            except re.error as e:
                raise ValueError(f"Regex compile error in rule '{name}': {e}")
    
            # --- VALIDATE REPLACEMENT ---
            repl = rule.get("repl", self.default_mask)
            if repl != "" and not (repl.startswith ("<") or repl.endswith (">")):
                repl = f"<{repl}>"
            try:
                compiled.sub(repl, "")
            except re.error as e:
                raise ValueError(f"Replacement error in rule '{name}': {e}")
    
            prepared.append({
                "name": name,
                "pattern": pattern,
                "compiled": compiled,
                "repl": repl,
                "priority": rule.get("priority", 999),
                "notes" : rule.get ("notes"),
                "tags": rule.get("tags", [])
            })

        self.rule_index = {r["name"]: r for r in prepared}
    
        return sorted(prepared, key=lambda r: r["priority"])
        
    # ---------------------------------------------------------
    # SCAN: return matches grouped by rule name
    # ---------------------------------------------------------
    def scan(self, text, include=None, exclude=None, tags=None, sequence=None):
        ordered = self._resolve_sequence(sequence)
        results = {}

        for rule in ordered:
            name = rule["name"]

            if include and name not in include:
                continue
            if exclude and name in exclude:
                continue
            if tags and not (set(tags) & set(rule["tags"])):
                continue

            found = rule["compiled"].findall(text)
            if not found:
                continue

            cleaned = []
            for f in found:
                cleaned.append(" ".join(f) if isinstance(f, tuple) else f)

            results[name] = cleaned

        return results

    # ---------------------------------------------------------
    # MATCH: fetch matches for a single rule
    # ---------------------------------------------------------
    def match(self, name, text):
        for rule in self.rules:
            if rule["name"] == name:
                found = rule["compiled"].findall(text)
                cleaned = []
                for f in found:
                    cleaned.append(" ".join(f) if isinstance(f, tuple) else f)
                return cleaned
        return []

    def _apply_edges(self, pattern, edges):
        if not edges:
            return pattern
    
        # Detect existing boundaries
        has_left = pattern.startswith(r"\b")
        has_right = pattern.endswith(r"\b")
        if edges in (True, 'strict', 'yes'): edges = 'both'
    
        # Apply left boundary
        if edges in ("left", "start", "both") and not has_left:
            pattern = r"\b" + pattern
    
        # Apply right boundary
        if edges in ("right", "end", "both") and not has_right:
            pattern = pattern + r"\b"
    
        return pattern
        
    # ---------------------------------------------------------
    # APPLY: run replacements
    # ---------------------------------------------------------
    def apply_dnu(self, text, include=None, exclude=None, tags=None, sequence=None):
        res = text
        ordered = self._resolve_sequence(sequence)

        for rule in ordered:
            name = rule["name"]

            if include and name not in include:
                continue
            if exclude and name in exclude:
                continue
            if tags and not (set(tags) & set(rule["tags"])):
                continue

            res = rule["compiled"].sub(rule["repl"], res)

        return res

    def apply(self, text, include=None, exclude=None, tags=None, sequence=None, enforce_boundary=None):
        res = text
        ordered = self._resolve_sequence(sequence)
    
        for rule in ordered:
            name = rule["name"]
    
            # --- FILTERING ---
            if include and name not in include:
                continue
            if exclude and name in exclude:
                continue
            if tags and not (set(tags) & set(rule["tags"])):
                continue
    
            # --- EDGE HANDLING ---
            pattern = rule["pattern"]
            if enforce_boundary:
                pattern = self._apply_edges(pattern, edges=enforce_boundary)
                compiled = re.compile(pattern, self.flags)
            else:
                compiled = rule["compiled"]
    
            # --- APPLY RULE ---
            res = compiled.sub(rule["repl"], res)
        return res
    
    # ---------------------------------------------------------
    # DIFF: show before/after + rule-by-rule matches
    # ---------------------------------------------------------
    def diff(self, text, include=None, exclude=None, tags=None, sequence=None, enforce_boundary=None):
        before = text
        after = self.apply(text, include, exclude, tags, sequence, enforce_boundary)

        ordered = self._resolve_sequence(sequence)
        changes = []

        for rule in ordered:
            name = rule["name"]

            if include and name not in include:
                continue
            if exclude and name in exclude:
                continue
            if tags and not (set(tags) & set(rule["tags"])):
                continue

            matches = self.match(name, before)
            if matches:
                changes.append({"rule": name, "matches": matches})

        return {"before": before, "after": after, "changes": changes}

    # ---------------------------------------------------------
    # INTERNAL: resolve template or priority order
    # ---------------------------------------------------------
    def _resolve_sequence(self, sequence):
        # Case 1: sequence is a template name (string)
        if isinstance(sequence, str):
            if sequence in self.templates:
                names = self.templates[sequence]
                return [r for r in self.rules if r["name"] in names]
    
            # treat as single rule name
            rule_names = {r["name"] for r in self.rules}
            if sequence in rule_names:
                return [r for r in self.rules if r["name"] == sequence]
    
            raise ValueError(f"Unknown template or rule '{sequence}'")
    
        # Case 2: sequence is a list → expand templates inside the list
        if isinstance(sequence, list):
            expanded = []
            rule_names = {r["name"] for r in self.rules}
    
            for item in sequence:
                # template expansion
                if item in self.templates:
                    expanded.extend(self.templates[item])
                    continue
    
                # rule name
                if item in rule_names:
                    expanded.append(item)
                    continue
    
                raise ValueError(f"Unknown template or rule '{item}'")
    
            # return rule objects in the expanded order
            return [r for r in self.rules if r["name"] in expanded]
    
        # Case 3: no sequence → priority order
        return self.rules

    # ---------------------------------------------------------
    # meta data operations
    # ---------------------------------------------------------
    def inspect(self, name):
        if name in ['rules', 'templates', 'aliases']:
            return getattr(self, name)
            
        for r in self.rules: # rule
            if r["name"] == name:
                return {
                    "type": "rule",
                    "definition": {
                        "name": r["name"],
                        "pattern": r["pattern"],
                        "repl": r["repl"],
                        "priority": r["priority"],
                        "notes" : r["notes"],
                        "tags": r["tags"]
                    }
                }
    
        if name in self.templates: # template
            return {"type": "template","definition": self.templates[name]}
    
        if name in self.aliases: # alias
            return {"type": "alias", "definition": self.aliases[name]}
    
        return None

    def inject(self, item):
        """
        item can be:
        - rule dict
        - {"template": name, "sequence": [...]}
        - {"alias": name, "values": [...]}
        """        
        # --- RULE UPSERT ---
        if "name" in item and "pattern" in item:
            name = item["name"]
            # extract existing rules expecting the updated one
            raw_rules = [{"name": r["name"], "pattern": r["pattern"], "repl": r["repl"], "priority": r["priority"], "notes" : r["notes"], "tags": r["tags"]}
                         for r in self.rules if r["name"] != name]
            raw_rules.append(item) # add new rule
            self.rules = self._validate_and_prepare_rules(raw_rules) # Recompile
            return
    
        # --- TEMPLATE UPSERT ---
        if "template" in item:
            self.templates[item["template"]] = item["sequence"]
            return
    
        # --- ALIAS UPSERT ---
        if "alias" in item:
            alias_name, alias_values = item["alias"], item["values"]
            self.aliases[alias_name] = alias_values # upsert alias
            raw_rules = [{"name": r["name"], "pattern": r["pattern"], "repl": r["repl"], "priority": r["priority"], "notes" : r["notes"], "tags": r["tags"]}
                         for r in self.rules]
            self.rules = self._validate_and_prepare_rules(raw_rules) # Recompile
            return
    
        raise ValueError("Unknown inject type")

    def visualize_rule(self, rule, size=5, return_details=False, optionals='retain'):
        if not (res := self.rule_index.get(rule)):
            return "Unknown rule"

        size = max(2, size)
    
        def _apply_optionals(pat: str, mode: str) -> str:
            """Apply optional mode repeatedly until pattern stabilises."""
            _simple = re.compile(r"(\\.|\[[^\]]+\]|[^)(])\?(?!:)")
            _group  = re.compile(r"(\(\?:[^()]*\))\?")   # (?:...)? with no nesting inside
        
            prev = None
            while prev != pat:
                prev = pat
                if mode == 'remove':
                    pat = _simple.sub(r"", pat)
                    pat = _group.sub(r"", pat)
                elif mode == 'force':
                    pat = _simple.sub(r"\1", pat)
                    pat = _group.sub(r"\1", pat)
            return pat
        
        def _make_sampling_safe(pat: str, optionals_mode: str) -> str:
            """Cap unbounded quantifiers and remove xeger-unsafe assertions."""
            # Normalise quadruple-escaped patterns (stored via repr) to double-escaped
            if '\\\\' in pat:
                pat = pat.replace('\\\\', '\\')            
            pat = re.sub(r"\\b", "", pat)
            pat = re.sub(r"\\s[*+]", " ", pat)
        
            if optionals_mode in ('remove', 'force'):
                pat = _apply_optionals(pat, optionals_mode)
        
            pat = re.sub(r"\\d\+", r"\\d{1,6}", pat)
            pat = re.sub(r"\\d\*", r"\\d{0,6}", pat)
            pat = re.sub(r"\\w\+", r"\\w{1,8}", pat)
            pat = re.sub(r"\\w\*", r"\\w{0,8}", pat)
        
            pat = re.sub(r"(\[[^\]]+\])\+", r"\g<1>{1,4}", pat)
            pat = re.sub(r"(\[[^\]]+\])\*", r"\g<1>{0,4}", pat)
        
            # Only cap simple non-capturing groups (no nested parens inside)
            pat = re.sub(r"(\(\?:[^()]+\))\*(?!\{)", r"\g<1>{0,2}", pat)
            pat = re.sub(r"(\(\?:[^()]+\))\+(?!\{)", r"\g<1>{1,2}", pat)
        
            return pat

        _optional_re = re.compile(r"(\\.|\[[^\]]+\]|[^)(])\?(?!:)")
        pat, notes = res['pattern'], res.get('notes', None)
        has_optionals = bool(_optional_re.search(pat))
    
        if optionals == 'both' or (has_optionals and optionals == 'retain'):
            half = size // 2
            forced  = [rstr.xeger(_make_sampling_safe(pat, 'force'))  for _ in range(half)]
            removed = [rstr.xeger(_make_sampling_safe(pat, 'remove')) for _ in range(size - half)]
            samples = forced + removed
        else:
            samples = [rstr.xeger(_make_sampling_safe(pat, optionals)) for _ in range(size)]
    
        return samples if not return_details else {'name': rule, 'notes': notes, 'pattern': pat, 'samples': samples}        
      
if __name__ == '__main__':

    # data sets
    rules = [
        {"name": "payment_alias", "pattern": r"\b{{payment}}\b", "repl": "TOKEN", "priority": 5, "notes": "Expand aliases", "tags": ["alias", "payment"]},
        {"name": "currency", "pattern": r"(₹|\$|A\$|S\$)\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2,3})?)", 
             "repl": r"\1 Amount", "priority": 10, "notes": "Amounts with currency", "tags": ["money"]},
        {"name": "date_numeric","pattern": r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}", "repl": "<DATE>", "priority": 20, "tags": ["date"]},
        {"name": "date_month", "pattern": r"\d{1,2}[/-][A-Za-z]{3}[/-]\d{2,4}", "repl": "<DATE>", "priority": 21, "tags": ["date"]},
        {"name": "valid_ccy", "pattern": r"\b{{CCY}}\b"}
    ]
    aliases = {"payment": ["Payment", "Pymt", "Pay", "Pmt", "Pyment"]}   
    templates = {
        "quick_clean": ["currency", "date_numeric", "date_month"],
        "money_only": ["currency"]
    }
    
    scrubber = Scrubber(rules=rules, aliases=aliases, templates=templates)
    scrubber.templates = templates

    text = "Available as on 01-Mar-26 : ₹ 4,984"

    # simple apply
    result = scrubber.apply(text)
    print (result)

    # apply a templates
    result = scrubber.apply(text, sequence="money_only")
    print(result)
    
    # apply sequence of checks
    result = scrubber.apply(text, sequence=["currency", "date_month"])
    print(result)

    # show pre & post
    result = scrubber.diff(text)
    print (result)

    # apply rules matching tags
    result = scrubber.apply(text, tags=['date'])
    print (result)

    # aliases
    text = "Pymt received on 01-Mar-26 for ₹ 4,984"
    print(scrubber.apply(text, enforce_boundary='both'))

    # peek
    result = scrubber.scan (text)
    print (result)

    # inject & inspect
    scrubber.inject ({'alias':'payment', 'values':['Payment', 'Pymt', 'Pay', 'Pmt', 'Pyment', 'pymts']})
    print (scrubber.inspect ('payment'))

    # visualize rule
    result = scrubber.visualize_rule ('valid_ccy')
    print (result)