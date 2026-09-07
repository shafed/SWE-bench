# Candidate sympy__sympy-24562

- repository: `sympy/sympy`
- base commit: `b1cb676cf92dd1a48365b731979833375b188bf2`
- checkout: `/home/shafed/.cache/nir-v3-src/sympy__sympy-24562`

The checkout is the repository as it stands before the fix, with
no git history. The tests that accompany the fix are not present.

## Problem statement

Rational calc value error
python 3.11, sympy 1.11.1
when calc Rational('0.5', '100'), the value is 1/100100; but Rational(0.5, 100) the value is 1/200, this value is the true value, and the version of sympy 1.8 is normal

