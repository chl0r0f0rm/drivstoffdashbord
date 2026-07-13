import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from baf_parser import parse_colorline

SAMPLE_HTML = """
<section class="mod modStructuredinfo default contentarea-narrow">
  <div class="mod-hd">
    <h2 class="sectionHeader">BAF Adjustment Fee 01.–31.07.2026 (NOK / LM)</h2>
  </div>
  <div class="mod-bd">
    <div class="row">
      <div class="label grid-all-1-3">Oslo – Kiel</div>
      <div class="text grid-all-2-3"><p>123 NOK (€ 11,1)</p></div>
    </div>
    <div class="row">
      <div class="label grid-all-1-3">Larvik – Hirtshals</div>
      <div class="text grid-all-2-3"><p>125 NOK (€ 11,3)</p></div>
    </div>
    <div class="row">
      <div class="label grid-all-1-3">Kristiansand – Hirtshals</div>
      <div class="text grid-all-2-3"><p>125 NOK (€ 11,3)</p></div>
    </div>
  </div>
</section>
"""


class BafParserTest(unittest.TestCase):
    def test_parse_colorline_sample_html(self):
        fetched_at = datetime(2026, 7, 6, tzinfo=timezone.utc)
        rows = parse_colorline(SAMPLE_HTML, fetched_at=fetched_at)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["route"], "Oslo – Kiel")
        self.assertEqual(rows[0]["price_nok"], 123)
        self.assertAlmostEqual(rows[0]["price_eur"], 11.1)
        self.assertEqual(rows[0]["valid_from"], "2026-07-01")
        self.assertEqual(rows[0]["valid_to"], "2026-07-31")
        self.assertEqual(rows[0]["company"], "Color Line")


if __name__ == "__main__":
    unittest.main()
