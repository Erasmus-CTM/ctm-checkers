"""Trusted-base checklist planning. Never imports or executes course code.

The GitHub adapter must obtain permissions, authors and head/base repository IDs
from GitHub, not comment text. This module emits decisions, never shell commands.
"""
import base64
import json
import re

from ctm_variants.model import VariantError, canonical

TOKEN = re.compile(r'<!-- ctm-variant:([A-Za-z0-9_-]+) -->')
CHECKED = re.compile(r'^\s*- \[[xX]\] ', re.MULTILINE)


def token(label, locator, content_hash, number=None):
    value = {"label": label, "id": locator, "hash": content_hash, "n": number}
    _identity(value)
    encoded = base64.urlsafe_b64encode(canonical(value).encode()).decode().rstrip('=')
    return '<!-- ctm-variant:' + encoded + ' -->'


def bulk_token(label, records, decisions):
    """Bind the bulk tick to the complete listed id/hash/number set."""
    previous = {row['id']: row for row in decisions}
    identities = [{"label": label, "id": row['id'], "hash": row['hash'],
                   "n": previous[row['id']]['n'] if row['id'] in previous else None}
                  for row in records]
    for identity in identities:
        _identity(identity)
    value = {"label": label, "all": identities}
    encoded = base64.urlsafe_b64encode(canonical(value).encode()).decode().rstrip('=')
    return '<!-- ctm-variant:' + encoded + ' -->'


def _identity(value):
    if (type(value) is not dict or set(value) != {"label", "id", "hash", "n"}
            or any(not isinstance(value[key], str) or not value[key] for key in ('label', 'id', 'hash'))
            or not re.fullmatch('[0-9a-f]{16}', value['hash'])
            or (value['n'] is not None and (type(value['n']) is not int or value['n'] <= 0))):
        raise VariantError('invalid checklist identity')
    return value


def _decode(encoded):
    try:
        if len(encoded) > 262144:
            raise ValueError('oversized token')
        value = json.loads(base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4)))
    except (ValueError, UnicodeError) as error:
        raise VariantError('invalid checklist token') from error
    if type(value) is dict and set(value) == {'label', 'all'}:
        if not isinstance(value['label'], str) or type(value['all']) is not list or not value['all']:
            raise VariantError('invalid bulk checklist identity')
        for identity in value['all']:
            _identity(identity)
            if identity['label'] != value['label']:
                raise VariantError('bulk question differs')
        return value
    return _identity(value)


def plan(body, *, label, records, decisions, sender, permission, comment_author,
         bot_login, head_repository_id, base_repository_id):
    """Plan only authenticated own-comment ticks against current verified records.

    Records are supplied by the unprivileged check artifact for the exact PR
    head. The adapter must verify its head SHA before this call and again before
    committing. Passing verdicts are explicit; absent verdicts cannot approve.
    """
    if permission not in ('write', 'maintain', 'admin') or not sender:
        raise VariantError('variant decisions require write permission')
    if not bot_login or comment_author != bot_login:
        raise VariantError('only the configured bot comment can record ticks')
    if not head_repository_id or head_repository_id != base_repository_id:
        raise VariantError('variant decisions require a same-repository PR')
    current = {row['id']: row for row in records}
    if len(current) != len(records):
        raise VariantError('duplicate current proposal identity')
    previous = {row['id']: row for row in decisions}
    result, skipped, seen = [], [], {}
    for line in body.splitlines():
        if not CHECKED.match(line):
            continue
        matches = TOKEN.findall(line)
        if len(matches) != 1:
            raise VariantError('checked variant needs exactly one identity token')
        decoded = _decode(matches[0])
        identities = decoded.get('all', [decoded])
        for identity in identities:
            _select(identity, label, current, previous, seen, result, skipped, sender,
                    bulk='all' in decoded)
    return {'decisions': result, 'notPassing': skipped}


def _select(identity, label, current, previous, seen, result, skipped, sender, *, bulk):
    if identity['label'] != label:
        raise VariantError('wrong question checklist identity')
    if identity['id'] in seen:
        if seen[identity['id']] != identity:
            raise VariantError('conflicting checklist identities')
        return
    seen[identity['id']] = identity
    row = current.get(identity['id'])
    old = previous.get(identity['id'])
    if row is None or row['hash'] != identity['hash']:
        raise VariantError('checklist is stale; refresh before recording')
    already = old and old['hash'] == row['hash'] and old['status'] == 'approved'
    if identity['n'] != (old['n'] if old else None) and not (already and identity['n'] is None):
        raise VariantError('checklist variant number differs')
    if type(row.get('tests')) is not dict or row['tests'].get('passed') is not True:
        if bulk:
            skipped.append(row['id'])
            return
        raise VariantError('only explicitly passing variants can be approved')
    if already:
        return
    result.append({'id': row['id'], 'hash': row['hash'], 'status': 'approved', 'by': sender})
