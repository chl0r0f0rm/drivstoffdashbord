import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fetch_colorline_baf import (
    parse_colorline_baf,
    parse_eur_amount,
    parse_period_label,
    parse_price_text,
)

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


class ColorLineBafParserTest(unittest.TestCase):
    def test_parse_period_label(self):
        valid_from, valid_to, label = parse_period_label(
            "BAF Adjustment Fee 01.–31.07.2026 (NOK / LM)"
        )
        self.assertEqual(valid_from, "2026-07-01")
        self.assertEqual(valid_to, "2026-07-31")
        self.assertIn("07.2026", label)

    def test_parse_price_text(self):
        nok, eur = parse_price_text("123 NOK (€ 11,1)")
        self.assertEqual(nok, 123)
        self.assertAlmostEqual(eur, 11.1)

    def test_parse_eur_amount(self):
        self.assertAlmostEqual(parse_eur_amount("11,1"), 11.1)

    def test_parse_sample_html(self):
        rows = parse_colorline_baf(
            SAMPLE_HTML,
            fetched_at=datetime(2026, 7, 6, tzinfo=timezone.utc),
        )
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["route"], "Oslo – Kiel")
        self.assertEqual(rows[0]["price_nok"], 123)
        self.assertEqual(rows[0]["valid_from"], "2026-07-01")
        self.assertEqual(rows[0]["company"], "Color Line")


if __name__ == "__main__":
    unittest.main()
