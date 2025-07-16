from .schema import *
from . import reader
from . import stringify_impl
from . import json_impl

def from_file(filename):
    if filename.endswith(".json"):
        return json_impl.from_file(filename)
    else:
        return reader.from_file(filename)
    
def to_file(filename, doc):
    if filename.endswith(".json"):
        json_impl.to_file(filename, doc)
    else:
        s_doc = str(doc)
        with open(filename, "w") as fd:
            fd.write(s_doc)
