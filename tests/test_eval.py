from eval.dataset import is_test_split_frozen, load_split, parse_line
from eval.metrics import evaluate, merge
from pii_shield import PIIScrubber


def test_markup_offsets():
    ex = parse_line("Call {{PHONE|(555) 123-4567}} or {{EMAIL|a@example.com}}.\\nBye")
    assert ex.text == "Call (555) 123-4567 or a@example.com.\nBye"
    for span in ex.gold:
        assert ex.text[span.start : span.end] == span.value


def test_every_split_parses_and_offsets_are_exact():
    for split in ("dev", "test", "limits"):
        examples = load_split(split)
        assert examples
        for ex in examples:
            for span in ex.gold:
                assert ex.text[span.start : span.end] == span.value


def test_test_split_is_frozen():
    assert is_test_split_frozen()


def test_merge():
    assert merge([(5, 8), (0, 3), (2, 4), (8, 9)]) == [(0, 4), (5, 9)]


class Fixed:
    def __init__(self, spans):
        self.spans = spans

    def detect(self, text):
        return [{"start": s, "end": e} for s, e in self.spans]


def test_partial_coverage_is_a_miss():
    ex = [parse_line("x {{PHONE|+44 20 7946 0958}} y")]
    report = evaluate(Fixed([(2, 5)]), ex, "t")  # only "+44" hidden
    assert report.recall == 0 and report.totals()["partial"] == 1


def test_false_positive_lowers_precision_and_clean_rate():
    ex = [parse_line("nothing here 12 Main"), parse_line("{{SSN|219-09-9999}}")]
    report = evaluate(Fixed([(0, 4)]), ex, "t")
    assert report.clean_rate == 0
    assert report.precision == 0.5  # one hit on the SSN line, one false alarm


def test_v2_beats_baselines_on_test_split():
    from baselines.pathreview_original import PIIScrubber as Original
    from baselines.pathreview_pr98 import PIIScrubber as PR98

    test = load_split("test")
    scores = {name: evaluate(cls(), test, name).f1 for name, cls in [("o", Original), ("p", PR98), ("v", PIIScrubber)]}
    assert scores["v"] > scores["p"] > scores["o"]
