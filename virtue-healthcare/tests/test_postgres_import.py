import unittest
from pathlib import Path
from decimal import Decimal

from app.postgres import allocate_flags, parse_array, prepare_facilities, prepare_postal, FACILITY_COLUMNS, POSTAL_COLUMNS, DATA_DIR, facility_snapshot


class ImportTests(unittest.TestCase):
    def test_flag_proportions_and_reproducibility(self):
        ids = [str(i) for i in range(1000)]
        flags = allocate_flags(ids)
        self.assertEqual(sum(p for p, _ in flags.values()), 200)
        self.assertEqual(sum(u for _, u in flags.values()), 300)
        self.assertEqual(flags, allocate_flags(list(reversed(ids))))
        self.assertNotEqual(flags, allocate_flags(ids, 43))

    def test_duplicate_ids_rejected(self):
        with self.assertRaises(ValueError):
            allocate_flags(['a', 'a'])

    def test_arrays_reject_bad_shape(self):
        self.assertEqual(parse_array(''), [])
        for value in ['{}', '[null]', '[1]']:
            with self.assertRaises(ValueError):
                parse_array(value)

    def test_decoded_nul_is_removed(self):
        self.assertEqual(parse_array(r'["dial\u0000ysis", "MRI"]'), ['dialysis', 'MRI'])
        self.assertEqual(parse_array(r'["literal \\u0000"]'), [r'literal \u0000'])

    def test_real_snapshot_is_importable(self):
        path = facility_snapshot()
        rows = list(prepare_facilities(path))
        self.assertEqual(len(rows), 9989)
        self.assertEqual(sum(r[60] for r in rows), 1998)
        self.assertTrue(all(row[61] is None for row in rows))
        self.assertTrue(all(len(r) == 64 for r in rows))

        self.assertEqual(len(FACILITY_COLUMNS), 60)
        id_column = FACILITY_COLUMNS.index('unique_id')
        flags = allocate_flags([row[id_column] for row in rows])
        for row in rows:
            postcode_flag, legacy_url_flag = flags[row[id_column]]
            self.assertEqual(row[62], Decimal('1') - Decimal('0.3') * postcode_flag - Decimal('0.5') * legacy_url_flag)
            for value in row:
                for text in (value if isinstance(value, list) else [value]):
                    if isinstance(text, str):
                        self.assertNotIn('\x00', text)

    def test_full_postal_snapshot_is_importable(self):
        path = DATA_DIR / 'pincode_offices_clean.csv.gz'
        rows = list(prepare_postal(path))
        self.assertEqual(len(rows), 165625)
        self.assertEqual(len(POSTAL_COLUMNS), 15)
        self.assertTrue(all(len(row) == 15 for row in rows))
        key = POSTAL_COLUMNS.index('source_record')
        self.assertEqual(len({row[key] for row in rows}), len(rows))


if __name__ == '__main__':
    unittest.main()
