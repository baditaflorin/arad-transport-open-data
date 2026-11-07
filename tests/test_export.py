import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("exporter", Path(__file__).resolve().parents[1] / "scripts/export.py")
exporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(exporter)


class ExportTests(unittest.TestCase):
    def test_polyline_reference_and_coordinate_order(self):
        self.assertEqual(exporter.decode_polyline('_p~iF~ps|U_ulLnnqC_mqNvxq`@'),
                         [[-120.2, 38.5], [-120.95, 40.7], [-126.453, 43.252]])

    def test_truncated_polyline_rejected(self):
        with self.assertRaises(ValueError):
            exporter.decode_polyline('_p~iF')

    def test_negative_pattern_and_repeated_stop_are_preserved(self):
        routes = [{"id": 13, "shortName": "3", "longName": "Test", "type": 0,
                   "patterns": [{"routeId": 13, "index": -14, "direction": -1,
                                 "fromStopId": 1, "toStopId": 1, "stops": [1, 2, 1], "geometry": ""}]}]
        stops = [{"id": 1, "patterns": [{"routeId": 13}]}, {"id": 2, "patterns": [{"routeId": 13}]}]
        normalized, patterns, ordered, _ = exporter.normalize(routes, stops)
        self.assertEqual(normalized[0]["mode"], "tram")
        self.assertEqual(patterns[0]["patternId"], "13:-14")
        self.assertEqual([r["stopId"] for r in ordered], [1, 2, 1])
        self.assertEqual([r["stopSequence"] for r in ordered], [1, 2, 3])

    def test_unknown_stop_rejected(self):
        route = {"id": 1, "shortName": "1", "type": 3, "patterns": [{"index": -1, "stops": [999]}]}
        with self.assertRaises(ValueError):
            exporter.normalize([route], [])

    def test_failed_source_keeps_previous_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "routes.json").write_text('["previous"]')
            with patch.object(exporter.Client, "get", side_effect=TimeoutError("upstream")):
                with self.assertRaises(TimeoutError):
                    exporter.export(path)
            self.assertEqual((path / "routes.json").read_text(), '["previous"]')


if __name__ == "__main__":
    unittest.main()
