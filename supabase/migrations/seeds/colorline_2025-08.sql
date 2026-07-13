-- Color Line BAF august 2025 (Wayback Machine 2025-08-09)
-- Kilde: https://web.archive.org/web/20250809085831/https://www.colorline-cargo.com/services/baf-adjustments

INSERT INTO baf_data (
  id,
  company,
  route,
  valid_from,
  valid_to,
  period_label,
  price_nok,
  price_eur,
  source_url,
  first_seen_at,
  updated_at
)
VALUES
  (
    'Color Line|Oslo – Kiel|2025-08-01',
    'Color Line',
    'Oslo – Kiel',
    '2025-08-01',
    '2025-08-31',
    'BAF Adjustment Fee 01.–31.08.2025 (NOK / LM)',
    105,
    8.8,
    'https://web.archive.org/web/20250809085831/https://www.colorline-cargo.com/services/baf-adjustments',
    '2025-08-09T08:58:31+00:00',
    now()
  ),
  (
    'Color Line|Larvik – Hirtshals|2025-08-01',
    'Color Line',
    'Larvik – Hirtshals',
    '2025-08-01',
    '2025-08-31',
    'BAF Adjustment Fee 01.–31.08.2025 (NOK / LM)',
    103,
    8.6,
    'https://web.archive.org/web/20250809085831/https://www.colorline-cargo.com/services/baf-adjustments',
    '2025-08-09T08:58:31+00:00',
    now()
  ),
  (
    'Color Line|Kristiansand – Hirtshals|2025-08-01',
    'Color Line',
    'Kristiansand – Hirtshals',
    '2025-08-01',
    '2025-08-31',
    'BAF Adjustment Fee 01.–31.08.2025 (NOK / LM)',
    103,
    8.6,
    'https://web.archive.org/web/20250809085831/https://www.colorline-cargo.com/services/baf-adjustments',
    '2025-08-09T08:58:31+00:00',
    now()
  )
ON CONFLICT (id) DO UPDATE SET
  company = EXCLUDED.company,
  route = EXCLUDED.route,
  valid_from = EXCLUDED.valid_from,
  valid_to = EXCLUDED.valid_to,
  period_label = EXCLUDED.period_label,
  price_nok = EXCLUDED.price_nok,
  price_eur = EXCLUDED.price_eur,
  source_url = EXCLUDED.source_url,
  updated_at = now();

INSERT INTO baf_price_history (baf_id, price_nok, price_eur, period_label, valid_to, fetched_at)
SELECT
  d.id,
  d.price_nok,
  d.price_eur,
  d.period_label,
  d.valid_to,
  d.first_seen_at
FROM baf_data AS d
WHERE d.id IN (
  'Color Line|Oslo – Kiel|2025-08-01',
  'Color Line|Larvik – Hirtshals|2025-08-01',
  'Color Line|Kristiansand – Hirtshals|2025-08-01'
)
AND NOT EXISTS (
  SELECT 1
  FROM baf_price_history AS h
  WHERE h.baf_id = d.id
    AND h.fetched_at = d.first_seen_at
);

INSERT INTO baf_fetch_log (fetched_at, row_count, error_count, errors, status)
VALUES (now(), 3, 0, '[]'::jsonb, 'ok');
