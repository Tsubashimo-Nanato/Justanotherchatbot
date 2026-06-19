from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
import subprocess
import sys
import textwrap
import time
from uuid import uuid4

from local_qq_agent.paths import project_path


@dataclass(frozen=True)
class MathContext:
    used: bool
    query: str
    context: str
    result_text: str = ""
    latency_seconds: float = 0.0
    reason: str = ""
    error: str = ""
    temp_script_path: str = ""
    temp_script_deleted: bool = False
    details: dict = field(default_factory=dict)

    def to_metadata(self) -> dict:
        return {
            "math_used": self.used,
            "math_query": self.query,
            "math_result": self.result_text,
            "math_latency_seconds": self.latency_seconds,
            "math_reason": self.reason,
            "math_error": self.error,
            "math_temp_script_path": self.temp_script_path,
            "math_temp_script_deleted": self.temp_script_deleted,
            "math_details": self.details,
        }


class MathTool:
    def __init__(
        self,
        temp_dir: str | Path = "personality/nanato/workspace/temp",
        *,
        timeout_seconds: float = 6.0,
    ) -> None:
        self.temp_dir = project_path(temp_dir)
        self.timeout_seconds = timeout_seconds

    def should_calculate(self, message: str) -> bool:
        text = self._clean_query(message).casefold().strip()
        if not text:
            return False

        triggers = (
            "calculate",
            "compute",
            "solve",
            "evaluate",
            "equation",
            "math",
            "sqrt",
            "sin",
            "cos",
            "tan",
            "log",
            "计算",
            "算一下",
            "算下",
            "求解",
            "方程",
            "表达式",
            "开方",
            "平方根",
            "函数",
        )
        if any(trigger in text for trigger in triggers):
            return True

        has_operator = any(operator in text for operator in ("+", "-", "*", "/", "^", "=", "√"))
        has_digit = any(character.isdigit() for character in text)
        return has_operator and has_digit

    async def answer_context(self, message: str) -> MathContext:
        return self._run_script(self._clean_query(message))

    def _clean_query(self, message: str) -> str:
        text = message.strip()
        command_pattern = re.compile(r"\s+\.(?:enforce|detail|debug|ignore|think)(?:\s+[0-3])?\s*$", re.IGNORECASE)
        while command_pattern.search(text):
            text = command_pattern.sub("", text).strip()
        return text

    def _run_script(self, message: str) -> MathContext:
        started_at = time.perf_counter()
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        script_path = self.temp_dir / f"math_eval_{uuid4().hex}.py"
        script_path.write_text(_SCRIPT_TEMPLATE, encoding="utf-8")

        deleted = False
        timeout_error: subprocess.TimeoutExpired | None = None
        try:
            completed = subprocess.run(
                [sys.executable, str(script_path)],
                input=json.dumps({"query": message}, ensure_ascii=False),
                text=True,
                capture_output=True,
                timeout=self.timeout_seconds,
                check=False,
                encoding="utf-8",
            )
        except subprocess.TimeoutExpired as error:
            completed = None
            timeout_error = error
        finally:
            try:
                script_path.unlink(missing_ok=True)
                deleted = True
            except OSError:
                deleted = False

        if timeout_error is not None:
            return self._failure(
                message,
                script_path,
                started_at,
                f"math tool timed out after {self.timeout_seconds:g}s",
                deleted=deleted,
                details={"timeout_seconds": self.timeout_seconds, "stdout": timeout_error.stdout or ""},
            )

        latency = round(time.perf_counter() - started_at, 3)
        if completed.returncode != 0:
            return MathContext(
                used=True,
                query=message,
                context="",
                latency_seconds=latency,
                reason="script_failed",
                error=completed.stderr.strip() or f"exit code {completed.returncode}",
                temp_script_path=str(script_path),
                temp_script_deleted=deleted,
                details={"stdout": completed.stdout.strip()},
            )

        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            return MathContext(
                used=True,
                query=message,
                context="",
                latency_seconds=latency,
                reason="invalid_script_output",
                error=str(error),
                temp_script_path=str(script_path),
                temp_script_deleted=deleted,
                details={"stdout": completed.stdout.strip()},
            )

        result_text = str(payload.get("result_text", "")).strip()
        context = self._build_context(result_text, payload)
        return MathContext(
            used=True,
            query=message,
            context=context,
            result_text=result_text,
            latency_seconds=latency,
            reason=str(payload.get("reason", "calculated")),
            error=str(payload.get("error", "")),
            temp_script_path=str(script_path),
            temp_script_deleted=deleted,
            details=payload,
        )

    def _failure(
        self,
        message: str,
        script_path: Path,
        started_at: float,
        error: str,
        *,
        deleted: bool,
        details: dict,
    ) -> MathContext:
        return MathContext(
            used=True,
            query=message,
            context="",
            latency_seconds=round(time.perf_counter() - started_at, 3),
            reason="failed",
            error=error,
            temp_script_path=str(script_path),
            temp_script_deleted=deleted,
            details=details,
        )

    def _build_context(self, result_text: str, payload: dict) -> str:
        if not result_text:
            return ""

        lines = [
            "Math result from a local scratch calculation:",
            result_text,
        ]
        steps = payload.get("steps")
        if isinstance(steps, list) and steps:
            lines.append("Useful details:")
            lines.extend(f"- {step}" for step in steps[:5])
        return "\n".join(lines)


_SCRIPT_TEMPLATE = textwrap.dedent(
    r'''
    import ast
    import json
    import math
    import re
    import sys


    SAFE_NAMES = {
        "pi": math.pi,
        "e": math.e,
        "tau": math.tau,
    }
    SAFE_FUNCS = {
        "sqrt": math.sqrt,
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "log": math.log,
        "ln": math.log,
        "log10": math.log10,
        "exp": math.exp,
        "abs": abs,
        "round": round,
        "floor": math.floor,
        "ceil": math.ceil,
    }


    def main():
        request = json.loads(sys.stdin.read() or "{}")
        query = str(request.get("query", "")).strip()
        result = analyze(query)
        print(json.dumps(result, ensure_ascii=False))


    def analyze(query):
        text = normalize(query)
        assignments = parse_assignments(text)
        if assignments:
            return analyze_assignments(text, assignments)

        expression = expression_candidate(text)
        if not expression:
            return {
                "ok": False,
                "reason": "no_expression_found",
                "result_text": "I could not find a complete expression to calculate.",
                "steps": [],
            }

        try:
            value = safe_eval(expression, {})
        except Exception as error:
            return {
                "ok": False,
                "reason": "expression_not_evaluable",
                "result_text": f"The expression needs more information before it can be calculated: {error}",
                "expression": expression,
                "steps": [f"Parsed expression: {expression}"],
            }

        return {
            "ok": True,
            "reason": "numeric_expression",
            "result_text": f"{expression} = {format_number(value)}",
            "expression": expression,
            "value": value,
            "steps": [f"Parsed expression: {expression}", f"Evaluated value: {format_number(value)}"],
        }


    def normalize(query):
        replacements = {
            "，": ",",
            "；": ";",
            "：": ":",
            "（": "(",
            "）": ")",
            "×": "*",
            "÷": "/",
            "√": "sqrt",
            "^": "**",
        }
        text = query
        for old, new in replacements.items():
            text = text.replace(old, new)
        return text


    def parse_assignments(text):
        pattern = re.compile(r"\b([A-Za-z]\w*)\s*=\s*([^,;\n]+?)(?=\s+[A-Za-z]\w*\s*=|[,;\n]|$)")
        return [(match.group(1), match.group(2).strip()) for match in pattern.finditer(text)]


    def analyze_assignments(text, assignments):
        numeric_values = {}
        symbolic = []
        steps = []

        for name, expression in assignments:
            clean_expression = cleanup_expression(expression)
            try:
                value = safe_eval(clean_expression, numeric_values)
                numeric_values[name] = value
                steps.append(f"{name} = {format_number(value)}")
            except Exception:
                symbolic.append((name, clean_expression))
                steps.append(f"{name} is defined as {clean_expression}")

        if symbolic and numeric_values:
            evaluated = []
            for name, expression in symbolic:
                try:
                    value = safe_eval(expression, numeric_values)
                except Exception:
                    continue
                evaluated.append(f"{name} = {format_number(value)}")
            if evaluated:
                return {
                    "ok": True,
                    "reason": "substituted_expression",
                    "result_text": "; ".join(evaluated),
                    "steps": steps + evaluated,
                    "assignments": assignments,
                }

        if symbolic:
            pieces = []
            for name, expression in symbolic:
                domain = sqrt_domain(expression)
                if domain:
                    pieces.append(f"{name} = {pretty(expression)}, real-valued domain: {domain}")
                    steps.append(f"sqrt condition: {domain}")
                else:
                    pieces.append(f"{name} = {pretty(expression)}")

            pieces.append("There is no single numeric value unless another condition or variable value is given.")
            return {
                "ok": True,
                "reason": "symbolic_definition",
                "result_text": "; ".join(pieces),
                "steps": steps,
                "assignments": assignments,
            }

        if numeric_values:
            result_text = "; ".join(f"{name} = {format_number(value)}" for name, value in numeric_values.items())
            return {
                "ok": True,
                "reason": "numeric_assignments",
                "result_text": result_text,
                "steps": steps,
                "assignments": assignments,
            }

        return {
            "ok": False,
            "reason": "assignment_not_evaluable",
            "result_text": "I found an equation-like expression, but it is missing enough information to solve a value.",
            "steps": steps,
            "assignments": assignments,
        }


    def expression_candidate(text):
        lowered = text.casefold()
        for marker in ("calculate", "compute", "evaluate", "计算", "算一下", "算下"):
            index = lowered.find(marker.casefold())
            if index >= 0:
                candidate = text[index + len(marker):].strip(" :，,")
                return cleanup_expression(candidate)

        match = re.search(r"[-+*/().\d\s*]+", text)
        if match:
            return cleanup_expression(match.group(0))
        return ""


    def cleanup_expression(expression):
        expression = expression.strip()
        expression = re.sub(r"^(x|y|z)\s*,\s*", "", expression, flags=re.IGNORECASE)
        expression = re.sub(r"\s+", " ", expression)
        return expression.strip()


    def safe_eval(expression, variables):
        tree = ast.parse(expression, mode="eval")
        return eval_node(tree.body, variables)


    def eval_node(node, variables):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.Name):
            if node.id in variables:
                return variables[node.id]
            if node.id in SAFE_NAMES:
                return SAFE_NAMES[node.id]
            raise ValueError(f"unknown variable '{node.id}'")
        if isinstance(node, ast.UnaryOp):
            value = eval_node(node.operand, variables)
            if isinstance(node.op, ast.UAdd):
                return +value
            if isinstance(node.op, ast.USub):
                return -value
        if isinstance(node, ast.BinOp):
            left = eval_node(node.left, variables)
            right = eval_node(node.right, variables)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
            if isinstance(node.op, ast.Pow):
                return left ** right
            if isinstance(node.op, ast.Mod):
                return left % right
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            function = SAFE_FUNCS.get(node.func.id)
            if function is None:
                raise ValueError(f"function '{node.func.id}' is not allowed")
            args = [eval_node(arg, variables) for arg in node.args]
            return function(*args)
        raise ValueError("unsupported expression")


    def sqrt_domain(expression):
        matches = re.findall(r"sqrt\s*\(([^()]*)\)", expression)
        if not matches:
            return ""

        inner = matches[0].replace(" ", "")
        match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)-x", inner)
        if match:
            return f"x <= {match.group(1)}"
        match = re.fullmatch(r"x-([0-9]+(?:\.[0-9]+)?)", inner)
        if match:
            return f"x >= {match.group(1)}"
        return f"{pretty(inner)} >= 0"


    def pretty(expression):
        return expression.replace("**", "^")


    def format_number(value):
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        if isinstance(value, float):
            return f"{value:.12g}"
        return str(value)


    if __name__ == "__main__":
        main()
    '''
).lstrip()
