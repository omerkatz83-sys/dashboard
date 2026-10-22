"""Check stop cancellations without loading prices or executing the dashboard."""
import ast
import copy
import math
import unittest
from pathlib import Path


source = Path(__file__).resolve().parents[1] / "dashboard_app.py"
tree = ast.parse(source.read_text(encoding="utf-8"))
nodes = [n for n in tree.body if (
    isinstance(n, ast.FunctionDef) and n.name in {"normalize_market_ticker", "_normalize_active_stop_orders"}
) or (isinstance(n, ast.Assign) and any(
    isinstance(t, ast.Name) and t.id == "YAHOO_TICKER_ALIASES" for t in n.targets))]
ns = {"copy": copy, "math": math}
exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), ns)


class StopOrderTests(unittest.TestCase):
    def test_removed_stops_stay_absent_with_open_positions(self):
        saved = {"NVDA": {"stop_price": 190, "currency": "USD", "check_from_ts": "original"}}
        before = copy.deepcopy(saved)
        for _ in range(3):
            saved, changed = ns["_normalize_active_stop_orders"](saved, {"NVDA", "IEMG", "GOOGL", "FBTC"})
            self.assertFalse(changed)
            self.assertEqual(saved, before)

    def test_empty_saved_list_remains_empty(self):
        result, changed = ns["_normalize_active_stop_orders"]({}, {"IEMG", "GOOGL", "FBTC"})
        self.assertEqual(result, {})
        self.assertFalse(changed)

    def test_legacy_aliases_and_sold_positions(self):
        saved = {"CNDX": 1600, "SOLD": {"stop_price": 100}, "INVALID": {"stop_price": float("nan")}}
        result, changed = ns["_normalize_active_stop_orders"](saved, {"CNDX.L", "INVALID"})
        self.assertTrue(changed)
        self.assertEqual(result, {"CNDX.L": {"stop_price": 1600.0, "currency": "USD"}})
        self.assertIn("SOLD", saved)

    def test_invalid_state_is_not_replaced(self):
        with self.assertRaises(ValueError):
            ns["_normalize_active_stop_orders"]([], {"IEMG"})


if __name__ == "__main__":
    unittest.main()
