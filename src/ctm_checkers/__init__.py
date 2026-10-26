"""The Python checker library of CTM Assessment (grading in the browser and at build time)."""

# The package root imports no SymPy, so a component can read the version
# without loading it.
__version__ = "0.12.0.dev0"
# Major levels describe incompatibilities; a string preserves an additive
# minor level exactly (1.10 must not become the floating-point number 1.1).
API = "1.1"

# The STACK engine (ctm_checkers.stack) comes in a wheel of its own
# (ctm_checkers_stack-<version>-py3-none-any.whl), so that pages with
# math-exercise do not carry it: with both wheels on sys.path, this adds the
# second wheel's ctm_checkers/ to the package (pkgutil-style namespace).
__path__ = __import__("pkgutil").extend_path(__path__, __name__)
