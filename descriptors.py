import json
import os

def read_desc(filename):
    with open(filename, "r") as fd:
        lines = fd.read().strip().splitlines()
    def parse(line):
        name, spec = line.split(":", 1)
        name = name.strip()
        spec = spec.strip()
        if ' ' in spec:
            rate, mode, channel_count = spec.split(' ')
            ty = bus(rate, mode, int(channel_count))
        else:
            ty = spec
        return name, ty
    return [parse(line) for line in lines]

class bus:
    def __init__(self, rate, mode, channel_count=1):
        self.rate = rate
        self.mode = mode # in/out/in-feedback
        self.channel_count = channel_count

    @property
    def sans_mode(self):
        return self.rate, self.channel_count

    def __str__(self):
        return f"{self.rate} {self.mode} {self.channel_count}"

    def __repr__(self):
        return str(self)

boolean   = "boolean"
unipolar  = "unipolar"
number    = "number"
bipolar   = "bipolar"
pitch     = "pitch"
hz        = "hz"
db        = "db"
duration  = "duration"
trigger   = "trigger"
kinds = [boolean, unipolar, number, bipolar, pitch, hz, db, duration, trigger]

class Saver:
    def __init__(self, directory):
        if not os.path.exists(directory):
            os.mkdir(directory)
        self.directory = directory

    def __call__(self, synthdef, **params):
        desc = "\n".join(f"{n}: {v}" for n,v in params.items())
        with open(os.path.join(self.directory, f'{synthdef.effective_name}.scsynthdef'), 'wb') as fd:
            fd.write(synthdef.compile())
        with open(os.path.join(self.directory, f'{synthdef.effective_name}.desc'), 'w') as fd:
            fd.write(desc)

class Descriptor:
    def __init__(self, synthdef, mdesc, type_param):
        self.synthdef = synthdef
        self.mdesc = mdesc
        self.type_param = type_param

    @property
    def quadratic_controllable(self):
        return (len(set(['a', 'b', 'c', 't', 'trigger']) - set(self.synthdef.parameters)) == 0)

    def field_type(self, name):
        if name == "*":
            return self.type_param
        if name == "~" and self.type_param is not None:
            return "boolean"
        spec = self.mdesc.get(name, None)
        if isinstance(spec, str):
            return spec

    def field_mode(self, name):
        spec = self.mdesc.get(name, None)
        if isinstance(spec, bus):
            return spec.mode

    def field_bus(self, name):
        spec = self.mdesc.get(name, None)
        if isinstance(spec, bus):
            return spec.sans_mode

    def avail(self, ty):
        available_fields = []
        for name, spec in [("n/a", "n/a")] + list(self.mdesc.items()):
            if isinstance(spec, str) and spec in ty:
                available_fields.append(name)
            elif isinstance(spec, str) and len(ty) == 0:
                available_fields.append(name)
            elif spec == "hz" and "pitch" in ty:
                available_fields.append(name)
        if self.type_param is not None and self.type_param in ty:
            available_fields.append("*")
        if self.type_param is not None and "boolean" in ty:
            available_fields.append("~")
        return available_fields

    def autoselect(self, ty):
        a = self.avail(ty)
        return a[0] if len(a) else "n/a"

    @property
    def inputs(self):
        for name, spec in self.mdesc.items():
            if isinstance(spec, bus) and spec.mode == 'in':
                yield name
        
    @property
    def outputs(self):
        for name, spec in self.mdesc.items():
            if isinstance(spec, bus) and spec.mode == 'out':
                yield name


