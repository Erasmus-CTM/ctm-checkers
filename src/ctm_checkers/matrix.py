"""Basis assessment for matrix answers (math-exercise 0.10.0's assess_basis,
moved verbatim; stack-sympy's basis_helper.py holds the same function and
moves here with its engine)."""
from sympy import Matrix, zeros


def assess_basis(matrix, *, axis, target_dimension, belongs, name, space_name="space"):
    """Assess a row- or column-basis submission without privileging vector order.

    ``belongs(vector)`` decides only whether a nonzero vector belongs to the
    target space.  This helper owns rank, dependence, scoring, assessment
    colors, and standard feedback so individual checkers do not duplicate them.
    """
    if axis not in ("rows", "columns"):
        raise ValueError("Basis assessment axis must be rows or columns")
    target_dimension = int(target_dimension)
    if target_dimension < 0:
        raise ValueError("Basis target dimension cannot be negative")
    if not callable(belongs):
        raise TypeError("Basis membership test must be callable")

    count = matrix.rows if axis == "rows" else matrix.cols
    singular = "row" if axis == "rows" else "column"
    vectors = [matrix[i, :] for i in range(count)] if axis == "rows" else [matrix[:, i] for i in range(count)]

    if target_dimension == 0:
        statuses = ["incorrect"] * count
        return {
            "score": 1.0 if count == 0 else 0.0,
            "show_score": False,
            "feedback": "" if count == 0 else f"The {space_name} is trivial, so its basis is empty. Remove every {singular}.",
            "assessment": {name: {axis: statuses}},
        }

    locally_valid = []
    valid_vectors = []
    for vector in vectors:
        zero = vector == zeros(*vector.shape)
        valid = (not zero) and bool(belongs(vector))
        locally_valid.append(valid)
        if valid:
            valid_vectors.append(vector)

    if valid_vectors:
        family = Matrix.vstack(*valid_vectors) if axis == "rows" else Matrix.hstack(*valid_vectors)
        rank = int(family.rank())
    else:
        rank = 0
    valid_count = len(valid_vectors)
    dependent = rank < valid_count
    statuses = [
        ("dependent" if dependent else "correct") if valid else "incorrect"
        for valid in locally_valid
    ]

    if count == 0:
        score = 0.0
    else:
        coverage = min(rank, target_dimension) / target_dimension
        validity = valid_count / count
        independence = rank / valid_count if valid_count else 0.0
        score = float(coverage * validity * independence)

    invalid_count = count - valid_count
    plural = singular + "s"
    if score >= 1.0 - 1e-9:
        feedback = ""
    elif count == 0:
        feedback = f"Add one or more basis {plural} for the {space_name}."
    elif invalid_count and dependent:
        feedback = (f"The red {plural} are zero or outside the {space_name}. "
                    f"The yellow {plural} belong to the {space_name}, but together they are linearly dependent. "
                    f"Remove or replace the red {plural}, choose an independent subset of the yellow {plural}, "
                    f"and check that the result spans the whole {space_name}.")
    elif invalid_count:
        feedback = f"Remove or replace the red {plural}; each is zero or outside the {space_name}."
        if rank < target_dimension:
            feedback += f" Then add independent {plural} until the family spans the whole {space_name}."
    elif dependent and rank == target_dimension:
        feedback = (f"Every yellow {singular} belongs to the {space_name}, but the family is linearly dependent. "
                    f"Remove one or more yellow {plural} until an independent basis remains.")
    elif dependent:
        feedback = (f"Every yellow {singular} belongs to the {space_name}, but the family is linearly dependent. "
                    f"Choose an independent subset, then add independent {plural} until it spans the whole {space_name}.")
    else:
        feedback = (f"The green {plural} are valid and independent. "
                    f"Add more independent {plural} until they span the whole {space_name}.")

    return {"score": score, "show_score": False, "feedback": feedback, "assessment": {name: {axis: statuses}}}


# STACK library predicates. Scoring remains with the response tree.
import sympy as sp


def rational_matrix(value):
    if not isinstance(value, sp.MatrixBase):
        raise ValueError("Enter a matrix.")
    if any(entry.is_Rational is not True for entry in value):
        raise ValueError("Use real integers or exact fractions in every cell.")
    if any(max(abs(int(entry.p)).bit_length(), int(entry.q).bit_length()) > 256
           for entry in value):
        raise ValueError("Matrix entries exceed the 256-bit rational bound.")
    return value


def basis(student, teacher, options):
    space = options.get("space")
    # An invalid reference is an author error; invalid student entries are input feedback.
    reference = rational_matrix(teacher)
    rank = reference.rank()
    axis = "rows" if space == "rowspace" else "columns"
    if space == "nullspace":
        dimension, ambient = reference.cols - rank, reference.cols
        belongs = lambda vector: reference * vector == sp.zeros(reference.rows, 1)
        space_name = "null space"
    elif space == "columnspace":
        dimension, ambient = rank, reference.rows
        belongs = lambda vector: reference.row_join(vector).rank() == rank
        space_name = "column space"
    elif space == "rowspace":
        dimension, ambient = rank, reference.cols
        belongs = lambda vector: reference.col_join(vector).rank() == rank
        space_name = "row space"
    else:
        raise ValueError("Choose a null, column or row space.")
    if not dimension:
        raise ValueError("The target space has an empty basis; empty matrix inputs are not yet supported.")
    try:
        submitted = rational_matrix(student)
    except ValueError as exc:
        return {"valid": False, "correct": False, "feedback": str(exc)}
    submitted_ambient = submitted.rows if axis == "columns" else submitted.cols
    result = assess_basis(submitted, axis=axis, target_dimension=int(dimension),
                          name="answer", space_name=space_name,
                          belongs=lambda vector: submitted_ambient == ambient and belongs(vector))
    statuses = result["assessment"]["answer"][axis]
    count = submitted.cols if axis == "columns" else submitted.rows
    return {"valid": True,
            "correct": count == dimension and all(status == "correct" for status in statuses),
            "feedback": result["feedback"], "assessment": {axis: statuses}}


def matrix_property(student, teacher, options):
    property_name = options.get("property")
    if property_name not in {"integer_entries", "determinant", "identity"}:
        raise ValueError("Choose integer_entries, determinant or identity.")
    if property_name == "determinant":
        if (not isinstance(teacher, sp.Rational)
                or max(abs(int(teacher.p)).bit_length(), int(teacher.q).bit_length()) > 256):
            raise ValueError("The expected determinant must be a bounded exact rational number.")
    elif teacher is not sp.true and teacher is not sp.false:
        raise ValueError("The expected property value must be true or false.")
    try:
        matrix = rational_matrix(student)
    except ValueError as exc:
        return {"valid": False, "correct": False, "feedback": str(exc)}
    if property_name == "determinant":
        if matrix.rows != matrix.cols:
            return {"valid": False, "correct": False, "feedback": "A determinant requires a square matrix."}
        actual = matrix.det()
    elif property_name == "integer_entries":
        actual = sp.true if all(entry.q == 1 for entry in matrix) else sp.false
    else:
        actual = sp.true if matrix.rows == matrix.cols and matrix == sp.eye(matrix.rows) else sp.false
    return {"valid": True, "correct": bool(actual == teacher)}


def hermitian(A):
    return A.rows == A.cols and A == A.H


def positive_definite(A):
    if A.rows != A.cols:
        return False
    # Re(z.H*A*z) equals z.H*H*z for real or complex matrices.
    H = (A + A.H) / 2
    return all(H[:k, :k].det() > 0 for k in range(1, H.rows + 1))


def check_property(ansm, expected, property_test, explanation):
    if any(part.is_Rational is not True
           for entry in ansm for part in entry.as_real_imag()):
        return {"valid": False, "correct": False,
                "feedback": "Use integers or exact fractions for the real and imaginary parts."}
    correct = bool(property_test(ansm)) == bool(expected)
    return {"valid": True, "correct": correct,
            "feedback": "" if correct else explanation}


def is_hermitian(ansm, expected, options):
    return check_property(ansm, expected, hermitian,
                          "The Hermitian-symmetry condition does not match the expected result.")


def is_positive_definite(ansm, expected, options):
    return check_property(ansm, expected, positive_definite,
                          "The positive-definiteness condition does not match the expected result.")


def is_hpd(ansm, expected, options):
    return check_property(ansm, expected,
                          lambda A: hermitian(A) and positive_definite(A),
                          "The Hermitian-positive-definiteness condition does not match the expected result.")
