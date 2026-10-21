# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install", "mfg_custom", "plm_custom")
class TestMfgQualityCheckLine(TransactionCase):
    """測試 :class:`MfgQualityCheckLine` 之 onchange 與上下限邏輯。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Check = cls.env["mfg_custom.quality.check"]
        cls.CheckLine = cls.env["mfg_custom.quality.check.line"]
        cls.Point = cls.env["mfg_custom.quality.point"]
        cls.PointLine = cls.env["mfg_custom.quality.point.line"]
        cls.Product = cls.env["product.product"]
        cls.UoM = cls.env["uom.uom"]
        cls.product = cls.Product.create({"name": "Line-Test Product", "type": "consu"})
        cls.point = cls.Point.create(
            {
                "name": "Line 規格",
                "product_id": cls.product.id,
            },
        )
        cls.check = cls.Check.create(
            {
                "point_id": cls.point.id,
                "product_id": cls.product.id,
                "qty_to_check": 1.0,
            },
        )

    def _make_line(self, **extra):
        vals = {
            "check_id": self.check.id,
            "name": "直徑",
            "min_value": 5.0,
            "max_value": 10.0,
        }
        vals.update(extra)
        return self.CheckLine.create(vals)

    def test_onchange_in_range_sets_ok(self):
        """量測值在上下限內，onchange 將 result 預設為 ok。"""
        line = self._make_line(measured_value=7.5, result="pending")
        line._onchange_measured_value()
        self.assertEqual(line.result, "ok")

    def test_onchange_out_of_range_sets_fail(self):
        """量測值超出上下限，onchange 預設 result=fail。"""
        line = self._make_line(measured_value=12.0, result="pending")
        line._onchange_measured_value()
        self.assertEqual(line.result, "fail")

    def test_onchange_no_limits_no_change(self):
        """未設上下限時不變動 result。"""
        line = self._make_line(min_value=0.0, max_value=0.0, measured_value=42.0)
        line._onchange_measured_value()
        self.assertEqual(line.result, "pending")

    def test_value_range_constraint(self):
        """直接給下限 > 上限的檢項 → 拋 ValidationError。"""
        with self.assertRaises(ValidationError):
            self._make_line(min_value=100.0, max_value=1.0)

    def test_user_can_override_result(self):
        """即使上下限不在範圍內，使用者仍可手動改 result。

        onchange 只在 ``result == 'pending'`` 時變動；非 pending 不覆蓋。
        """
        line = self._make_line(
            measured_value=12.0, result="ok", min_value=5.0, max_value=10.0,
        )
        line._onchange_measured_value()
        self.assertEqual(
            line.result,
            "ok",
            "使用者已標示為 ok 時，onchange 不可改為 fail",
        )
