from lark import Lark, Transformer, v_args
from dataclasses import dataclass
from typing import Set, List, Tuple, Dict, Optional, Any
from supriya import ugens, CalculationRate
from supriya.ugens import UGen, PseudoUGen, UGenOperable, SynthDefBuilder
from supriya.enums import BinaryOperator, UnaryOperator
import descriptors

synth_grammar = """
    start: (statement ";")* -> as_list
    
    statement: apply [operator] "=" expr -> assign
             | apply ":" apply ["=" expr]  -> annotated

    operator: "*" -> mul_op
            | "/" -> div_op
            | "+" -> plus_op
            | "-" -> minus_op

    ?expr: sum

    ?sum: product
        | "-" sum         -> neg
        | sum "+" product -> add
        | sum "-" product -> sub

    ?product: repeat
        | product "*" repeat -> multiply
        | product "/" repeat -> divide
    
    ?repeat: ann
           | repeat "!" ann -> repeat

    ?ann: apply
        | apply ":" apply ["=" expr] -> annotated

    ?apply: term
          | apply term -> app
          | apply NAME "'" term -> app_k

    ?term: "(" expr ")"
         | NUMBER   -> number
         | NAME     -> var
         | term "." NAME -> attr
         | "[" "]" -> list
         | "[" expr ("," expr)* "]" -> list

    %import common.CNAME -> NAME
    %import common.NUMBER
    %import common.WS
    %import common.SH_COMMENT
    %ignore WS
    %ignore SH_COMMENT
"""

@dataclass
class Object:
    pass

@dataclass
class SemiLocal(Object):
    lift : Any

@dataclass
class Bus(Object):
    name : str
    calculation_rate : CalculationRate
    channel_count : int
    operable : UGenOperable
    mode : str

    def as_input(self):
        mk = getattr(ugens.In, rate_to_attr[self.calculation_rate])
        return mk(bus=self.operable, channel_count=self.channel_count)

    def as_output(self, val):
        mk = getattr(ugens.Out, rate_to_attr[self.calculation_rate])
        mk(bus=self.operable, source=to(val))

@dataclass
class Environ:
    builder : SynthDefBuilder
    var : Dict[str, UGenOperable | int | float]
    par : Dict[str, Any]
    mdesc : List[Any]

@dataclass
class Local(Object):
    env : Environ
    name : str

    def to(self):
        return self.env.var[self.name]

    def store(self, val):
        self.env.var[self.name] = v = to(val)
        return v

    def inplace(self, op, val):
        self.env.var[self.name] = v = to(op(self.env.var[self.name], to(val)))
        return v

@dataclass
class UGenLibrary(Object):
    name : str
    ugen : UGen
    keys : Tuple[str]
    cr : Set[int]

    def attr(self, name):
        if name not in self.cr:
            raise Exception(f"Ugen {self.name} has no calculation rate {name}")
        return UGenCR(self, name)

@dataclass
class UGenCR(Object):
    ugenlibrary : UGenLibrary
    calculation_rate : str

    def to(self):
        return getattr(self.ugenlibrary.ugen, self.calculation_rate)()

    def apply(self, *args, **kwargs):
        kwargs.update(zip(self.ugenlibrary.keys, args))
        kwargs = {n:to(v) for n,v in kwargs.items()}
        return getattr(self.ugenlibrary.ugen, self.calculation_rate)(**kwargs)

@dataclass
class CalculationRateLibrary(Object):
    calculation_rate : CalculationRate

    def to(self):
        return PortSpec(self.calculation_rate, 1)

    def apply(self, channel_count):
        return PortSpec(self.calculation_rate, channel_count)

@dataclass
class PortSpec(Object):
    calculation_rate : CalculationRate
    channel_count : int

    def bind(self, slot, val):
        assert isinstance(slot, Local)
        assert slot.name not in slot.env.var
        assert slot.name not in slot.env.par
        parameter = slot.env.builder.add_parameter(name=slot.name, value=0, rate=CalculationRate.IR)
        mode = "in" if val is None else "out"
        bus = Bus(slot.name, self.calculation_rate, self.channel_count, parameter, mode)
        slot.env.mdesc[slot.name] = descriptors.bus(
            rate_to_attr[self.calculation_rate],
            mode,
            self.channel_count
        )
        if val is not None:
            bus.as_output(val)
            slot.env.par[slot.name] = None
            return None
        else:
            slot.env.par[slot.name] = operable = bus.as_input()
            return operable

@dataclass
class ParameterSpec(Object):
    flavor : str

    def bind(self, slot, val):
        assert isinstance(slot, Local)
        assert slot.name not in slot.env.var
        assert slot.name not in slot.env.par
        val = to(val) or 0.0
        parameter = slot.env.builder.add_parameter(name=slot.name, value=val)
        slot.env.par[slot.name] = parameter
        slot.env.mdesc[slot.name] = self.flavor
        return parameter

def make_gate(env):
    assert "gate" not in env.var
    parameter = env.builder.add_parameter(name="gate", value=1)
    env.par["gate"] = parameter
    return parameter

@dataclass
class Operator(Object):
    fn : Any

    def to(self):
        return self.fn()

    def apply(self, *args, **kwargs):
        return self.fn(*map(to, args), **{n:to(v) for n,v in kwargs.items()})

uop = {
    "-": (lambda x: -x),
}

bop = {
    "!": (lambda x, y: [x]*int(y)),
    "*": (lambda x, y: x * y),
    "/": (lambda x, y: x / y),
    "+": (lambda x, y: x + y),
    "-": (lambda x, y: x - y)
}

available_libraries = {
    "ir": CalculationRateLibrary(CalculationRate.IR),
    "kr": CalculationRateLibrary(CalculationRate.KR),
    "ar": CalculationRateLibrary(CalculationRate.AR),
    "dr": CalculationRateLibrary(CalculationRate.DR),
    "boolean": ParameterSpec("boolean"),
    "unipolar": ParameterSpec("unipolar"),
    "number": ParameterSpec("number"),
    "bipolar": ParameterSpec("bipolar"),
    "pitch": ParameterSpec("pitch"),
    "hz": ParameterSpec("hz"),
    "db": ParameterSpec("db"),
    "duration": ParameterSpec("duration"),
    "trigger": ParameterSpec("trigger"),
    "abs": Operator(abs),
    "dbamp": Operator(lambda x: x.db_to_amplitude()),
    "midicps": Operator(lambda x: x.midi_to_hz()),
    "Envelope": Operator(ugens.Envelope),
    "adsr": Operator(ugens.Envelope.adsr),
    "asr": Operator(ugens.Envelope.asr),
    "perc": Operator(ugens.Envelope.percussive),
    "linen": Operator(ugens.Envelope.linen),
    "triangle": Operator(ugens.Envelope.triangle),
    "envelope_from_segments": Operator(ugens.Envelope.from_segments),
    "freeself": 2,
    "gate": SemiLocal(make_gate),

    "and": Operator(lambda x, y: x & y),
    "ceil": Operator(lambda x: x.__ceil__()),
    "eq": Operator(lambda x, y: x.__eq__(y)),
    "floor": Operator(lambda x: x.__floor__()),
    "floordiv": Operator(lambda x, y: x.__floordiv__(y)),
    "ge": Operator(lambda x, y: x.__ge__(y)),
    "gt": Operator(lambda x, y: x.__gt__(y)),
    "invert": Operator(lambda x: x.__invert__()),
    "lsh": Operator(lambda x,y: x.__lshift__(y)),
    "rsh": Operator(lambda x,y: x.__rshift__(y)),
    "le": Operator(lambda x, y: x.__le__(y)),
    "lt": Operator(lambda x, y: x.__lt__(y)),
    "mod": Operator(lambda x, y: x.__mod__(y)),
    "ne": Operator(lambda x, y: x.__ne__(y)),
    "or": Operator(lambda x, y: x.__or__(y)),
    "pow": Operator(lambda x, y: x.__pow__(y)),
    "xor": Operator(lambda x, y: x.__xor__(y)),
    "absdiff": Operator(lambda x, y: x.absdiff(y)),
    "acos": Operator(lambda x: x.acos()),
    "asin": Operator(lambda x: x.asin()),
    "atan": Operator(lambda x: x.atan()),
    "atan2": Operator(lambda x: x.atan2()),
    "cos": Operator(lambda x: x.cos()),
    "cosh": Operator(lambda x: x.cosh()),
    "cubed": Operator(lambda x: x.cubed()),
    "am_clip": Operator(lambda x, y: x.am_clip(y)),
    "ampdb": Operator(lambda x: x.amplitude_to_db()),
    "bi_lin_rand": Operator(lambda x: x.bi_lin_rand()),
    "bi_rand": Operator(lambda x: x.bi_rand()),
    "clip": Operator(lambda x, mi, ma: x.clip(mi, ma)),
    "clip2": Operator(lambda x, m: x.clip2(m)),
    "difference_of_squares": Operator(lambda x, y: x.difference_of_squares(y)),
    "digit_value": Operator(lambda x: x.digit_value()),
    "distort": Operator(lambda x: x.distort()),
    "exceeds": Operator(lambda x, y: x.exceeds(y)),
    "excess": Operator(lambda x, y: x.excess(y)),
    "exponential": Operator(lambda x: x.exponential()),
    "exponential_rand_range": Operator(lambda x,y: x.exponential_rand_range(y)),
    "fold2": Operator(lambda x, m: x.clip2(m)),
    "fractional_part": Operator(lambda x: x.fractional_part()),
    "gcd": Operator(lambda x, y: x.gcd(y)),
    "hanning_window": Operator(lambda x: x.hanning_window()),
    "hypot": Operator(lambda x, y: x.hypot(y)),
    "hypotx": Operator(lambda x, y: x.hypotx(y)),
    "cpsmidi": Operator(lambda x: x.hz_to_midi()),
    "cpsoct": Operator(lambda x: x.hz_to_octave()),
    "is_equal_to": Operator(lambda x, y: x.is_equal_to(y)),
    "is_not_equal_to": Operator(lambda x, y: x.is_not_equal_to(y)),
    "lagged": Operator(lambda x, *y: x.lagged(*y)),
    "lcm": Operator(lambda x, y: x.lcm(y)),
    "lin_rand": Operator(lambda x: x.lin_rand()),
    "log": Operator(lambda x: x.log()),
    "log10": Operator(lambda x: x.log10()),
    "log2": Operator(lambda x: x.log2()),
    "max": Operator(lambda x, y: x.max(y)),
    "min": Operator(lambda x, y: x.min(y)),
    "octcps": Operator(lambda x: x.octave_to_hz()),
    "rand": Operator(lambda x: x.rand()),
    "rand_range": Operator(lambda x,y: x.rand_range(y)),
    "ratiomidi": Operator(lambda x: x.ratio_to_semitones()),
    "reciprocal": Operator(lambda x: x.reciprocal()),
    "rectangle_window": Operator(lambda x: x.rectangle_window()),
    "ring1": Operator(lambda x, y: x.ring1(y)),
    "ring2": Operator(lambda x, y: x.ring2(y)),
    "ring3": Operator(lambda x, y: x.ring3(y)),
    "ring4": Operator(lambda x, y: x.ring4(y)),
    "round": Operator(lambda x, y: x.round(y)),
    "round_up": Operator(lambda x, y: x.round_up(y)),
    "s_curve": Operator(lambda x: x.s_curve()),
    "scale": Operator(lambda x, *y: x.scale(*y)),
    "linlin": Operator(lambda x, *y: x.scale_negative(*y)),
    "midiratio": Operator(lambda x: x.semitones_to_ratio()),
    "sign": Operator(lambda x: x.sign()),
    "silence": Operator(lambda x: x.silence()),
    "sin": Operator(lambda x: x.sin()),
    "sinh": Operator(lambda x: x.sinh()),
    "softclip": Operator(lambda x: x.softclip()),
    "sqrt": Operator(lambda x: x.sqrt()),
    "square_of_difference": Operator(lambda x, y: x.square_of_difference(y)),
    "square_of_sum": Operator(lambda x, y: x.square_of_sum(y)),
    "squared": Operator(lambda x: x.squared()),
    "sum3_rand": Operator(lambda x: x.sum3_rand()),
    "sum_of_squares": Operator(lambda x, y: x.sum_of_squares(y)),
    "tan": Operator(lambda x: x.tan()),
    "tanh": Operator(lambda x: x.tanh()),
    "through": Operator(lambda x: x.through()),
    "triangle_window": Operator(lambda x: x.triangle_window()),
    "truncate": Operator(lambda x, y: x.truncate(y)),
    "unsigned_shift": Operator(lambda x, y: x.unsigned_shift(y)),
    "welch_window": Operator(lambda x: x.welch_window()),
    "wrap2": Operator(lambda x, y: x.wrap2(y)),
}

rate_to_attr = {
    CalculationRate.SCALAR: "ir",
    CalculationRate.DEMAND: "dr",
    CalculationRate.CONTROL: "kr",
    CalculationRate.AUDIO: "ar",
}

for name in ugens.__all__:
    obj = getattr(ugens, name)
    if obj == ugens.EnvGen:
        available_libraries[name] = UGenLibrary(name, obj,
            keys = ('envelope', 'gate', 'level_scale', 'level_bias', 'time_scale', 'done_action'),
            cr   = {"kr", "ar"})
    elif isinstance(obj, type):
        if obj.__bases__ == (UGen,):
            cr = set(rate_to_attr[c] for c in obj._valid_calculation_rates)
            available_libraries[name] = UGenLibrary(name, obj, obj._ordered_keys, cr)
        #if obj.__bases__ == (PseudoUGen,):
        #    print("TODO:", name, cr)
        #if obj.__bases__ == (ugens.pv.PV_ChainUGen,):
        #    print("TODO:", name)

@dataclass
class Expr:
    def flatten(self, env):
        return self, [], {}

@dataclass
class Assign(Expr):
    lhs : Expr
    op  : str | None
    rhs : Expr

    def evaluate(self, env, local):
        lhs = evaluate(env, self.lhs, local=True)
        val = evaluate(env, self.rhs, local=False)
        if self.op is None:
            return lhs.store(val)
        else:
            return lhs.inplace(bop[self.op], val)

@dataclass
class UnaryOp(Expr):
    op : str
    rhs : Expr

    def evaluate(self, env, local):
        rhs = evaluate(env, self.rhs, False)
        return uop[self.op](to(rhs))

@dataclass
class BinaryOp(Expr):
    op : str
    lhs : Expr
    rhs : Expr

    def evaluate(self, env, local):
        lhs = evaluate(env, self.lhs, False)
        rhs = evaluate(env, self.rhs, False)
        return bop[self.op](to(lhs), to(rhs))

@dataclass
class Annotated(Expr):
    lhs : Expr
    rhs : Expr
    val : Expr

    def evaluate(self, env, local):
        lhs = evaluate(env, self.lhs, local=True)
        rhs = evaluate(env, self.rhs, local=False)
        if self.val is None:
            return rhs.bind(lhs, None)
        else:
            val = evaluate(env, self.val, local=False)
            return rhs.bind(lhs, val)

@dataclass
class Constant(Expr):
    value : int | float

    def evaluate(self, env, local):
        return self.value

@dataclass
class Var(Expr):
    name : str

    def evaluate(self, env, local):
        if self.name in env.par:
            return env.par[self.name]
        elif local or self.name in env.var:
            return Local(env, self.name)
        else:
            if self.name not in available_libraries:
                print(list(available_libraries.keys()))
            obj = available_libraries[self.name]
            if isinstance(obj, SemiLocal):
                return obj.lift(env)
            else:
                return available_libraries[self.name]

@dataclass
class Attr(Expr):
    lhs : Expr
    name : str

    def evaluate(self, env, local):
        return attr(evaluate(env, self.lhs, local), self.name)

@dataclass
class Apply(Expr):
    lhs : Expr
    rhs : Expr

    def flatten(self, env):
        callee, args, kwargs = self.lhs.flatten(env)
        return callee, args + [evaluate(env, self.rhs, False)], kwargs

@dataclass
class ApplyK(Expr):
    lhs : Expr
    name : str
    rhs : Expr

    def flatten(self, env):
        callee, args, kwargs = self.lhs.flatten(env)
        assert self.name not in kwargs
        kwargs[self.name] = evaluate(env, self.rhs, False)
        return callee, args, kwargs

@dataclass
class List(Expr):
    exprs : List[Expr]

    def evaluate(self, env, local):
        return [to(evaluate(env, x, False)) for x in self.exprs]

def attr(obj, name):
    if isinstance(obj, Object):
        return obj.attr(name)
    else:
        raise Exception(f"no attr supported for: {obj}")

def to(obj):
    while isinstance(obj, Object):
        obj = obj.to()
    return obj

def evaluate(env, obj, local):
    obj, args, kwargs = obj.flatten(env)
    if len(args) + len(kwargs) != 0:
        obj = obj.evaluate(env, False)
        if isinstance(obj, Object):
            return obj.apply(*args, **kwargs)
        else:
            raise Exception(f"cannot invoke {obj}")
    return obj.evaluate(env, local)

@v_args(inline=True)
class SynthLangTransformer(Transformer):
    @v_args(inline=False)
    def as_list(self, seq):
        return seq

    def assign(self, lhs, op, rhs):
        return Assign(lhs, op, rhs)

    def mul_op(self):
        return "*"

    def div_op(self):
        return "/"

    def plus_op(self):
        return "+"

    def minus_op(self):
        return "-"

    def annotated(self, lhs, mhs, rhs):
        return Annotated(lhs, mhs, rhs)

    def multiply(self, lhs, rhs):
        return BinaryOp("*", lhs, rhs)

    def divide(self, lhs, rhs):
        return BinaryOp("*", lhs, rhs)

    def add(self, lhs, rhs):
        return BinaryOp("+", lhs, rhs)

    def sub(self, lhs, rhs):
        return BinaryOp("-", lhs, rhs)

    def repeat(self, lhs, rhs):
        return BinaryOp("!", lhs, rhs)

    def neg(self, rhs):
        return UnaryOp("-", rhs)

    def app(self, lhs, rhs):
        return Apply(lhs, rhs)

    def app_k(self, lhs, name, rhs):
        return ApplyK(lhs, str(name), rhs)

    def number(self, num):
        num = str(num)
        if "." in num:
            return Constant(float(num))
        return Constant(int(num))

    def var(self, name):
        return Var(str(name))

    def attr(self, lhs, name):
        return Attr(lhs, str(name))

    @v_args(inline=False)
    def list(self, exprs):
        return List(exprs)

parser = Lark(synth_grammar, parser="lalr", transformer=SynthLangTransformer())

def from_string(source, name):
    with SynthDefBuilder() as builder:
        env = Environ(builder, {}, {}, {})
        for x in parser.parse(source):
            evaluate(env, x, False)
    return builder.build(name=name), env.mdesc

example = """
sig = Saw.ar (midicps (note : pitch = 69));
sig *= EnvGen.kr adsr gate done_action' freeself;
sig *= dbamp (volume : db = -6);
out : ar 2 = sig ! 2;
"""

if __name__=="__main__":
    synthdef = from_string(example, name="foobar")

    import supriya, time, os
    if "SC_JACK_DEFAULT_INPUTS" not in os.environ:
        os.environ["SC_JACK_DEFAULT_INPUTS"] = "system"
    if "SC_JACK_DEFAULT_OUTPUTS" not in os.environ:
        os.environ["SC_JACK_DEFAULT_OUTPUTS"] = "system"
    
    s = supriya.Server().boot()
    s.add_synthdefs(synthdef)
    s.sync()
    s.add_synth(synthdef, gate=1, note=63)#, freq=440)
    time.sleep(2)
