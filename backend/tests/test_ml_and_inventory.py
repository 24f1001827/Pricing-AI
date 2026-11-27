import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_ml_placeholder.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key-at-least-32-chars-long")

from ml.profiler import FORBIDDEN_LEAKAGE_COLUMNS, aggregate_daily_sku_demand, profile_dataset
from ml.strategist import default_training_plan
from ml.trainer import _select_feature_columns, train_best_pipeline


class MLAndInventoryUnitTests(unittest.TestCase):
    def _synthetic_orders(self, days: int = 45) -> pd.DataFrame:
        rng = np.random.default_rng(42)
        start = datetime(2025, 1, 1).date()
        rows = []
        for d in range(days):
            cur = start + timedelta(days=d)
            for pid, base_p, cost in [("SKU-A", 30.0, 14.0), ("SKU-B", 50.0, 22.0)]:
                price = round(base_p * float(rng.choice([0.85, 1.0, 1.15])), 2)
                is_promo = 1 if price < base_p else 0
                weekend = 1 if cur.weekday() in (5, 6) else 0
                # True downward-sloping demand curve
                expected_demand = max(1, int(round(40 * (base_p / price) ** 1.6 + (6 * weekend) + (5 * is_promo))))
                # Split into 2 orders to test daily aggregation
                q1 = max(1, expected_demand // 2)
                q2 = max(1, expected_demand - q1)
                for q in (q1, q2):
                    rows.append({
                        "date": cur.strftime("%Y-%m-%d"),
                        "product_id": pid,
                        "units_sold": q,
                        "price": price,
                        "cost": cost,
                        "is_promotion": is_promo,
                        "inventory_level": 120,
                        "channel": "online",
                    })
        return pd.DataFrame(rows)

    def test_aggregation_removes_leakage_and_builds_causal_features(self):
        raw_df = self._synthetic_orders(20)
        # Inject forbidden columns as if present
        raw_df["revenue"] = raw_df["units_sold"] * raw_df["price"]
        raw_df["profit"] = raw_df["revenue"] - raw_df["units_sold"] * raw_df["cost"]

        daily_df = aggregate_daily_sku_demand(raw_df, enable_lags=True)
        self.assertEqual(len(daily_df), 40)  # 20 days * 2 SKUs
        for forbidden in FORBIDDEN_LEAKAGE_COLUMNS:
            self.assertNotIn(forbidden, daily_df.columns)

        profile = profile_dataset(daily_df)
        plan = default_training_plan(profile)
        num_cols, cat_cols = _select_feature_columns(daily_df, plan)
        self.assertIn("price", num_cols)
        self.assertNotIn("units_sold", num_cols)
        self.assertNotIn("revenue", num_cols)
        self.assertNotIn("profit", num_cols)
        self.assertIn("product_id", cat_cols)

    def test_training_pipeline_learns_monotonic_elasticity_and_persists_bundle(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["DATA_DIR"] = tmpdir
            import ml.trainer as trainer_mod
            trainer_mod.DATA_DIR = tmpdir

            raw_df = self._synthetic_orders(45)
            daily_df = aggregate_daily_sku_demand(raw_df, enable_lags=True)
            profile = profile_dataset(daily_df)
            plan = default_training_plan(profile)

            res = train_best_pipeline(daily_df, unique_id="unit-test-job", plan=plan, profile=profile)
            self.assertTrue(os.path.exists(res["model_path"]))
            self.assertIn("rmse", res["metrics"])
            self.assertGreater(res["metrics"]["r2"], 0.3)


if __name__ == "__main__":
    unittest.main()
