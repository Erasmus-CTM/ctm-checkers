"""assess_basis (moved from math-exercise's tests/basis-assessment.test.mjs,
which ran the same assertions on the library decoded from math-exercise.js)."""
from sympy import Matrix

from ctm_checkers.core.result import normalize_result
from ctm_checkers.matrix import assess_basis


def col_result(matrix, dimension, belongs=lambda vector: True):
    return assess_basis(matrix, axis="columns", target_dimension=dimension,
                        belongs=belongs, name="B", space_name="test space")


def test_basis_assessment_is_symmetric_supports_rows_and_handles_empty_bases():
    dependent_columns = [Matrix([1, 0]), Matrix([0, 1]), Matrix([1, 1])]
    for order in ((0, 1, 2), (2, 0, 1), (1, 2, 0)):
        result = col_result(Matrix.hstack(*(dependent_columns[i] for i in order)), 2)
        assert abs(result["score"] - 2/3) < 1e-12
        assert result["show_score"] is False
        assert not any(character.isdigit() for character in result["feedback"])
        assert result["assessment"]["B"]["columns"] == ["dependent"] * 3

    incomplete = col_result(Matrix([[1], [0]]), 2)
    assert incomplete["score"] == 0.5
    assert incomplete["show_score"] is False
    assert not any(character.isdigit() for character in incomplete["feedback"])
    assert incomplete["assessment"]["B"]["columns"] == ["correct"]

    mixed = col_result(Matrix.eye(3), 2, lambda vector: vector[2, 0] == 0)
    assert abs(mixed["score"] - 2/3) < 1e-12
    assert mixed["show_score"] is False
    assert not any(character.isdigit() for character in mixed["feedback"])
    assert mixed["assessment"]["B"]["columns"] == ["correct", "correct", "incorrect"]

    rows = assess_basis(Matrix([[1, 0], [0, 1], [1, 1]]), axis="rows",
                        target_dimension=2, belongs=lambda vector: True,
                        name="R", space_name="test row space")
    assert rows["assessment"]["R"]["rows"] == ["dependent"] * 3

    empty_nontrivial = col_result(Matrix(0, 0, []), 2)
    assert empty_nontrivial["score"] == 0
    assert empty_nontrivial["show_score"] is False
    assert empty_nontrivial["assessment"]["B"]["columns"] == []

    empty_trivial = col_result(Matrix(0, 0, []), 0)
    assert empty_trivial["score"] == 1
    assert empty_trivial["show_score"] is False
    assert empty_trivial["assessment"]["B"]["columns"] == []

    normalized = normalize_result({"score": 0.5, "show_score": False})
    assert normalized["status"] == "partial"
    assert normalized["show_score"] is False
