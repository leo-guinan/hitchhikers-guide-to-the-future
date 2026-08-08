import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COURSE = ROOT / "site" / "course" / "index.html"


class CourseRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = COURSE.read_text()
        scripts = re.findall(r"<script>(.*?)</script>", cls.html, re.S)
        cls.assert_script_count = len(scripts)
        cls.script_path = Path("/tmp/hgf-course-regression.js")
        cls.script_path.write_text(scripts[0] if scripts else "")

    def test_course_has_seven_ordered_steps_and_kipper_first(self):
        self.assertEqual(self.assert_script_count, 1)
        self.assertEqual(len(re.findall(r'class="step(?: active)?"', self.html)), 7)
        self.assertIn("step 01 / install the rail", self.html.lower())
        self.assertLess(self.html.lower().index("install kipper first"), self.html.lower().index("humanpower is the case study"))
        self.assertIn("chromewebstore.google.com", self.html)

    def test_course_requires_explicit_local_actions(self):
        self.assertIn("id=\"kipperCheck\"", self.html)
        self.assertIn("id=\"mechanism\"", self.html)
        self.assertIn("id=\"question\"", self.html)
        self.assertIn("id=\"actionTaken\"", self.html)
        self.assertIn("id=\"reflection\"", self.html)

    def test_receipt_is_local_and_claim_calibrated(self):
        for marker in ("course_completion", "self-attested completion receipt", "wallet ownership", "Quai delivery", "does not promise money, Quai"):
            self.assertIn(marker, self.html)
        self.assertIn("Posting remains your action", self.html)
        self.assertNotIn("guaranteed quai", self.html.lower())
        self.assertNotIn("private key", self.html.lower())

    def test_inline_javascript_parses(self):
        result = subprocess.run(["node", "--check", str(self.script_path)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
