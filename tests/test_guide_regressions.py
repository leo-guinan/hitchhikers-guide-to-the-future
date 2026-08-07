import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GUIDE_HTML = ROOT / "site" / "guide" / "index.html"
CANONICAL = "https://guide.hitchhikersguidetothefuture.com"


def frontend_script():
    html = GUIDE_HTML.read_text()
    match = re.search(r"<script>(.*?)</script>", html, re.S)
    if not match:
        raise AssertionError("Guide page has no inline script")
    return match.group(1)


def polygon_for_connection_count(connection_count):
    """Evaluate the production polygon function in Node, not a Python copy."""
    script = frontend_script()
    match = re.search(r"(function shapeForConnections\(.*?)(?=\nfunction pointInPolygon)", script, re.S)
    if not match:
        raise AssertionError("Guide page has no shapeForConnections function")
    script = match.group(1)
    probe = f"""
const points = Array.from({{length: {connection_count + 1}}}, (_, i) => ({{x: (i + 1) / 20, y: (i + 1) / 23}}));
process.stdout.write(JSON.stringify(shapeForConnections(points, {{x0: 6, y0: 6, x1: 754, y1: 616}})));
"""
    source = script + "\n" + probe
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as handle:
        handle.write(source)
        path = handle.name
    try:
        result = subprocess.run(["node", path], capture_output=True, text=True, check=True)
    finally:
        Path(path).unlink(missing_ok=True)
    return json.loads(result.stdout)


def point_in_polygon(point, polygon):
    inside = False
    for i, current in enumerate(polygon):
        previous = polygon[i - 1]
        xi, yi = current
        xj, yj = previous
        intersects = ((yi > point[1]) != (yj > point[1])) and (
            point[0] < (xj - xi) * (point[1] - yi) / (yj - yi) + xi
        )
        if intersects:
            inside = not inside
    return inside


def orientation(a, b, c):
    value = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    return (value > 1e-9) - (value < -1e-9)


def segments_intersect(a, b, c, d):
    return orientation(a, b, c) * orientation(a, b, d) < 0 and orientation(c, d, a) * orientation(c, d, b) < 0


def assert_simple_polygon(testcase, polygon):
    count = len(polygon)
    for i in range(count):
        a, b = polygon[i], polygon[(i + 1) % count]
        for j in range(i + 1, count):
            if j in (i, (i + 1) % count, (i - 1) % count):
                continue
            c, d = polygon[j], polygon[(j + 1) % count]
            testcase.assertFalse(
                segments_intersect(a, b, c, d),
                f"self-crossing edges {(a, b)} and {(c, d)} in {polygon}",
            )


class GuideProjectionRegressionTests(unittest.TestCase):
    def test_frontend_script_parses(self):
        script = frontend_script()
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as handle:
            handle.write(script)
            path = handle.name
        try:
            result = subprocess.run(["node", "--check", path], capture_output=True, text=True)
        finally:
            Path(path).unlink(missing_ok=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_polygon_vertex_count_tracks_connections_and_is_not_plain_rectangle(self):
        for connections in range(1, 8):
            polygon = polygon_for_connection_count(connections)
            expected = min(10, max(4, 3 + connections))
            self.assertEqual(len(polygon), expected)
            # A connection-derived projection must visibly chamfer at least one corner.
            self.assertTrue(
                any(x not in (6, 754) for x, _ in polygon)
                and any(y not in (6, 616) for _, y in polygon),
                f"polygon regressed to a rectangle: {polygon}",
            )

    def test_polygon_is_ordered_simple_and_contains_content_rectangle(self):
        bounds = (6, 6, 754, 616)
        content = (40, 40, 720, 580)
        polygon = polygon_for_connection_count(7)
        assert_simple_polygon(self, polygon)
        for corner in ((content[0], content[1]), (content[2], content[1]), (content[2], content[3]), (content[0], content[3])):
            self.assertTrue(point_in_polygon(corner, polygon), f"content corner escaped polygon: {corner} {polygon}")
        self.assertEqual(bounds, (6, 6, 754, 616))

    def test_runtime_contains_measurement_and_reflow_hooks(self):
        script = frontend_script()
        for required in (
            "getBoundingClientRect()",
            "assertProjectionContainment",
            "dataset.containment",
            "requestAnimationFrame(layoutSnapshot)",
            "if(!snapshotBox.hidden)requestAnimationFrame(layoutSnapshot)",
            "cardOutline.setAttribute('viewBox'",
        ):
            self.assertIn(required, script)

    def test_answer_renderer_uses_synthesis_not_result_count(self):
        script = frontend_script()
        self.assertIn("snapshotAnswer.textContent=d.answer.text", script)
        self.assertNotIn("snapshotAnswer.textContent=d.result_count", script)
        self.assertIn("cryptoeconomic coordination layer", (ROOT / "services" / "api" / "app.py").read_text())


@unittest.skipUnless(os.environ.get("RUN_LIVE_GUIDE") == "1", "set RUN_LIVE_GUIDE=1 for network smoke checks")
class LiveGuideRegressionTests(unittest.TestCase):
    def curl(self, *args):
        return subprocess.run(["curl", "-fsS", *args], capture_output=True, text=True, check=True).stdout

    def test_live_crypto_answer_is_substantive(self):
        raw = self.curl(
            "-X", "POST",
            f"{CANONICAL}/api/guide/search?regression=crypto",
            "-H", "content-type: application/json",
            "--data", '{"query":"what is crypto?"}',
        )
        payload = json.loads(raw)
        text = payload["answer"]["text"]
        self.assertIn("reveal a collective answer of", text)
        self.assertIn("cryptoeconomic coordination layer", text)
        self.assertNotRegex(text.lower(), r"reveal a collective answer of\s*\d+\s*(documents?|records?)\.?$")
        self.assertGreaterEqual(payload["search_trace"]["stage_count"], 6)
        self.assertIn("synthesis", payload["answer"])

    def test_live_ai_answer_is_substantive(self):
        raw = self.curl(
            "-X", "POST",
            f"{CANONICAL}/api/guide/search?regression=ai",
            "-H", "content-type: application/json",
            "--data", '{"query":"what is AI?"}',
        )
        payload = json.loads(raw)
        text = payload["answer"]["text"]
        self.assertIn("reveal a collective answer of", text)
        self.assertIn("transforms inputs into more valuable outputs", text)
        self.assertIn("human coordination", text)
        self.assertIsNotNone(payload["answer"]["synthesis"])

    def test_live_page_contains_containment_contract(self):
        html = self.curl(f"{CANONICAL}/guide/?regression=source-contract")
        self.assertIn("assertProjectionContainment", html)
        self.assertIn("dataset.containment", html)
        self.assertIn("requestAnimationFrame(layoutSnapshot)", html)
        self.assertIn("c=Math.min(18", html)


if __name__ == "__main__":
    unittest.main()
