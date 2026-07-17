import unittest
from unittest.mock import patch

from lib import badges


class PublishedMetricsTests(unittest.TestCase):
    def test_counts_visible_content_and_each_roast_paragraph(self):
        issue = {
            "date": "2026-07-18",
            "top_stories": [
                {
                    "title": "Story title",
                    "category": "News",
                    "short_summary": "Short summary",
                    "deep_summary": "Deep summary",
                    "score": 99,
                    "url": "https://example.com/ignored",
                }
            ],
            "cves": [
                {
                    "title": "CVE title",
                    "summary": "CVE summary",
                    "cve_ids": ["CVE-2026-0001"],
                    "score": 10,
                }
            ],
            "roast_summary": ["First roast", "Second roast\nThird roast", ""],
        }
        visible_text = [
            "Story title",
            "News",
            "Short summary",
            "Deep summary",
            "CVE title",
            "CVE summary",
            "CVE-2026-0001",
            "First roast",
            "Second roast",
            "Third roast",
        ]
        encoding = badges._get_encoding()
        expected_tokens = sum(len(encoding.encode(text)) for text in visible_text)

        metrics = badges.calculate_published_metrics([issue])

        self.assertEqual(metrics["tokens"], expected_tokens)
        self.assertEqual(metrics["posts"], 5)

    def test_supports_legacy_string_roasts_and_skips_invalid_issues(self):
        metrics = badges.calculate_published_metrics(
            [None, {"top_stories": [], "cves": [], "roast_summary": "One\n\nTwo"}]
        )

        self.assertEqual(metrics["posts"], 2)
        self.assertGreater(metrics["tokens"], 0)

    def test_warm_cache_avoids_reloading_s3_issues(self):
        badges._content_cache["metrics"] = None
        badges._content_cache["expires_at"] = 0
        with patch.object(
            badges, "get_issue_dates", return_value=["2026-07-18"]
        ) as dates, patch.object(
            badges,
            "get_issue_data",
            return_value={"top_stories": [], "cves": [], "roast_summary": ["Roast"]},
        ) as issue:
            first = badges.get_published_metrics()
            second = badges.get_published_metrics()

        self.assertEqual(first, second)
        dates.assert_called_once_with()
        issue.assert_called_once_with("2026-07-18")


class SvgRenderingTests(unittest.TestCase):
    def test_escapes_text_and_rejects_unsafe_colors(self):
        svg = badges.render_badge_svg(
            "<script>&",
            "1,234",
            "url(javascript:alert(1))",
            "ABC",
        )

        self.assertIn("&lt;script&gt;&amp;", svg)
        self.assertNotIn("<script>", svg)
        self.assertIn('fill="#000000"', svg)
        self.assertIn('fill="#abc"', svg)
        self.assertNotIn("javascript", svg)


class BadgeRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from web.main import app

        app.config.update(TESTING=True)
        cls.client = app.test_client()

    def test_returns_metric_svg_with_cache_headers_and_etag(self):
        with patch("web.main.get_badge_value", return_value=1234):
            response = self.client.get(
                "/badge/posts.svg?left_text=all%20posts&left_color=BLACK&right_color=GREEN"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "image/svg+xml")
        self.assertIn(b"all posts", response.data)
        self.assertIn(b"1,234", response.data)
        self.assertEqual(response.headers["Cache-Control"], "public, max-age=300, s-maxage=300")
        self.assertIn("ETag", response.headers)

        with patch("web.main.get_badge_value", return_value=1234):
            conditional = self.client.get(
                "/badge/posts.svg?left_text=all%20posts&left_color=BLACK&right_color=GREEN",
                headers={"If-None-Match": response.headers["ETag"]},
            )
        self.assertEqual(conditional.status_code, 304)

    def test_returns_visible_uncached_badge_when_metric_fails(self):
        with patch("web.main.get_badge_value", side_effect=RuntimeError("AWS unavailable")):
            response = self.client.get("/badge/tokens.svg")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"unavailable", response.data)
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_unknown_metric_returns_404_svg(self):
        response = self.client.get("/badge/not-real.svg")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.mimetype, "image/svg+xml")


if __name__ == "__main__":
    unittest.main()
