"""Bounded native CTM placeholder rendering, not component wiring. AGPL-3.0-or-later."""
import ast
import builtins
from dataclasses import dataclass
import json
import keyword
import math
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ctm_variants.generation import GenerationError, MAX_IPC, _helpers, _read_lines, _run, _source

MAX_TEMPLATE = 16384
MAX_PLACEHOLDERS = 128
MAX_PRECISION = 1000
DISPLAY = {"dispdp", "dispsf"}


@dataclass(frozen=True)
class DisplayValue:
    """Presentation only: neither arithmetic nor the exact teacher codec accepts it."""
    style: str
    precision: int
    text: str
    latex: str


def _position(text, start, end):
    return {"start":start, "end":end, "line":text.count("\n",0,start)+1,
            "column":start-text.rfind("\n",0,start)}


def _escaped(text, index):
    count = 0
    while index > 0 and text[index-1] == "\\":
        count, index = count+1, index-1
    return bool(count % 2)


def _math_end(text, start, opener):
    closer = {"$":"$", "$$":"$$", "\\(":"\\)", "\\[":"\\]"}[opener]
    begin = start+len(opener)
    if opener == "$" and (begin == len(text) or text[begin].isspace() or text[begin] == "$"):
        return None
    index = begin
    while True:
        index = text.find(closer,index)
        if index < 0 or "\n\n" in text[begin:index]:
            return None
        if not _escaped(text,index):
            if opener != "$" or (index > begin and not text[index-1].isspace()
                    and text[index-1] != "$" and (index+1 == len(text) or not text[index+1].isdigit())
                    and not text.startswith("$$",index)):
                return index
        index += len(closer)


def _scan(text):
    if not isinstance(text,str) or len(text.encode("utf-8")) > MAX_TEMPLATE:
        raise GenerationError("template exceeds byte limit")
    tokens, count = [], 0
    def region(begin,end,in_math=False):
        nonlocal count
        index = begin
        while index < end:
            if text.startswith("\\\\",index):
                tokens.append(text[index:index+2]); index += 2; continue
            if text.startswith(("\\{@","\\{#"),index):
                closer = "@}" if text[index+2] == "@" else "#}"
                finish = text.find(closer,index+3,end)
                finish = finish+2 if finish >= 0 else index+3
                tokens.append(text[index+1:finish]); index = finish; continue
            if not in_math:
                if index == 0 or text[index-1] == "\n":
                    match = re.match(r" {0,3}(`{3,}|~{3,})[^\n]*(?:\n|$)",text[index:end])
                    if match:
                        fence = match.group(1)
                        close = re.search(r"(?m)^ {0,3}"+re.escape(fence[0])+"{"+str(len(fence))+r",}[ \t]*(?:\n|$)",text[index+match.end():end])
                        finish = index+match.end()+close.end() if close else end
                        tokens.append(text[index:finish]); index = finish; continue
                if text[index] == "`":
                    run = re.match(r"`+",text[index:end]).group()
                    close = re.search(r"(?<!`)"+re.escape(run)+r"(?!`)",text[index+len(run):end])
                    if close:
                        finish = index+len(run)+close.end()
                        tokens.append(text[index:finish]); index = finish; continue
                    tokens.append(run); index += len(run); continue
                opener = next((mark for mark in ("$$","$","\\(","\\[") if text.startswith(mark,index)),None)
                finish = _math_end(text,index,opener) if opener else None
                if finish is not None and finish < end:
                    closer = {"$":"$","$$":"$$","\\(":"\\)","\\[":"\\]"}[opener]
                    span = _position(text,index,finish+len(closer))
                    tokens.append({"kind":"math-open","text":opener,"span":span})
                    region(index+len(opener),finish,True)
                    tokens.append({"kind":"math-close","text":closer,"span":span})
                    index = finish+len(closer); continue
            if text.startswith(("{@","{#"),index):
                closer = "@}" if text[index+1] == "@" else "#}"
                finish = text.find(closer,index+2,end)
                span = _position(text,index,end if finish < 0 else finish+2)
                if finish < 0:
                    raise GenerationError("line {line}, column {column}: unclosed placeholder".format(**span))
                expression = text[index+2:finish].strip()
                if not expression or "{@" in expression or "{#" in expression:
                    raise GenerationError("line {line}, column {column}: empty or nested placeholder".format(**span))
                count += 1
                if count > MAX_PLACEHOLDERS:
                    raise GenerationError("placeholder count exceeds limit")
                tokens.append({"kind":"latex" if text[index+1] == "@" else "raw", "expression":expression,
                               "span":span,"in_math":in_math})
                index = finish+2; continue
            if text.startswith(("@}","#}"),index):
                span = _position(text,index,index+2)
                raise GenerationError("line {line}, column {column}: unmatched placeholder closer".format(**span))
            if text[index] == "\\" and index+1 < end:
                tokens.append(text[index:index+2]); index += 2; continue
            tokens.append(text[index]); index += 1
    region(0,len(text))
    return tokens


def _exact(value, *, matrix=False):
    import sympy as sp
    from ctm_checkers.variants import encode
    if isinstance(value,sp.MatrixBase):
        if not matrix:
            raise ValueError("raw matrices need separate field/input rendering; unsupported here")
        for entry in value:
            _exact(entry)
    elif (not isinstance(value,sp.Expr) or value.has(sp.Float,sp.oo,-sp.oo,sp.zoo,sp.nan)
            or value.is_finite is False or value.is_commutative is not True):
        raise ValueError("placeholder needs an exact finite scalar expression")
    for symbol in value.free_symbols:
        if (not symbol.name.isidentifier() or symbol.name.startswith("_")
                or symbol.name == "inf" or symbol.name in vars(sp)
                or symbol.name in vars(builtins) or keyword.iskeyword(symbol.name)):
            raise ValueError("unsupported placeholder symbol name")
    encode(value)  # The existing bounded exact codec remains the only value protocol.
    return value


def _input(value):
    from sympy.printing.str import StrPrinter
    class Printer(StrPrinter):
        def _print_Abs(self,item):
            return "abs("+self._print(item.args[0])+")"
    return Printer().doprint(_exact(value)).replace("**","^")


def _display(style,value,precision):
    import sympy as sp
    from ctm_checkers.math_exercise.numeric import round_exact, sigfig_exact
    if (isinstance(precision,bool) or not isinstance(precision,(int,sp.Integer))
            or not (0 if style == "dispdp" else 1) <= precision <= MAX_PRECISION):
        raise ValueError("invalid display precision (dp 0..1000, sf 1..1000)")
    precision = int(precision)
    rounded = round_exact(value,precision) if style == "dispdp" else sigfig_exact(value,precision)
    def fixed(number,places):
        from decimal import Decimal
        negative = number < 0
        # Decimal(int) is exact and does not cross Python 3.11+'s int-to-str
        # digit limit when adding fractional display zeros to a large value.
        digits = format(Decimal(abs(int(number*10**places))),"f")
        if places:
            digits = digits.zfill(places+1)
            digits = digits[:-places]+"."+digits[-places:]
        return ("-" if negative else "")+digits
    if style == "dispdp":
        text = fixed(rounded,precision)
        return DisplayValue(style,precision,text,text)
    if rounded == 0:
        text = "0"+("."+"0"*(precision-1) if precision > 1 else "")
        return DisplayValue(style,precision,text,text)
    exponent = sp.floor(sp.log(abs(rounded),10))
    if not isinstance(exponent,sp.Integer):
        raise ValueError("cannot determine display magnitude")
    places = precision-int(exponent)-1
    if places > 0:
        text = fixed(rounded,places)
        return DisplayValue(style,precision,text,text)
    mantissa = fixed(rounded/sp.Integer(10)**exponent,precision-1)
    return DisplayValue(style,precision,mantissa+"*10^"+str(exponent),mantissa+r"\times 10^{"+str(exponent)+"}")


def _evaluate(source,variables):
    from ctm_checkers.testing import expression
    normalized,tree = _source("placeholderValue="+source)
    if len(tree.body) != 1 or not isinstance(tree.body[0],ast.Assign):
        raise ValueError("placeholder needs one expression")
    node = tree.body[0].value
    calls = [item for item in ast.walk(node) if isinstance(item,ast.Call) and isinstance(item.func,ast.Name) and item.func.id in DISPLAY]
    names = dict(_helpers(),**variables)
    if calls:
        if len(calls) != 1 or calls[0] is not node or len(node.args) != 2 or node.keywords:
            raise ValueError("display calls must be top-level, with two arguments, and cannot enter arithmetic")
        return _display(node.func.id,*(expression(ast.unparse(arg),names) for arg in node.args))
    return expression(ast.unparse(node),names)


def _render(text,variables,progress):
    import sympy as sp
    from ctm_checkers.variants import encode
    _run("",variables,"",None,lambda *_:None)  # Reuse canonical catalogue/name validation.
    if set(variables) & DISPLAY:
        raise ValueError("variable names collide with display functions")
    output,canonical,resolutions,segments,segment = [],[],[],[],None
    for token in _scan(text):
        if isinstance(token,str):
            output.append(token); canonical.append(token)
            if segment is not None: segment.append(token)
            continue
        kind = token["kind"]
        if kind in ("math-open","math-close"):
            output.append(token["text"]); canonical.append(token["text"])
            if kind == "math-open":
                segment = []
            else:
                segments.append({"span":token["span"],"input":"".join(segment)})
                segment = None
            continue
        progress(len(resolutions),token["span"])
        try:
            value = _evaluate(token["expression"],variables)
            if isinstance(value,DisplayValue):
                raw,latex = value.text,value.latex
                wire = {"display":dict(style=value.style,precision=value.precision,text=raw,latex=latex)}
            else:
                _exact(value,matrix=kind == "latex")
                # A matrix has LaTeX display but deliberately no scalar student-input syntax.
                raw = None if isinstance(value,sp.MatrixBase) else _input(value)
                latex = sp.latex(value)
                wire = {"exact":encode(value)}
            rendered = raw if kind == "raw" else ("{"+latex+"}" if token["in_math"] else "$"+latex+"$")
            canonical_value = raw if raw is not None else json.dumps(wire["exact"],sort_keys=True,separators=(",",":"))
            canonical_rendered = canonical_value if kind == "raw" else ("{"+canonical_value+"}" if token["in_math"] else "$"+canonical_value+"$")
            output.append(rendered); canonical.append(canonical_rendered)
            if segment is not None:
                segment.append(canonical_rendered)
            elif kind == "latex":
                segments.append({"span":token["span"],"input":canonical_value})
            resolutions.append(dict(token,input=raw,latex=latex,value=wire))
        except Exception as error:
            raise GenerationError("line {line}, column {column}: {error}".format(error=error,**token["span"])) from error
    return {"text":"".join(output),"canonical_text":"".join(canonical),"resolutions":resolutions,"math_segments":segments}


def render(text,*,variables=None,file="<template>",label="<question>",placeholder_timeout=5.0,template_timeout=30.0):
    """Render supported text templates in one supervised native child; fail atomically."""
    from ctm_checkers.variants import encode,decode
    where = "{}: {}: ".format(file,label)
    for timeout in (placeholder_timeout,template_timeout):
        if isinstance(timeout,bool) or not isinstance(timeout,(int,float)) or not math.isfinite(timeout) or timeout <= 0:
            raise GenerationError(where+"timeouts must be positive finite seconds")
    try:
        if variables is not None and not isinstance(variables,dict):
            raise GenerationError("placeholder variables must be a mapping")
        tokens = _scan(text)
        expected = [token for token in tokens if isinstance(token,dict) and token["kind"] in ("raw","latex")]
        segment_spans = [token["span"] for token in tokens if isinstance(token,dict)
            and (token["kind"] == "math-open" or token["kind"] == "latex" and not token["in_math"])]
        import ctm_checkers,ctm_variants,sympy,mpmath
        roots = sorted({str(Path(package.__file__).resolve().parents[1]) for package in (ctm_checkers,ctm_variants,sympy,mpmath)})
        request = json.dumps({"text":text,"variables":encode({} if variables is None else variables),"import_roots":roots},ensure_ascii=True).encode("utf-8")
        if len(request) > MAX_IPC:
            raise GenerationError("template request exceeds byte limit")
    except Exception as error:
        raise GenerationError(where+str(error)) from error
    messages,stopped = queue.Queue(maxsize=1),threading.Event()
    with tempfile.TemporaryDirectory(prefix="ctm-placeholders-") as temporary:
        request_path = Path(temporary)/"request.json"
        request_path.write_bytes(request)
        environment = dict(os.environ)
        environment.pop("PYTHONPATH",None)
        started = current_started = time.monotonic()
        process = subprocess.Popen([sys.executable,"-I",str(Path(__file__).resolve()),str(request_path)],
            stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env=environment,cwd=temporary)
        reader = threading.Thread(target=_read_lines,args=(process.stdout,messages,stopped),name="ctm-placeholder-reader",daemon=True)
        reader.start()
        index,span = 0,{"line":1,"column":1}
        try:
            while True:
                deadline = min(started+template_timeout,current_started+placeholder_timeout)
                remaining = deadline-time.monotonic()
                if remaining <= 0: raise GenerationError("template time budget exceeded")
                try: message = messages.get(timeout=remaining)
                except queue.Empty: raise GenerationError("template time budget exceeded")
                if time.monotonic() > deadline: raise GenerationError("template time budget exceeded")
                if not isinstance(message,dict): raise GenerationError("worker exited without a result")
                if set(message) == {"placeholder","span"}:
                    if (index >= len(expected) or type(message["placeholder"]) is not int or message["placeholder"] != index
                            or not isinstance(message["span"],dict)
                            or any(type(value) is not int for value in message["span"].values())
                            or message["span"] != expected[index]["span"]):
                        raise GenerationError("unexpected placeholder boundary")
                    span = message["span"]
                    if index: current_started = time.monotonic()
                    index += 1
                elif set(message) == {"result"} and index == len(expected):
                    result = message["result"]
                    if (not isinstance(result,dict) or set(result) != {"text","canonical_text","resolutions","math_segments"}
                            or not all(isinstance(result[key],str) for key in ("text","canonical_text"))
                            or not isinstance(result["resolutions"],list) or len(result["resolutions"]) != len(expected)
                            or not isinstance(result["math_segments"],list) or len(result["math_segments"]) != len(segment_spans)):
                        raise GenerationError("invalid template result shape")
                    for item,wanted in zip(result["resolutions"],expected):
                        if (not isinstance(item,dict) or set(item) != set(wanted)|{"input","latex","value"}
                                or any(item.get(key) != wanted[key] for key in wanted)
                                or type(item["in_math"]) is not bool or not isinstance(item["span"],dict)
                                or any(type(value) is not int for value in item["span"].values())
                                or not isinstance(item["latex"],str) or item["input"] is not None and not isinstance(item["input"],str)):
                            raise GenerationError("invalid template resolution")
                        wire = item["value"]
                        if set(wire) == {"exact"}:
                            value = decode(wire["exact"])
                            # Semantic exactness/printing was proved under child deadlines.
                            # Keep parent work to the existing bounded codec and type checks.
                            if not isinstance(value,(sympy.Expr,sympy.MatrixBase)) or item["kind"] == "raw" and isinstance(value,sympy.MatrixBase):
                                raise GenerationError("invalid exact template result type")
                            item["value"] = value
                        elif set(wire) == {"display"}:
                            display = wire["display"]
                            if (not isinstance(display,dict) or set(display) != {"style","precision","text","latex"}
                                    or display["style"] not in DISPLAY or type(display["precision"]) is not int
                                    or not (0 if display["style"] == "dispdp" else 1) <= display["precision"] <= MAX_PRECISION
                                    or not isinstance(display["text"],str) or not isinstance(display["latex"],str)):
                                raise GenerationError("invalid display result")
                            item["value"] = DisplayValue(**wire["display"])
                        else: raise GenerationError("invalid template value")
                    for item,wanted_span in zip(result["math_segments"],segment_spans):
                        if (not isinstance(item,dict) or set(item) != {"span","input"} or not isinstance(item["input"],str)
                                or not isinstance(item["span"],dict) or set(item["span"]) != {"start","end","line","column"}
                                or any(type(value) is not int for value in item["span"].values())
                                or item["span"] != wanted_span):
                            raise GenerationError("invalid canonical math segment")
                    return result
                elif set(message) == {"error"} and isinstance(message["error"],str):
                    raise GenerationError(message["error"])
                else: raise GenerationError(message.get("protocol_error","unexpected worker protocol"))
        except Exception as error:
            detail = str(error)
            if not detail.startswith("line "):
                detail = "line {line}, column {column}: {error}".format(error=detail,**span)
            raise GenerationError(where+detail) from error
        finally:
            stopped.set()
            if process.poll() is None: process.kill()
            process.wait()
            reader.join(timeout=2)
            if reader.is_alive(): raise GenerationError(where+"worker reader failed to terminate")


def _worker(request_path):
    def emit(message):
        data = json.dumps(message,ensure_ascii=True)
        if len(data.encode("utf-8")) > MAX_IPC-1: raise GenerationError("template output exceeds byte limit")
        print(data,flush=True)
    try:
        with open(request_path,"rb") as stream: request = stream.read(MAX_IPC+1)
        if len(request) > MAX_IPC: raise GenerationError("template request exceeds byte limit")
        request = json.loads(request)
        sys.path[:0] = request["import_roots"]
        from ctm_checkers.variants import decode
        result = _render(request["text"],decode(request["variables"]),lambda index,span:emit({"placeholder":index,"span":span}))
        emit({"result":result})
    except Exception as error:
        emit({"error":str(error)[:4096]})


if __name__ == "__main__":
    _worker(sys.argv[1])
