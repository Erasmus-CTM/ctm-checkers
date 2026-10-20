<?php
// Native STACK's validation of student input, for tools/stack_native/check_validation.py.
// Part of ctm-checkers, AGPL-3.0-or-later; it runs STACK's own PHP code (GPL-3.0-or-later)
// from a STACK checkout, with the Moodle emulation of STACK's API (api/emulation).
//
// Usage (the driver writes config.php one folder above the working directory, as the
// emulation requires it): php validation.php STACK_SOURCE < cases.json > results.json
//
// cases.json: [{"raw", "forbiddenkeys", "insertstars", "forbidwords", "forbidfloat", "type"}, ...]
// For each case, what STACK's input validation does with the student's string
// (stack/input/inputbase.class.php validate_contents_filters and validate_contents):
// the question's security with the names its question variables write as forbidden keys
// (question.php:430-442), the input's forbidden words, and the parser filters that the
// input's options select. The result: valid, the errors (STACK's English strings) and
// the answer notes.

$stack = rtrim($argv[1], '/');
require_once('../config.php');
require_once($stack . '/api/emulation/MoodleEmulation.php');
require_once($stack . '/stack/cas/ast.container.class.php');
require_once($stack . '/stack/cas/cassecurity.class.php');
require_once($stack . '/stack/cas/caserror.class.php');

$cases = json_decode(file_get_contents('php://stdin'), true);
$results = [];
foreach ($cases as $case) {
    $security = new stack_cas_security(false, '', implode(',', $case['forbidwords']), $case['forbiddenkeys']);
    // validate_contents_filters with grammarAutofixes = insertstars (0 or 1).
    $filters = [];
    if ($case['forbidfloat']) {
        $filters[] = '101_no_floats';
    }
    $filters[] = '150_replace_unicode_letters';
    if ($case['type'] === 'numerical') {
        $filters[] = '210_x_used_as_multiplication';
    }
    $filters[] = '402_split_prefix_from_common_function_name';
    $filters[] = '403_split_at_number_letter_boundary';
    $filters[] = '406_split_implied_variable_names';
    $filters[] = '502_replace_pm';
    $filters[] = '504_insert_tuples_for_groups';
    $filters[] = '505_no_evaluation_groups';
    $filters[] = '997_string_security';
    if ((int) $case['insertstars'] === 0) {
        $filters[] = '999_strict';
    } else {
        $filters[] = '990_no_fixing_spaces';
    }
    $container = stack_ast_container::make_from_student_source($case['raw'], '', $security, $filters);
    $results[] = ['valid' => $container->get_valid(), 'errors' => $container->get_errors(),
                  'notes' => $container->get_answernote()];
}
echo json_encode($results, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES), "\n";
