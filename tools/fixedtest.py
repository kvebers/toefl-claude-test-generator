"""Offline regressions for fixed paper-test modules and raw-only score reporting."""
from __future__ import annotations

import copy
import unittest

from common import LIBRARY_DIR, iter_tasks, load_json, sanitize, score_task
from report import env
from score import compute, objective_results
from validate import validate


class FixedPracticeTests(unittest.TestCase):
    def setUp(self):
        self.test = copy.deepcopy(load_json(LIBRARY_DIR / 'sample-mini' / 'test.json'))
        self.test['score_reporting'] = 'raw_only'
        for sec in self.test['sections']:
            if 'm2_easy' in sec['modules']:
                sec['modules']['m2'] = sec['modules'].pop('m2_hard')
                sec['modules'].pop('m2_easy')

    def test_fixed_modules_survive_empty_routes_and_validate(self):
        self.assertEqual(validate(self.test)[0], [])
        selected = list(iter_tasks(self.test, {}))
        self.assertTrue(any(s == 'reading' and m == 'm2' for s, m, _ in selected))
        self.assertTrue(any(s == 'listening' and m == 'm2' for s, m, _ in selected))
        self.assertEqual(len(selected), len(list(iter_tasks(self.test))))

    def test_fixed_modules_cannot_claim_adaptive_scaled_scores(self):
        self.test.pop('score_reporting')
        self.assertTrue(any('raw_only' in e for e in validate(self.test)[0]))

    def test_mixed_fixed_and_adaptive_modules_rejected(self):
        mods = self.test['sections'][0]['modules']
        mods['m2_easy'] = copy.deepcopy(mods['m2'])
        mods['m2_hard'] = copy.deepcopy(mods['m2'])
        self.assertTrue(any('cannot be combined' in e for e in validate(self.test)[0]))

    def test_all_modules_scored_without_manufactured_bands(self):
        responses = {}
        for _, _, task in iter_tasks(self.test):
            if task.get('questions') and 'answer' in task['questions'][0]:
                responses[task['id']] = {'answers': {q['id']: q['answer'] for q in task['questions']}}
        objective = objective_results(self.test, responses, {}, {})
        score = compute(self.test, {}, objective, None)
        for sid in ('reading', 'listening'):
            items = [i for i in objective['items'] if i['section'] == sid]
            self.assertGreater(len(items), 0)
            # Word-completion responses are blank; the denominator must still include both modules.
            self.assertEqual(score['sections'][sid]['raw'].split('/')[1], str(len(items)))
        self.assertIsNone(score['summary']['est_total_120'])
        self.assertIsNone(score['summary']['overall_band'])
        self.assertTrue(all(s['band'] is None and 'est_30' not in s for s in score['sections'].values()))
        self.assertEqual(score['summary']['score_reporting'], 'raw_only')
        self.assertNotIn('±0.5', score['summary']['estimate_note'])

    def test_fixed_middle_sentence_text_and_hidden_keys(self):
        task = {'id': 'fixed-sentence', 'type': 'build_sentence', 'items': [{
            'id': 'b1', 'prompt': 'Are your travel plans ready?', 'end': '?',
            'fixed': {'2': 'book your'}, 'chunks': ['yet', 'flight', 'you', 'did'],
            'answer': ['did', 'you', 'flight', 'yet'], 'skill': 'grammar.questions'}]}
        result = score_task('writing', 'm1', task, {'items': {'b1': task['items'][0]['answer']}})[0]
        self.assertTrue(result['correct'])
        self.assertEqual(result['given'], 'did you book your flight yet ?')
        self.test['sections'][2]['modules']['m1']['tasks'][0] = task
        clean = sanitize(self.test)['sections'][2]['modules']['m1']['tasks'][0]['items'][0]
        self.assertNotIn('answer', clean)
        self.assertEqual(clean['fixed'], {'2': 'book your'})

    def test_raw_report_does_not_request_all_four_sections_or_show_scaled_totals(self):
        objective = objective_results(self.test, {}, {}, {})
        score = compute(self.test, {}, objective, None)
        html = env().get_template('report.html.j2').render(
            test=self.test, attempt={'id': 'synthetic', 'started': '2026-11-08T12:00:00'},
            score=score, objective=objective, tasks={}, grading={}, meta={}, levels={})
        self.assertIn('Practice results', html)
        self.assertNotIn('needs all 4 sections', html)
        self.assertNotIn('Overall band', html)
        self.assertNotIn('How the band was calculated', html)


if __name__ == '__main__':
    unittest.main()
