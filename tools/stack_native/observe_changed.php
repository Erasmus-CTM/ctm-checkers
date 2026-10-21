<?php
// Part of ctm-checkers, AGPL-3.0-or-later.
// Observe the upstream PHP question/answer-test implementations. No CTM code is loaded.
// The Python driver supplies an isolated config.php above the working directory.
$stack = rtrim($argv[1], '/');
require_once('../config.php');
require_once($stack . '/api/emulation/MoodleEmulation.php');
require_once($stack . '/api/util/StackQuestionLoader.php');
require_once($stack . '/stack/cas/installhelper.class.php');
require_once($stack . '/stack/answertest/controller.class.php');
require_once($stack . '/stack/questiontestresult.php');
require_once($stack . '/stack/cas/casstring.units.class.php');
file_put_contents(stack_cas_configuration::maximalocal_location(),
    stack_cas_configuration::generate_maximalocal_contents());
current_language('en');

function observe_answer($question, $answers) {
    $inputs = [];
    foreach ($question->inputs as $name => $input) {
        $state = $question->get_input_state($name, $answers);
        $inputs[$name] = ['status' => $state->status, 'errors' => $state->errors,
            'note' => $state->note, 'interpreted' => $state->contentsmodified,
            'display' => $state->contentsdisplayed];
    }
    $prts = [];
    $total = 0;
    foreach ($question->get_parts_and_weights() as $name => $weight) {
        $result = $question->get_prt_result($name, $answers, true);
        $score = $result->get_score();
        $prts[$name] = ['score' => $score, 'penalty' => $result->get_penalty(),
            'notes' => $result->get_answernotes(), 'branch_notes' => $result->get_answernotes(false),
            'errors' => $result->get_errors(), 'feedback' => $result->get_feedback()];
        $total += $weight * $score;
    }
    return ['inputs' => $inputs, 'prts' => $prts, 'score' => $total,
        'runtimeerrors' => $question->runtimeerrors];
}

function observe($case) {
    if ($case['call'] === 'stack.answer_test') {
        $value = $case['input'];
        // Same construction as upstream tests/answertest_general_cas_test.php.
        // Keeping the source AST preserves the literal used by NumDecPlaces.
        $sa = stack_ast_container::make_from_teacher_source($value['student'], '', new stack_cas_security());
        $ta = stack_ast_container::make_from_teacher_source($value['teacher'], '', new stack_cas_security());
        $op = stack_ast_container::make_from_teacher_source($value['options'] ?: 'null', '', new stack_cas_security());
        $test = new stack_ans_test_controller($value['test'], $sa, $ta, $op);
        $verdict = $test->do_test();
        return ['verdict' => $verdict, 'valid' => $test->get_at_valid(), 'score' => $test->get_at_mark(),
            'note' => $test->get_at_answernote(), 'feedback' => $test->get_at_feedback(),
            'errors' => $test->get_at_errors()];
    }
    $loaded = \api\util\StackQuestionLoader::loadxml($case['xml'], true);
    $question = $loaded['question'];
    // Replay the golden's actual seed, even when it is not a deployed API variant.
    $question->seed = $case['input']['seed'] ?? 1;
    $question->initialise_question_from_seed();
    $question->castextprocessor = new castext2_qa_processor(new stack_outofcontext_process());
    if (!empty($question->runtimeerrors)) {
        return ['runtimeerrors' => $question->runtimeerrors];
    }
    if ($case['call'] === 'stack.answer') {
        return observe_answer($question, $case['input']['answers']);
    }
    if ($case['call'] === 'stack.tests') {
        $out = [];
        foreach ($loaded['testcases'] as $test) {
            $response = stack_question_test::compute_response($question, $test->inputs);
            $result = $test->process_results($question, $response);
            $out[] = ['testcase' => $test->testcase, 'response' => $response,
                'result' => $result->passed_with_reasons(), 'actual' => observe_answer($question, $response)];
        }
        return ['tests' => $out, 'runtimeerrors' => $question->runtimeerrors];
    }
    // Imports and variants have different representations in the two engines;
    // expose native loading/initialisation rather than comparing CTM JSON/HTML.
    return ['initialised' => true, 'name' => $question->name, 'seed' => $question->seed,
        'runtimeerrors' => $question->runtimeerrors];
}

// JSON lines preserve observations already completed if a later case fails.
while (($line = fgets(STDIN)) !== false) {
    $case = json_decode($line, true, 512, JSON_THROW_ON_ERROR);
    try {
        $result = ['observation' => observe($case)];
    } catch (Throwable $error) {
        // A native exception is evidence, never an agreement or a passing verdict.
        $result = ['exception' => get_class($error) . ': ' . $error->getMessage()];
        $result['harness_error'] = $error instanceof Error;
    }
    $result['key'] = $case['key'];
    echo json_encode($result, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR), "\n";
    flush();
}
