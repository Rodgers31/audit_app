-- REVIEW PROPOSAL ONLY. Take and verify an external backup before applying.
-- Snapshot: public county entity API, 2026-09-27. Default ends in ROLLBACK.
BEGIN;
CREATE TEMP TABLE expected_county_identity (id int PRIMARY KEY, canonical_name text, slug text) ON COMMIT DROP;
INSERT INTO expected_county_identity VALUES
(33, 'Baringo County', 'baringo-county'),
(39, 'Bomet County', 'bomet-county'),
(42, 'Bungoma County', 'bungoma-county'),
(43, 'Busia County', 'busia-county'),
(31, 'Elgeyo Marakwet County', 'elgeyo-marakwet-county'),
(17, 'Embu County', 'embu-county'),
(10, 'Garissa County', 'garissa-county'),
(46, 'Homa Bay County', 'homa-bay-county'),
(14, 'Isiolo County', 'isiolo-county'),
(37, 'Kajiado County', 'kajiado-county'),
(40, 'Kakamega County', 'kakamega-county'),
(38, 'Kericho County', 'kericho-county'),
(25, 'Kiambu County', 'kiambu-county'),
(6, 'Kilifi County', 'kilifi-county'),
(23, 'Kirinyaga County', 'kirinyaga-county'),
(48, 'Kisii County', 'kisii-county'),
(45, 'Kisumu County', 'kisumu-county'),
(18, 'Kitui County', 'kitui-county'),
(5, 'Kwale County', 'kwale-county'),
(34, 'Laikipia County', 'laikipia-county'),
(8, 'Lamu County', 'lamu-county'),
(19, 'Machakos County', 'machakos-county'),
(20, 'Makueni County', 'makueni-county'),
(12, 'Mandera County', 'mandera-county'),
(13, 'Marsabit County', 'marsabit-county'),
(15, 'Meru County', 'meru-county'),
(47, 'Migori County', 'migori-county'),
(4, 'Mombasa County', 'mombasa-county'),
(24, 'Murang''a County', 'muranga-county'),
(3, 'Nairobi County', 'nairobi-county'),
(35, 'Nakuru County', 'nakuru-county'),
(32, 'Nandi County', 'nandi-county'),
(36, 'Narok County', 'narok-county'),
(49, 'Nyamira County', 'nyamira-county'),
(21, 'Nyandarua County', 'nyandarua-county'),
(22, 'Nyeri County', 'nyeri-county'),
(28, 'Samburu County', 'samburu-county'),
(44, 'Siaya County', 'siaya-county'),
(9, 'Taita Taveta County', 'taita-taveta-county'),
(7, 'Tana River County', 'tana-river-county'),
(16, 'Tharaka Nithi County', 'tharaka-nithi-county'),
(29, 'Trans Nzoia County', 'trans-nzoia-county'),
(26, 'Turkana County', 'turkana-county'),
(30, 'Uasin Gishu County', 'uasin-gishu-county'),
(41, 'Vihiga County', 'vihiga-county'),
(11, 'Wajir County', 'wajir-county'),
(27, 'West Pokot County', 'west-pokot-county');
SELECT id FROM entities WHERE lower(type::text) = 'county' ORDER BY id FOR UPDATE;
DO $$ BEGIN
  IF (SELECT count(*) FROM entities WHERE lower(type::text) = 'county') <> 47
     OR EXISTS (SELECT 1 FROM expected_county_identity x LEFT JOIN entities e ON e.id=x.id
                WHERE e.id IS NULL OR e.canonical_name <> x.canonical_name OR e.slug <> x.slug
                   OR lower(e.type::text) <> 'county') THEN
    RAISE EXCEPTION 'County identity snapshot changed; regenerate and review';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM entities WHERE id=4 AND canonical_name='Mombasa County'
      AND metadata #>> '{metrics,FY2024/25,county_code}' = '047'
      AND metadata #>> '{metrics,FY2025/26,county_code}' = '047')
     OR NOT EXISTS (SELECT 1 FROM entities WHERE id=3 AND canonical_name='Nairobi County'
      AND metadata #>> '{metrics,FY2024/25,county_code}' = '001'
      AND metadata #>> '{metrics,FY2025/26,county_code}' = '001') THEN
    RAISE EXCEPTION 'Expected four metadata cells changed; regenerate and review';
  END IF;
END $$;
-- Recovery data must also be exported BEFORE this transaction in the release run.
CREATE TEMP TABLE county_identity_before ON COMMIT DROP AS SELECT * FROM entities WHERE id IN (3,4);
UPDATE entities SET metadata = jsonb_set(jsonb_set(metadata,
    '{metrics,FY2024/25,county_code}', to_jsonb(CASE id WHEN 4 THEN '001'::text ELSE '047'::text END), false),
    '{metrics,FY2025/26,county_code}', to_jsonb(CASE id WHEN 4 THEN '001'::text ELSE '047'::text END), false)
WHERE id IN (3,4);
SELECT e.id, e.canonical_name, e.slug, b.metadata AS before, e.metadata AS after
FROM entities e JOIN county_identity_before b USING (id) ORDER BY e.id;
-- No IDs, names, slugs, foreign keys, budget amounts or document relations change.
ROLLBACK;
