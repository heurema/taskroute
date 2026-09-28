import copy
import unittest

from task_batches import plan_batches


def t(name, deps=None, priority=0):
    return dict(id=name, depends_on=[] if deps is None else deps, priority=priority)


class FrozenTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(plan_batches([], []), [])

    def test_single(self):
        self.assertEqual(plan_batches([t("a")], []), [["a"]])

    def test_batch_priority(self):
        self.assertEqual(
            plan_batches([t("a", priority=-2), t("b", priority=3), t("c", priority=1)], []),
            [["b", "c", "a"]],
        )

    def test_stable_ties(self):
        self.assertEqual(plan_batches([t("z"), t("a"), t("m")], []), [["z", "a", "m"]])

    def test_batch_boundary(self):
        self.assertEqual(plan_batches([t("a"), t("b", ["a"], 99), t("c")], []), [["a", "c"], ["b"]])

    def test_diamond(self):
        self.assertEqual(
            plan_batches([t("d", ["b", "c"]), t("c", ["a"]), t("a"), t("b", ["a"])], []),
            [["a"], ["c", "b"], ["d"]],
        )

    def test_completed(self):
        self.assertEqual(plan_batches([t("a"), t("b", ["a"])], ["a"]), [["b"]])

    def test_external_completed(self):
        self.assertEqual(plan_batches([t("a", ["external"])], ["external", "external"]), [["a"]])

    def test_duplicate_dependencies(self):
        self.assertEqual(plan_batches([t("a"), t("b", ["a", "a"])], []), [["a"], ["b"]])

    def test_all_completed_cycle(self):
        self.assertEqual(plan_batches([t("a", ["b"]), t("b", ["a"])], ["a", "b"]), [])

    def test_completed_breaks_cycle(self):
        self.assertEqual(plan_batches([t("a", ["b"]), t("b", ["a"])], ["a"]), [["b"]])

    def test_missing_even_completed(self):
        with self.assertRaisesRegex(ValueError, "^MISSING_DEPENDENCY$"):
            plan_batches([t("a", ["missing"])], ["a"])

    def test_duplicate_task(self):
        with self.assertRaisesRegex(ValueError, "^DUPLICATE_TASK$"):
            plan_batches([t("a"), t("a", ["missing"])], [])

    def test_invalid_shapes(self):
        samples = [
            (None, []),
            ([], ()),
            ([None], []),
            ([dict(id="a")], []),
            ([t("")], []),
            ([t("a", ("x",))], []),
            ([t("a", [1])], []),
            ([t("a", priority=True)], []),
            ([], [False]),
            ([dict(t("a"), extra=1)], []),
        ]
        for tasks, done in samples:
            with (
                self.subTest(tasks=tasks, done=done),
                self.assertRaisesRegex(ValueError, "^INVALID_TASK$"),
            ):
                plan_batches(tasks, done)

    def test_shape_precedence(self):
        with self.assertRaisesRegex(ValueError, "^INVALID_TASK$"):
            plan_batches([t("a", ["missing"]), t("a"), None], [])

    def test_missing_before_cycle(self):
        with self.assertRaisesRegex(ValueError, "^MISSING_DEPENDENCY$"):
            plan_batches([t("a", ["a"]), t("b", ["missing"])], [])

    def test_cycles(self):
        for tasks in [[t("a", ["a"])], [t("ready"), t("a", ["b"]), t("b", ["a"])]]:
            with (
                self.subTest(tasks=tasks),
                self.assertRaisesRegex(ValueError, "^DEPENDENCY_CYCLE$"),
            ):
                plan_batches(tasks, [])

    def test_nonmutation(self):
        tasks = [t("b", ["a", "a"]), t("a")]
        done = ["external", "external"]
        before = copy.deepcopy((tasks, done))
        self.assertEqual(plan_batches(tasks, done), [["a"], ["b"]])
        self.assertEqual((tasks, done), before)

    def test_long_chain(self):
        tasks = [t(str(i), [str(i - 1)] if i else []) for i in range(1200)]
        self.assertEqual(plan_batches(tasks, []), [[str(i)] for i in range(1200)])

    def test_whitespace_and_negative(self):
        self.assertEqual(plan_batches([t(" ", priority=-3), t("b", [" "], -5)], []), [[" "], ["b"]])
