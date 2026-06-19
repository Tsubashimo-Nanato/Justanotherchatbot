import asyncio

from local_qq_agent.tools import MathTool


def test_math_tool_evaluates_arithmetic_and_cleans_temp_script(tmp_path):
    temp_dir = tmp_path / "temp"
    tool = MathTool(temp_dir=temp_dir)

    result = asyncio.run(tool.answer_context("计算 2 + 3 * 4"))

    assert result.used
    assert "14" in result.result_text
    assert result.temp_script_deleted
    assert list(temp_dir.glob("math_eval_*.py")) == []


def test_math_tool_strips_debug_suffix_commands(tmp_path):
    tool = MathTool(temp_dir=tmp_path / "temp")

    result = asyncio.run(tool.answer_context("计算 2 + 3 * 4 .enforce .detail"))

    assert "14" in result.result_text
    assert result.query == "计算 2 + 3 * 4"


def test_math_tool_describes_sqrt_domain_when_value_is_underdetermined(tmp_path):
    tool = MathTool(temp_dir=tmp_path / "temp")

    result = asyncio.run(tool.answer_context("计算 x, y=sqrt(3-x)"))

    assert result.used
    assert "y = sqrt(3-x)" in result.result_text
    assert "x <= 3" in result.result_text
    assert "no single numeric value" in result.result_text
