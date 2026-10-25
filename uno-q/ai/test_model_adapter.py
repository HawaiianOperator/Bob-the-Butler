import unittest
try:
    from .model_adapter import ModelOutputError, parse_point, parse_search
except ImportError:
    from model_adapter import ModelOutputError, parse_point, parse_search


class ModelOutputTests(unittest.TestCase):
    def test_bounded_points(self):
        point = parse_point('{"x":0.25,"y":0.5}')
        self.assertEqual((point.x, point.y), (0.25, 0.5))

    def test_malformed_or_executable_outputs_do_not_become_targets(self):
        for text in ['not json', '{"x":0.5', '[]', '{"x":true,"y":0.5}',
                     '{"x":NaN,"y":0.5}', '{"x":1.01,"y":0.5}',
                     '{"x":0.5,"y":0.5,"command":"run something"}']:
            with self.subTest(text=text), self.assertRaises(ModelOutputError):
                parse_point(text)

    def test_chat_query_keeps_text_and_rejects_extra_actions(self):
        self.assertEqual(parse_search('{"query":" NVIDIA stock "}'), 'NVIDIA stock')
        for text in ['{"query":""}', '{"query":"NVIDIA stock","click":true}', '{"query":4}']:
            with self.assertRaises(ModelOutputError):
                parse_search(text)


if __name__ == '__main__':
    unittest.main()
