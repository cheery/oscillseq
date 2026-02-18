# https://github.com/patrick-kidger/wadler_lindig/blob/main/wadler_lindig/_wadler_lindig.py
# Lindig, C. 2000. Strictly Pretty.
# https://lindig.github.io/papers/strictly-pretty-2000.pdf

from dataclasses import dataclass

__all__ = ["pformat_doc", "text", "sp", "nl", "pretty"]

def pretty(x):
    if isinstance(x, (int, float, str)):
        return text(str(x))
    if not hasattr(x, "__pretty__"):
        raise Exception(f"{x!r} has not .__pretty__()")
    return x.__pretty__()

class AbstractDoc:
    def __add__(self, other):
        return ConcatDoc((self, other))

    def nest(self, indent):
        return NestDoc(self, indent)

    def group(self):
        return GroupDoc(self)

    def join(self, seq):
        group = ()
        for s in seq:
            if len(group) > 0:
                group += (self,pretty(s).group())
            else:
                group += (pretty(s).group(),)
        return ConcatDoc(group)

    def __pretty__(self):
        return self

@dataclass(frozen=True)
class TextDoc(AbstractDoc):
    text: str
    def __post_init__(self):
        if "\n" in self.text:
            raise ValueError("Cannot have newlines in TextDocs.")

def text(txt):
    return TextDoc(txt)

@dataclass(frozen=True)
class LineDoc(AbstractDoc):
    pass

@dataclass(frozen=True)
class BreakDoc(AbstractDoc):
    text: str
    def __post_init__(self):
        if "\n" in self.text:
            raise ValueError("Cannot have newlines in BreakDocs.")

sp = BreakDoc(" ")
nl = LineDoc()

@dataclass(frozen=True)
class ConcatDoc(AbstractDoc):
    children: tuple[AbstractDoc, ...]

    def __add__(self, other: AbstractDoc):
        return ConcatDoc(self.children + (other,))

@dataclass(frozen=True)
class NestDoc(AbstractDoc):
    child: AbstractDoc
    indent: int

@dataclass(frozen=True)
class GroupDoc(AbstractDoc):
    child: AbstractDoc

def fits(doc, width, indent):
    todo = [doc]
    while len(todo) > 0 and width >= 0:
        match todo.pop():
            case int(indent_past):
                indent = indent_past
            case TextDoc(text):
                width -= len(text)
            case BreakDoc(text):
                width -= len(text)
            case LineDoc():
                width = indent
            case ConcatDoc(children):
                todo.extend(reversed(children))
            case NestDoc(child, extra_indent):
                todo.append(indent)
                todo.append(child)
                indent += extra_indent
            case GroupDoc(child):
                todo.append(child)
    return width >= 0

def pformat_doc(doc, width) -> str:
    outs = []
    width_so_far = 0
    vertical = False # TODO: This didn't work out so well.. we need a better layouter.
    indent = 0
    todo = [GroupDoc(doc)]
    while len(todo) > 0:
        match todo.pop():
            case bool(vertical2):
                vertical = vertical2
            case int(indent2):
                indent = indent2
            case TextDoc(text):
                outs.append(text)
                width_so_far += len(text)
            case BreakDoc(text):
                if vertical:
                    outs.append("\n" + " " * indent)
                    width_so_far = indent
                else:
                    outs.append(text)
                    width_so_far += len(text)
            case LineDoc():
                 outs.append("\n" + " " * indent)
                 width_so_far = indent
            case ConcatDoc(children):
                todo.extend(reversed(children))
            case NestDoc(child, extra_indent):
                todo.append(indent)
                todo.append(child)
                indent += extra_indent
            case GroupDoc(child):
                if vertical and fits(child, width - width_so_far, indent):
                    todo.append(True)
                    todo.append(child)
                    vertical = False
                else:
                    todo.append(child)
    return "".join(outs)
