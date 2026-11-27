import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

_TMP_DIR = tempfile.mkdtemp(prefix="pricing_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP_DIR, 'test.db')}"
os.environ["SECRET_KEY"] = "integration-test-secret-key-at-least-32-chars"
os.environ["DATA_DIR"] = _TMP_DIR
os.environ["ALLOW_REGISTRATION"] = "true"
os.environ["MIN_RECORDS_TO_TRAIN"] = "20"
os.environ["INITIAL_ADMIN_EMAIL"] = "admin@test.local"
os.environ["INITIAL_ADMIN_PASSWORD"] = "StrongAdminPass123!"
os.environ["RUN_SCHEDULER"] = "false"
os.environ["MLFLOW_TRACKING_URI"] = ""
os.environ["GROQ_API_KEY"] = ""

from main import app  # noqa: E402


class APIIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client_cm = TestClient(app)
        cls.client = cls.client_cm.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client_cm.__exit__(None, None, None)

    def test_end_to_end_pricing_and_inventory_workflow(self):
        # 1. Health check
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "ok")

        # 2. Login as bootstrapped admin
        r = self.client.post("/auth/login", json={
            "email": "admin@test.local",
            "password": "StrongAdminPass123!",
        })
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["is_admin"])

        # 3. Create products with guardrails & low stock to verify inventory alerts
        p1 = self.client.post("/products/", json={
            "product_id": "P001",
            "product_name": "Espresso Beans",
            "category": "Coffee",
            "base_price": 25.0,
            "cost": 10.0,
            "min_price": 15.0,
            "max_price": 45.0,
            "stock_on_hand": 15,
            "lead_time_days": 7,
            "service_level": 0.95,
        })
        self.assertEqual(p1.status_code, 200)

        # Price bound validation rejects min_price > max_price
        bad_p = self.client.post("/products/", json={
            "product_id": "BAD",
            "product_name": "Invalid",
            "min_price": 50.0,
            "max_price": 20.0,
        })
        self.assertEqual(bad_p.status_code, 422)

        # 4. Seed 24 daily orders across varied prices
        start = datetime(2025, 2, 1)
        prices = [18.0, 22.0, 25.0, 30.0, 35.0, 40.0]
        for i in range(24):
            price = prices[i % len(prices)]
            qty = max(1, int(round(32 - 0.55 * price)))
            dt = (start + timedelta(days=i)).isoformat()
            res = self.client.post("/orders/", json={
                "customer_name": f"Customer {i}",
                "customer_email": f"cust{i}@example.com",
                "order_time": dt,
                "channel": "online",
                "is_promotion": price < 24.0,
                "line_items": [{"product_id": "P001", "quantity": qty, "unit_price": price}],
            })
            self.assertEqual(res.status_code, 200)

        # Reject invalid negative quantity
        bad_order = self.client.post("/orders/", json={
            "line_items": [{"product_id": "P001", "quantity": -2, "unit_price": 20.0}],
        })
        self.assertEqual(bad_order.status_code, 422)

        # 5. Summary & Calendar
        summary = self.client.get("/orders/summary")
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(summary.json()["total_orders"], 24)

        cal = self.client.post("/orders/calendar", json={
            "date": "2025-12-25",
            "is_closed": True,
            "is_holiday": True,
            "note": "Holiday",
        })
        self.assertEqual(cal.status_code, 200)

        # 6. Train model (runs in TestClient background task synchronously)
        train_res = self.client.post("/training/start")
        self.assertEqual(train_res.status_code, 200)
        unique_id = train_res.json()["unique_id"]

        status_res = self.client.get(f"/training/status/{unique_id}")
        self.assertEqual(status_res.status_code, 200)
        self.assertEqual(status_res.json()["status"], "completed")

        # 7. Predictions & Inventory Summary
        pred_res = self.client.get(f"/predictions/{unique_id}")
        self.assertEqual(pred_res.status_code, 200)
        pred_data = pred_res.json()
        self.assertTrue(len(pred_data["product_results"]) == 1)
        opt_price = pred_data["product_results"][0]["optimal_price"]
        self.assertGreaterEqual(opt_price, 15.0)
        self.assertLessEqual(opt_price, 45.0)
        self.assertTrue(len(pred_data["inventory_recommendations"]) == 1)

        inv_res = self.client.get("/products/inventory-summary")
        self.assertEqual(inv_res.status_code, 200)
        self.assertTrue(inv_res.json()["has_forecast"])
        inv_item = inv_res.json()["items"][0]
        self.assertIn(inv_item["stock_status"], ["stockout_risk", "reorder_now", "healthy", "overstock"])

        # 8. Restock & Apply Price
        restock = self.client.post("/products/P001/restock", json={"quantity": 200})
        self.assertEqual(restock.status_code, 200)
        self.assertGreaterEqual(restock.json()["stock_on_hand"], 200)

        apply_p = self.client.post("/products/P001/apply-price", json={"price": opt_price})
        self.assertEqual(apply_p.status_code, 200)
        self.assertEqual(apply_p.json()["base_price"], round(opt_price, 2))

        # 9. Chat endpoint works even without external LLM key
        chat_res = self.client.post(f"/predictions/chat/{unique_id}", json={"message": "Summarize pricing", "history": []})
        self.assertEqual(chat_res.status_code, 200)
        self.assertIn("response", chat_res.json())


if __name__ == "__main__":
    unittest.main()
