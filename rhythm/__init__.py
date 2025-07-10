from .dtree import *
from .tree import *
from .step import *
from .euclidean import *
from .parse import *
from . import quantize

grammar = grammar_from_string('''
t1: q1 -> 0.1 n
t1: q1 -> 0.1 r
t2: q1 -> 0.35 (q2 q2)
t4: q1 -> 0.35 (q2 q2 q2 q2)
t3: q1 -> 0.45 (q3 q3 q3)
t6: q1 -> 0.5  (q3 q3 q3 q3 q3 q3)
t8: q1 -> 0.6  (q2 q2 q2 q2 q2 q2 q2 q2)
t5: q1 -> 0.7  (q3 q3 q3 q3 q3)
t7: q1 -> 0.8  (q3 q3 q3 q3 q3 q3 q3)
t9: q1 -> 0.9  (q3 q3 q3 q3 q3 q3 q3 q3 q3)
t11: q1 -> 1.1  (q3 q3 q3 q3 q3 q3 q3 q3 q3 q3 q3)

r4: q2 -> 0.2 s
r5: q2 -> 0.1 n
r5: q2 -> 0.1 r
r6: q2 -> 0.5 (q4 q4)
r7: q2 -> 0.6 (q5 q5 q5)

r8:  q3 -> 0.2 s
r9:  q3 -> 0.1 n
r9:  q3 -> 0.1 r
r10: q3 -> 0.5 (q5 q5)
r14: q3 -> 0.7 (q5 q5 q5)

r11: q4 -> 0.2 s
r12: q4 -> 0.1 n
r12: q4 -> 0.1 r
r13: q4 -> 0.75 (q5 q5 q5)

q5 -> 0.2 s
q5 -> 0.1 n
q5 -> 0.1 r
''')
