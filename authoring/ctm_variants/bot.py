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
         bot_login, head_repository_id, base_repository_id, retained=()):
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
    lines = list(_action_lines(body))
    for line in lines:
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
    selected = {item['id']: item for item in result}
    by_number = {entry['n']: entry for entry in decisions}
    for line in lines:
        command = _rejection(line, label)
        if command is None:
            continue
        selectors, reason = command
        targeted = set()
        for kind, value in selectors:
            old = None
            if kind == 'id':
                row = current.get(value)
                old = previous.get(value)
            else:
                old = by_number.get(value)
                row = current.get(old['id']) if old else None
                if old and row is None:
                    moved = [item for item in records if item['hash'] == old['hash']]
                    if len(moved) == 1 and sum(item['hash'] == old['hash'] for item in decisions) == 1:
                        row = moved[0]
            if row is None and old and old['status'] == 'rejected' and old.get('reason', '') == reason:
                retained_same = any(p['record']['id'] == old['id'] and p['record']['hash'] == old['hash'] for p in retained)
                if retained_same:
                    continue  # An unchanged recorded retirement is an idempotent rerun.
            if row is None and old and old['status'] == 'approved':
                # Shared recorder rechecks full history proof before its leased write.
                from ctm_variants.model import classify
                state = next(entry['state'] for entry in classify(decisions, records)['entries']
                             if entry['entry']['id'] == old['id'])
                if state == 'gone':
                    row = next((p['record'] for p in retained
                                if p['record']['id'] == old['id'] and p['record']['hash'] == old['hash']), None)
            if row is None:
                raise VariantError('rejection selector needs a current candidate or retained gone approval')
            if row['id'] in targeted:
                raise VariantError('rejection selectors must name distinct candidates')
            targeted.add(row['id'])
            if old is None:
                moved = [entry for entry in decisions if entry['hash'] == row['hash']]
                if len(moved) == 1 and sum(item['hash'] == row['hash'] for item in records) == 1:
                    old = moved[0]
            item = {'id': row['id'], 'hash': row['hash'], 'status': 'rejected', 'by': sender, 'reason': reason}
            existing = selected.get(row['id'])
            if existing:
                if existing != item:
                    raise VariantError('conflicting approval/rejection commands')
                continue
            if old and old['hash'] == row['hash'] and old['status'] == 'rejected' and old.get('reason', '') == reason:
                continue  # Whole-state reruns do not append another identical rejection.
            selected[row['id']] = item
            result.append(item)
    return {'decisions': result, 'notPassing': skipped}


def _action_lines(body):
    """Ignore fenced examples and quoted/indented command text."""
    fence = None
    for line in body.splitlines():
        match = re.match(r'^ {0,3}(`{3,}|~{3,})', line)
        if match:
            mark = match[1]
            if fence is None:fence = mark
            elif mark[0] == fence[0] and len(mark) >= len(fence) and not line[match.end():].strip():fence = None
            continue
        if fence is None and not line.expandtabs(4).startswith("    "):yield line


def _rejection(line, label):
    """Parse data, never shell: positive n or id:<literal/JSON string>, reason JSON.

    Examples: /variants reject 7 12 "reason"
              /variants reject id:"opaque candidate id" "reason"
    The own-comment question marker supplies scope; an explicit matching label
    is accepted for the older documented /variants reject LABEL 7 form.
    """
    if not line.startswith('/variants'):
        return None
    if not line.startswith('/variants reject '):
        raise VariantError('unsupported variants command')
    rest, selectors, reason, position = line[len('/variants reject '):], [], None, 0
    decoder = json.JSONDecoder()
    explicit_label = False
    while position < len(rest):
        while position < len(rest) and rest[position].isspace():position += 1
        if position == len(rest):break
        if rest[position] == '"':
            try:reason, end = decoder.raw_decode(rest, position)
            except ValueError as error:raise VariantError('rejection reason must be a quoted JSON string') from error
            if rest[end:].strip():raise VariantError('rejection reason must be the last argument')
            break
        if rest.startswith('id:', position):
            position += 3
            if position < len(rest) and rest[position] == '"':
                try:value, position = decoder.raw_decode(rest, position)
                except ValueError as error:raise VariantError('invalid quoted rejection id') from error
                if position < len(rest) and not rest[position].isspace():raise VariantError('rejection selectors need whitespace separators')
            else:
                end = position
                while end < len(rest) and not rest[end].isspace():end += 1
                value, position = rest[position:end], end
            if not isinstance(value, str) or not value or len(value) > 4096:
                raise VariantError('rejection id must be a bounded nonempty current locator')
            selectors.append(('id', value))
        else:
            end = position
            while end < len(rest) and not rest[end].isspace():end += 1
            value, position = rest[position:end], end
            if not selectors and not explicit_label and value == label and not value.isdecimal():
                explicit_label = True
                continue
            if not re.fullmatch(r'[1-9][0-9]{0,15}', value):
                raise VariantError('rejection numbers must be positive stable integers; use id: for new proposals')
            selectors.append(('n', int(value)))
        if len(selectors) > 250:raise VariantError('rejection selector budget exceeded')
    if not selectors or not isinstance(reason, str) or not reason.strip() or len(reason) > 2000:
        raise VariantError('rejection needs current selectors and a nonempty quoted reason')
    return selectors, reason


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
