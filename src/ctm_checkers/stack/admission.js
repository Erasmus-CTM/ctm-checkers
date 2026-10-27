/* Shared STACK expression admission, AGPL-3.0-or-later.
 * The accompanying data is derived from STACK (GPL-3.0-or-later), distributed
 * under section 13 of both licences; see the wheel's licence texts.
 * Factory only: no eval, CAS, DOM, network, runtime startup or global state.
 * This bounded grammar is CTM's current subset, not STACK's full PHP parser.
 */
(function (root) {
  'use strict';
  function createAdmission(data) {
    // Copy data so callers cannot change a live admission instance's policy.
    data = JSON.parse(JSON.stringify(data));
    if (data.schema !== 1 || !/^[a-f0-9]{40}$/.test(data.stackCommit)) throw new TypeError('Invalid admission data');
    const limits = data.limits;
    const set = name => new Set(data[name]);
    const readable = set('READABLE'), unreadable = set('UNREADABLE'), callable = set('CALLABLE');
    const functions = set('FUNCTIONS'), allowedFunctions = set('functions');
    const trigFunctions = set('TRIG_FUNCTIONS'), forbidden = set('GLOBALLY_FORBIDDEN');
    const logic = new Map(Object.entries(data.logic));
    const logicPrecedence = new Map(Object.entries(data.logicPrecedence));
    function cases(names) {
      const out = new Map();
      for (const name of names) {
        const lower = name.toLowerCase();
        if (!out.has(lower)) out.set(lower, []);
        out.get(lower).push(name);
      }
      return out;
    }
    const variableCases = cases(data.VARIABLES), functionCases = cases(data.FUNCTIONS);
    const allowed = new Set('0123456789,./\\%#&{}[]()$@!"\'?`^~*_+qwertyuiopasdfghjklzxcvbnmQWERTYUIOPASDFGHJKLZXCVBNM:;=>< |-');
    const controls = new Map([['\n', '\\n'], ['\r', '\\r'], ['\t', '\\t'], ['\v', '\\v'], ['\x1b', '\\e'], ['\f', '\\f']]);
    const safeSpaces = [[' or ', 'STACKOR'], [' and ', 'STACKAND'], ['not ', 'STACKNOT'], ['nounnot ', 'STACKNOUNNOT'],
      [' nor ', 'STACKNOR'], [' nand ', 'STACKNAND'], [' xor ', 'STACKXOR'], [' xnor ', 'STACKXNOR'],
      [' implies ', 'STACKIMPLIES'], [' nounor ', 'STACKNOUNOR'], [' nounand ', 'STACKNOUNAND'],
      [' else if ', '%%STACKELSEIF%%'], [' if ', '%%STACKIF%%'], [':if ', ':%%STACKIF%%'],
      [' then ', '%%STACKTHEN%%'], [' else ', '%%STACKELSE%%']];
    const mark = '@@Is@@';
    const comma = 'A comma in your expression appears in a strange way.  Commas are used to separate items in lists, sets etc.  You need to use a decimal point, not a comma, in floating point numbers.';
    class AdmissionError extends Error {
      constructor(message, status = 'invalid') { super(message); this.status = status; }
    }
    const invalid = message => { throw new AdmissionError(message); };
    const unsupported = message => { throw new AdmissionError(message, 'unsupported'); };
    const replace = (text, old, value) => text.split(old).join(value);
    function studentText(raw) {
      let text = raw;
      for (const [old, value] of data.REPLACEMENTS) text = replace(text, old, value);
      for (const character of text) if (!allowed.has(character)) {
        invalid('CAS commands may not contain the following characters: ' + (controls.get(character) || character) + '.');
      }
      return text;
    }
    function spaceMessages(text) {
      const collapsed = text.trim().replace(/[ \t\n\r\f\v]+/g, ' ');
      if (!collapsed.includes(' ')) return [[], new Set()];
      let marked = collapsed, fixed = false;
      for (const [key, placeholder] of safeSpaces) marked = replace(marked, key, placeholder);
      const pattern = /([A-Za-z0-9_)]+)[ ]([A-Za-z0-9_(]+)/g;
      while (pattern.test(marked)) {
        pattern.lastIndex = 0; fixed = true;
        marked = marked.replace(pattern, '$1' + mark + '$2');
      }
      for (const [key, placeholder] of safeSpaces) marked = replace(marked, placeholder, key);
      if (!fixed) return [[], new Set()];
      const form = replace(marked.replace(/[ \t\n\r\f\v]*([-+*/^=,()\[\]{}<>])[ \t\n\r\f\v]*/g, '$1'), mark, '_');
      const messages = ['Illegal spaces found in expression ' + form + '.'], trig = new Set();
      for (const match of marked.matchAll(/([A-Za-z0-9_%]+)@@Is@@/g)) {
        if (trigFunctions.has(match[1])) {
          messages.push('To apply a trig function to its arguments you must use brackets, not spaces.  For example use ' + match[1] + '(...) instead.');
          trig.add(match[1]);
        }
      }
      return [messages, trig];
    }
    // Same lexical order and ASCII rules as the existing bounded Python grammar.
    const lex = () => /[ \t\n\r\f\v]*(?:((?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?)|(%?[A-Za-z_][A-Za-z_0-9]*)|(\*\*|\+\-|[=+*/^(),{}\[\]-]))/g;
    const tokenKind = m => m[1] !== undefined ? 'number' : m[2] !== undefined ? 'name' : 'op';
    function caseMessage(name, variants, kind) {
      const spellings = variants.get(name.toLowerCase()) || [];
      return spellings.length && !spellings.includes(name)
        ? 'Input is case sensitive: ' + name + ' is an unknown ' + kind + '. Did you mean ' + spellings.join(', ') + '?' : null;
    }
    function isReadable(name, keys) {
      if (unreadable.has(name)) return false;
      if (readable.has(name)) return true;
      if (keys.has(name)) return false;
      return (name.length <= 2 && !functions.has(name)) || /[0-9]$/.test(name);
    }
    function isCallable(name, keys) {
      if (callable.has(name)) return true;
      return !(keys.has(name) || name === 'In') && name.length <= 2;
    }
    function identifierMessages(text, keys, authorNames) {
      // finditer intentionally continues past gaps, as the Python reference
      // does when constructing diagnostics for a rejected expression.
      const tokens = [...text.matchAll(lex())].map(m => [tokenKind(m), m[1] ?? m[2] ?? m[3]]);
      const calls = [], variables = [];
      tokens.forEach(([kind, name], index) => {
        if (kind !== 'name' || logic.has(name) || name === 'true' || name === 'false') return;
        const target = tokens[index + 1]?.[1] === '(' ? calls : variables;
        if (!target.includes(name)) target.push(name);
      });
      const messages = [];
      for (const name of calls) {
        if (name === 'In') messages.push('You have typed in the expression In.  The natural logarithm is entered as ln in lower case.  ("Lima November" not "India November")');
        else {
          const message = caseMessage(name, functionCases, 'function');
          if (message) messages.push(message);
        }
      }
      for (const name of variables) {
        const before = messages.length;
        if (forbidden.has(name)) { messages.push('The expression ' + name + ' is forbidden.'); continue; }
        const parts = isReadable(name, keys) ? [name] : [...new Set(name.split('_'))];
        for (const part of parts) {
          if (!(isReadable(part, keys) || (part !== name && isCallable(part, keys)))) {
            messages.push(caseMessage(part, variableCases, 'variable') || 'Forbidden variable or constant: ' + part + '.');
          } else if (part.length > 1) {
            const message = caseMessage(part, variableCases, 'variable');
            if (message) messages.push(message);
          }
        }
        if (authorNames.has(name) && messages.length === before) messages.push('Forbidden variable or constant: ' + name + '.');
      }
      return messages;
    }
    function quoted(character) {
      if (character === "'") return '"\'"';
      return "'" + (character === '\\' ? '\\\\' : character) + "'";
    }
    function tokenize(source) {
      if (!source.trim() || source.length > limits.MAX_CHARS) invalid('Empty or oversized expression');
      const out = [], pattern = lex();
      let pos = 0;
      while (pos < source.length) {
        if (!source.slice(pos).trim()) break;
        pattern.lastIndex = pos;
        const match = pattern.exec(source);
        if (!match || match.index !== pos) {
          const position = pos + /^[ \t\n\r\f\v]*/.exec(source.slice(pos))[0].length;
          const character = source[position];
          invalid('Unexpected character ' + quoted(character) + ' (U+' + character.codePointAt(0).toString(16).toUpperCase().padStart(4, '0') + ') at position ' + position);
        }
        const kind = tokenKind(match), value = match[1] ?? match[2] ?? match[3];
        if (value === '+-') unsupported('Plus/minus input requires explicit alternatives');
        if (kind === 'number' && value.length > limits.MAX_DIGITS) invalid('Number too long');
        out.push([kind, value, pattern.lastIndex - value.length, pattern.lastIndex]);
        pos = pattern.lastIndex;
        if (out.length > limits.MAX_TOKENS) invalid('Too many tokens');
      }
      out.push(['end', '', source.length, source.length]);
      return out;
    }
    const node = (kind, value = '', children = []) => ({kind, value, children});
    const binding = new Map(Object.entries({xor: 0, xnor: 0, implies: 1, or: 2, nounor: 2, and: 4, nounand: 4,
      '=': 6, '+': 10, '-': 10, '*': 20, '/': 20, '^': 30, '**': 30}));
    function parse(text, insertstars) {
      const tokens = tokenize(text);
      let pos = 0;
      const current = () => tokens[pos][1];
      function take(value) { if (current() !== value) invalid('Expected ' + quoted(value)); pos++; }
      function expression(minimum = 0, depth = 0) {
        if (depth > limits.MAX_DEPTH) invalid('Expression nested too deeply');
        const [kind, value] = tokens[pos++];
        let lhs;
        if (value === 'not' || value === 'nounnot') lhs = node('logical', 'not', [expression(5, depth + 1)]);
        else if (value === 'true' || value === 'false') lhs = node('boolean', value);
        else if (kind === 'number') lhs = node('number', value);
        else if (kind === 'name') {
          if (current() === '(') {
            if (!allowedFunctions.has(value.toLowerCase())) invalid('Function ' + value + ' is not allowed; use ' + value + '*(...) for multiplication');
            take('(');
            const args = [];
            if (current() !== ')') do { args.push(expression(0, depth + 1)); if (current() !== ',') break; take(','); } while (true);
            take(')'); lhs = node('call', value.toLowerCase(), args);
          } else lhs = node('name', value);
        } else if (value === '+' || value === '-') lhs = node('unary', value, [expression(25, depth + 1)]);
        else if (value === '(') { lhs = expression(0, depth + 1); take(')'); }
        else if (value === '[' || value === '{') {
          const closing = value === '[' ? ']' : '}', items = [];
          if (current() !== closing) do { items.push(expression(0, depth + 1)); if (current() !== ',') break; take(','); } while (true);
          take(closing); lhs = node(value === '[' ? 'list' : 'set', '', items);
        } else invalid('Expected an expression');
        while (true) {
          const op = current();
          if (op === '[' && 40 >= minimum) { take('['); const idx = expression(0, depth + 1); take(']'); lhs = node('index', '', [lhs, idx]); continue; }
          const previous = tokens[pos - 1], following = tokens[pos];
          const implied = !logic.has(following[1]) && previous[3] === following[2]
            && (previous[0] === 'number' || previous[1] === ')')
            && (following[0] === 'name' || following[1] === '(' || (previous[1] === ')' && following[0] === 'number'));
          const bp = implied ? 20 : (binding.get(op) ?? -1);
          if (bp < minimum) break;
          if (implied && !insertstars) invalid('Missing * for multiplication (this input requires an explicit *)');
          if (!implied) pos++;
          const rhs = expression(op === '^' || op === '**' ? bp : bp + 1, depth + 1);
          if (!implied && logic.has(op)) lhs = node('logical', logic.get(op), [lhs, rhs]);
          else if (!implied && op === '=') {
            if (lhs.kind === 'equation' || rhs.kind === 'equation') unsupported('Chained equations are unsupported');
            lhs = node('equation', '=', [lhs, rhs]);
          } else lhs = node('binary', implied ? '*' : op, [lhs, rhs]);
        }
        return lhs;
      }
      const tree = expression();
      if (tokens[pos][0] !== 'end') invalid(current() === ',' ? comma : 'Unexpected trailing text');
      return tree;
    }
    function precedence(n) {
      if (n.kind === 'logical') return logicPrecedence.get(n.value);
      if (n.kind === 'equation') return 6;
      if (n.kind === 'unary') return 25;
      return n.kind === 'binary' ? binding.get(n.value) : 40;
    }
    function writtenText(n) {
      function child(item, parent, equal = false) {
        const text = writtenText(item), bp = precedence(item);
        return bp < parent || (equal && bp === parent) ? '(' + text + ')' : text;
      }
      if (['number', 'name', 'boolean'].includes(n.kind)) return n.value;
      if (n.kind === 'list' || n.kind === 'set') return (n.kind === 'list' ? '[' : '{') + n.children.map(writtenText).join(',') + (n.kind === 'list' ? ']' : '}');
      if (n.kind === 'call') return n.value + '(' + n.children.map(writtenText).join(',') + ')';
      if (n.kind === 'index') return child(n.children[0], 40) + '[' + writtenText(n.children[1]) + ']';
      if (n.kind === 'unary') return n.value + child(n.children[0], 25);
      if (n.kind === 'logical' && n.value === 'not') return 'not ' + child(n.children[0], 5);
      const power = n.kind === 'binary' && ['^', '**'].includes(n.value);
      let op = n.value === '**' ? '^' : n.value;
      if (n.kind === 'logical') op = ' ' + op + ' ';
      return child(n.children[0], precedence(n), power) + op
        + child(n.children[1], power && n.children[1].kind === 'unary' ? 25 : precedence(n), !power);
    }
    function admitExpression(raw, options = {}) {
      if (typeof raw !== 'string' || !options || typeof options !== 'object' || Array.isArray(options)) throw new TypeError('Expected expression text and admission options');
      const {insertstars = 0, questionVariables = [], authorNames = []} = options;
      for (const names of [questionVariables, authorNames]) if (!Array.isArray(names) || names.some(n => typeof n !== 'string')) throw new TypeError('Expected arrays of author variable names');
      if (insertstars !== 0 && insertstars !== 1) throw new TypeError('Expected insertstars 0 or 1');
      const keys = new Set(questionVariables), names = new Set(authorNames);
      let normalized = null;
      try {
        normalized = studentText(raw);
        const [spaces, trig] = spaceMessages(normalized);
        if (spaces.length) invalid([...spaces, ...(trig.size ? [] : identifierMessages(normalized, keys, names))].join(' '));
        let tree;
        try { tree = parse(normalized, insertstars); }
        catch (error) {
          if (!(error instanceof AdmissionError)) throw error;
          if (error.status === 'invalid' && error.message.startsWith('Function ')) {
            const messages = identifierMessages(normalized, keys, names);
            if (messages.length) invalid(messages.join(' '));
          }
          throw error;
        }
        const messages = identifierMessages(normalized, keys, names);
        if (messages.length) invalid(messages.join(' '));
        return {schema: 1, stackCommit: data.stackCommit, status: 'admitted', normalized, canonical: writtenText(tree), tree, feedback: ''};
      } catch (error) {
        if (!(error instanceof AdmissionError)) throw error;
        return {schema: 1, stackCommit: data.stackCommit, status: error.status, normalized, canonical: null, tree: null, feedback: error.message};
      }
    }
    return Object.freeze({schema: 1, stackCommit: data.stackCommit, admitExpression});
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = createAdmission;
  else root.CTMCreateStackAdmission = createAdmission;
})(typeof globalThis !== 'undefined' ? globalThis : this);
