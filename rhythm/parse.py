import re
from .dtree import DTree
from .tree import Tree
from .step import StepRhythm
from .euclidean import EuclideanRhythm
from .quantize import Nonterminal

__all__ = [
    'grammar_from_string',
    'from_string'
]

_BLANK_RE = re.compile(r'^(#.*)?$')
_RULE_RE = re.compile(
    r'^(([A-Za-z_][A-Za-z0-9_]*):)?\s*'
    r'([A-Za-z_][A-Za-z0-9_]*)\s*->\s*'
    r'(\d+(\.\d+)?)\s+'
    r'([^#]+)(\s*#.*)?$'
)

def grammar_from_string(s):
    rules = []
    nts   = {}
    for line in s.splitlines():
        line = line.strip()
        if _BLANK_RE.match(line):
            continue
        if m := _RULE_RE.match(line):
            rule_id = m.group(2)
            name = m.group(3)
            weight = float(m.group(4))
            rule = from_string(m.group(6))
            if name in nts:
                nt = nts[name]
            else:
                nt = nts[name] = Nonterminal(name)
            rules.append((nt, weight, rule, rule_id))
        else:
            raise ValueError(f"Cannot parse {repr(line)} as grammar rule")
    rw = lambda x: DTree(x.weight, nts[x.label], []) if x.label in nts else None
    for nt, weight, rule, rule_id in rules:
        rule.rule_id = rule_id
        nt.prod.append((weight, rule.rewrite(rw)))
    return rules[0][0]

_EUC_RE = re.compile(
    r'^\s*E'
    r'\(\s*'
      r'(-?\d+)\s*,\s*'          # pulses
      r'(-?\d+)\s*,\s*'          # steps
      r'(-?\d+)\s*'              # rotation (can be negative)
    r'\)\s*$'
)

_RAW_RE = re.compile(r'^\s*([01]+)\s*$')

def from_string(s):
    m = _EUC_RE.match(s)
    if m:
        pulses = int(m.group(1))
        steps  = int(m.group(2))
        rot    = int(m.group(3))
        return EuclideanRhythm(pulses, steps, rot)

    m = _RAW_RE.match(s)
    if m:
        bits = [int(ch) for ch in m.group(1)]
        return StepRhyhm(bits)

    if s in ["s", "n"]:
        return parse_dtree(s)
    tree = Tree.from_string(s)
    if tree is not None:
        return DTree.from_tree(tree)
    return parse_dtree(s)
    
def tokenize(tree_str):
    token_pattern = re.compile(r"\d+|[A-Za-z]+\d*|\(|\)| +")
    tokens = token_pattern.findall(tree_str)
    return tokens

def parse_dtree(tree_str):
    tokens = tokenize(tree_str)
    i = 0

    def parse_node():
        nonlocal i
        j = i
        if i < len(tokens) and tokens[i].isdigit():
            weight = int(tokens[i])
            i += 1
        else:
            weight = 1
        label = None
        if i < len(tokens) and re.fullmatch(r"[A-Za-z]+\d*", tokens[i]):
            label = tokens[i]
            i += 1
        children: List[DTree] = []
        if i < len(tokens) and tokens[i] == '(':
            i += 1
            skip_space()
            while i < len(tokens) and tokens[i] != ')':
                node = parse_node()
                children.append(node)
                skip_space()
            if i >= len(tokens) or tokens[i] != ')':
                raise ValueError(f"Expected ')' at token {i}, got {tokens[i] if i < len(tokens) else None}")
            i += 1
        if i == j:
            raise ValueError(f"Expected DTree at token {i}, got {tokens[i] if i < len(tokens) else None}")
        return DTree(weight, label, children)

    def skip_space():
        nonlocal i
        if i < len(tokens) and tokens[i] == " ":
            i += 1

    skip_space()
    root = parse_node()
    skip_space()
    if i != len(tokens):
        raise ValueError(f"Unexpected extra tokens from index {i}: {tokens[i:]}")
    return root
