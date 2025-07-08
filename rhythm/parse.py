import re
from .dtree import DTree
from .tree import Tree
from .step import StepRhythm
from .euclidean import EuclideanRhythm

__all__ = [
    'from_string'
]

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

    tree = Tree.from_string(s)
    if tree is not None:
        return DTree.from_tree(tree)
    return parse_dtree(s)
    
def tokenize(tree_str):
    token_pattern = re.compile(r"\d+|[A-Za-z]+|\(|\)")
    tokens = token_pattern.findall(tree_str)
    return tokens

def parse_dtree(tree_str):
    tokens = tokenize(tree_str)
    i = 0

    def parse_node():
        nonlocal i
        if i < len(tokens) and re.fullmatch(r"[A-Za-z]+", tokens[i]):
            label = tokens[i]
            i += 1
            return DTree(weight=1, label=label, children=[])
        if i >= len(tokens) or not tokens[i].isdigit():
            raise ValueError(f"Expected weight at token {i}, got {tokens[i] if i < len(tokens) else None}")
        weight = int(tokens[i])
        i += 1
        label = None
        if i < len(tokens) and re.fullmatch(r"[A-Za-z]+", tokens[i]):
            label = tokens[i]
            i += 1
        children: List[DTree] = []
        if i < len(tokens) and tokens[i] == '(':
            i += 1
            while i < len(tokens) and tokens[i] != ')':
                node = parse_node()
                children.append(node)
            if i >= len(tokens) or tokens[i] != ')':
                raise ValueError(f"Expected ')' at token {i}, got {tokens[i] if i < len(tokens) else None}")
            i += 1
        return DTree(weight, label, children)

    root = parse_node()
    if i != len(tokens):
        raise ValueError(f"Unexpected extra tokens from index {i}: {tokens[i:]}")
    return root
