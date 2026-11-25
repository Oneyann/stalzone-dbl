import unittest

from stalzone_dbl.index import SearchIndex, normalize, ngramize, parse


LISTING = [
    {
        "data": "items/weapons/ak105.json",
        "name": {"type": "translation", "lines": {"ru": "АК-105", "en": "AK-105"}},
    },
    {
        "data": "items/armor/zinc.json",
        "name": {"type": "text", "text": "Цинк"},
    },
]


class NormalizeTest(unittest.TestCase):
    def test_lowercases_and_strips_punctuation(self):
        self.assertEqual(normalize("  АК-105!  "), "ак 105")

    def test_empty_text_gives_empty_grams(self):
        self.assertEqual(ngramize(""), set())


class SearchIndexTest(unittest.TestCase):
    def setUp(self):
        self.index = SearchIndex()
        self.index.build("listing.json", LISTING)

    def test_finds_item_by_name(self):
        results = self.index.search("АК-105", threshold=0.5)
        self.assertTrue(results)
        self.assertEqual(results[0].id, "ak105")

    def test_unknown_query_returns_nothing(self):
        self.assertEqual(self.index.search("zzzzzz", threshold=0.5), [])

    def test_get_returns_entity(self):
        self.assertEqual(self.index.get("zinc")["data"], "items/armor/zinc.json")

    def test_rejects_non_list_data(self):
        with self.assertRaises(ValueError):
            list(parse("listing.json", {}))

    def test_rejects_unknown_file(self):
        with self.assertRaises(ValueError):
            list(parse("unknown.json", []))


if __name__ == "__main__":
    unittest.main()
