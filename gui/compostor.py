from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable, Tuple, Any, Set, Union
from collections import Counter
from .base import Widget, tuplize
import inspect
import contextvars
import functools

builder = contextvars.ContextVar("builder")
kwd_mark = (object(),)

class Composition(Widget):
    def __init__(self, site, key, memo, ancestor):
        super().__init__(site)
        self.key = key
        self.memo = memo
        self.ancestor = ancestor

    def __str__(self):
        return self.debug_str(0)

    def invalidate(self):
        while self is not None:
            self.key = None
            self = self.ancestor

def clear_subwidgets(widget):
    for child in widget:
        if not isinstance(child, Composition):
            clear_subwidgets(child)
    widget.clear()

class Builder:
    def __init__(self, context, composition, memo, counts = None, widget = None, site_prefix=()):
        self.context     = context
        self.composition = composition
        self.memo        = memo
        self.counts      = Counter() if counts is None else counts
        self.widget      = composition if widget is None else widget
        self.site_prefix = site_prefix
        self._token = None

    def make_site(self, frame, fn):
        site  = self.site_prefix + (frame.f_code, frame.f_lineno, fn)
        self.counts[site] += 1
        return site + (self.counts[site],)

    def __enter__(self):
        self._token = builder.set(self)
        return self.widget

    def __exit__(self, exc_type, exc_val, exc_traceback):
        builder.reset(self._token)

class Compostor:
    def __init__(self, fn, context=None):
        self.root = Composition((), (), {}, None)
        self.fn = fn
        self.context = context

    def __call__(self, *args, **kwargs):
        memo = self.root.memo
        clear_subwidgets(self.root)
        self.root = Composition((), (), {}, None)
        with Builder(self.context, self.root, memo):
            self.fn(*args, **kwargs)
        return self.root

    def refresh(self, hook_key):
        self.root.invalidate(hook_key)

def composable(fn):
    @functools.wraps(fn)
    def _composable_(*args, **kwargs):
        bd    = builder.get()
        frame = inspect.currentframe().f_back
        site  = bd.make_site(frame, fn)
        key   = make_key(args, kwargs)
        try:
            widget = bd.memo[site]
            if widget.key != key:
                clear_subwidgets(widget)
                memo = widget.memo
                widget = Composition(site, key, {}, bd.composition)
                with Builder(bd.context, widget, memo):
                    fn(*args, **kwargs)
        except KeyError:
            widget = Composition(site, key, {}, bd.composition)
            with Builder(bd.context, widget, {}):
                fn(*args, **kwargs)
        bd.composition.memo[site] = widget
        bd.widget.append(widget)
    return _composable_

def make_key(args, kwargs):
    key = args
    if kwargs:
        key += kwd_mark
        for item in kwargs.items():
            key += item
    return key

def key(*keys):
    bd = builder.get()
    return Builder(bd.context, bd.composition, bd.memo, bd.counts, bd.widget, bd.site_prefix + keys)

def widget():
    return builder.get().widget

def layout():
    return builder.get().widget

def context():
    return builder.get().context

def component(fn):
    @functools.wraps(fn)
    def _fn_(*args, **kwargs):
        bd = builder.get()
        frame = inspect.currentframe().f_back
        site  = bd.make_site(frame, fn)
        widget = Widget(site)
        bd.widget.append(widget)
        subwidget = fn(widget, *args, **kwargs)
        if subwidget is not None:
            widget = subwidget
        return Builder(bd.context, bd.composition, bd.memo, bd.counts, widget, bd.site_prefix)
    return _fn_

import os
from weakref import WeakValueDictionary

@dataclass(eq=False, frozen=True)
class HookRecord:
    args : Tuple[Any]
    kwargs : Dict[str, Any]

# TODO: reconsider the structure.
#       should this be any different?
class Hook:
    def __init__(self, producer):
        self.links = WeakValueDictionary()
        self.producer = producer

    def __call__(self, *args, **kwargs):
        bd = builder.get()
        self.links[HookRecord(args, kwargs)] = bd.composition
        return self.producer(*args, **kwargs)

    def invalidate(self):
        for composition in self.links.values():
            composition.invalidate()
