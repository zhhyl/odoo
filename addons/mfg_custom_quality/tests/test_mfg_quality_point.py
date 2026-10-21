# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install", "mfg_custom", "plm_custom")
class TestMfgQualityPoint(TransactionCase):
    """測試 :class:`MfgQualityPoint` 與 :class:`MfgQualityPointLine`。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Point = cls.env["mfg_custom.quality.point"]
        cls.PointLine = cls.env["mfg_custom.quality.point.line"]
        cls.Product = cls.env["product.product"]
        cls.product_a = cls.Product.create(
            {"name": "QA-Test Product A", "type": "consu"},
        )
        cls.product_b = cls.Product.create(
            {"name": "QA-Test Product B", "type": "consu"},
        )

    def _make_point(self, **extra):
        vals = {
            "name": "外觀尺寸",
            "product_id": self.product_a.id,
            "sample_qty": 3,
            "method": "measure",
            "trigger_on": "manual",
        }
        vals.update(extra)
        return self.Point.create(vals)

    def test_point_create_with_default_code(self):
        """建立品檢點時應自動產生 code。"""
        point = self._make_point()
        self.assertTrue(point.id)
        self.assertNotEqual(point.code, "New")
        self.assertTrue(point.code, "code 不可為空")
        self.assertTrue(point.active)

    def test_point_create_with_three_lines(self):
        """品檢點可一次性附帶 3 筆檢項。"""
        point = self._make_point()
        self.PointLine.create(
            {"point_id": point.id, "name": "長度", "min_value": 10.0, "max_value": 11.0},
        )
        self.PointLine.create(
            {"point_id": point.id, "name": "寬度", "min_value": 5.0, "max_value": 5.5},
        )
        self.PointLine.create(
            {"point_id": point.id, "name": "外觀", "is_critical": True},
        )
        self.assertEqual(len(point.check_line_ids), 3)
        criticals = point.check_line_ids.filtered("is_critical")
        self.assertEqual(len(criticals), 1)

    def test_point_action_view_checks(self):
        """action_view_checks 應回傳帶有 domain 與 context 的 action。"""
        point = self._make_point()
        action = point.action_view_checks()
        self.assertEqual(action["res_model"], "mfg_custom.quality.check")
        self.assertIn(("point_id", "=", point.id), action["domain"])
        self.assertEqual(action["context"]["default_point_id"], point.id)

    def test_point_value_range_validation(self):
        """檢項 min_value > max_value 應拋 ValidationError。"""
        point = self._make_point()
        with self.assertRaises(ValidationError):
            self.PointLine.create(
                {
                    "point_id": point.id,
                    "name": "錯誤上下限",
                    "min_value": 100.0,
                    "max_value": 5.0,
                },
            )

    def test_point_sample_qty_validation(self):
        """sample_qty < 1 應拋 ValidationError。"""
        with self.assertRaises(ValidationError):
            self._make_point(sample_qty=0)

    def test_point_product_category_consistency(self):
        """產品／分類一致性檢查：分類與產品所屬分類不一致應拋錯。"""
        other_category = self.env["product.category"].create({"name": "QA-Other"})
        with self.assertRaises(ValidationError):
            self._make_point(product_category_id=other_category.id)
