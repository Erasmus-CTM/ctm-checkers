"""Conservative author guidance from recorded decisions; never edit/evaluate code."""
from fractions import Fraction
import keyword
import re
from ctm_variants.model import validate_entries

_IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z0-9_]*\Z")
_NUMBER = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+|/[1-9][0-9]*)?\Z")


def _numeric(value):
    if not isinstance(value, str) or len(value) > 128 or not _NUMBER.fullmatch(value):
        return None
    return Fraction(value)


def rejection_hint(entries):
    """Suggest constraints after >=5 rejections and >=one third rejected.

    A suggestion needs a common exact scalar value in every rejection and
    a contrasting value in every approval. Only bounded numeric literals are compared exactly; no authored code is executed;
    ambiguous values, missing variables and the absence of approvals yield only
    the general hint. Historical decisions and snapshots remain untouched.
    """
    validate_entries(entries)
    rejected = [entry for entry in entries if entry['status'] == 'rejected']
    if len(rejected) < 5 or len(rejected) * 3 < len(entries):
        return None
    approved = [entry for entry in entries if entry['status'] == 'approved']
    reasons = list(dict.fromkeys(entry.get('reason') or '(No reason recorded)' for entry in rejected))
    suggestions = []
    if approved:
        for name, value in sorted(rejected[0]['snapshot']['variables'].items()):
            if (not _IDENTIFIER.fullmatch(name) or keyword.iskeyword(name)
                    or _numeric(value) is None):
                continue
            number = _numeric(value)
            contrasting = [_numeric(entry['snapshot']['variables'].get(name)) for entry in approved]
            if (all(_numeric(entry['snapshot']['variables'].get(name)) == number for entry in rejected)
                    and all(other is not None and other != number for other in contrasting)):
                suggestions.append('require({} != {})'.format(name, value))
    return {'rejected': len(rejected), 'decided': len(entries), 'reasons': reasons,
            'suggestions': suggestions}
