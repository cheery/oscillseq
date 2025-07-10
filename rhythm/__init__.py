from .dtree import *
from .tree import *
from .step import *
from .euclidean import *
from .parse import *
from . import quantize

grammar = grammar_from_string('''
r1: q1 -> 0.1 n
r2: q1 -> 0.35 (q2 q2)
r3: q1 -> 0.45 (q3 q3 q3)

r4: q2 -> 0.2 s
r5: q2 -> 0.1 n
r6: q2 -> 0.5 (q4 q4)
r7: q2 -> 0.6 (q5 q5 q5)

r8:  q3 -> 0.2 s
r9:  q3 -> 0.1 n
r10: q3 -> 0.5 (q5 q5)

r11: q4 -> 0.2 s
r12: q4 -> 0.1 n
r13: q4 -> 0.75 (q5 q5 q5)

q5 -> 0.2 s
q5 -> 0.1 n
''')
