"""The Python checker library of CTM Assessment (grading in the browser and at build time)."""

# The package root imports nothing, so a component can read the version
# without loading SymPy.
__version__ = "0.1.0.dev0"
# Rises only for an incompatible change of browser.call, the request and
# result shapes or an author contract (docs/api.md).
API = 1
