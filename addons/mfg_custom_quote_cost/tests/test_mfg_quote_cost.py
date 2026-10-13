# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install", "mfg_custom", "plm_custom")
class TestMfgCustomQuoteCost(TransactionCase):
    """測試 mfg_custom_quote_cost 模組的成本展開邏輯。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.CostLine = cls.env["mfg_custom.quote.cost.line"]
        cls.currency = cls.env.company.currency_id

    def test_01_compute_subtotal(self):
        """subtotal = unit_cost × product_qty。"""
        line = self.CostLine.create({
            "product_id": self.env.ref("product.product_product_4").id,
            "product_qty": 3.0,
            "unit_cost": 12.5,
            "cost_type": "material",
        })
        self.assertAlmostEqual(line.subtotal, 37.5, places=2)

    def test_02_suggested_price_formula(self):
        """target_margin=20, cost=80 → suggested_price=100。"""
        so = self.env["sale.order"].create({
            "partner_id": self.env.ref("base.res_partner_4").id,
        })
        sol = self.env["sale.order.line"].create({
            "order_id": so.id,
            "product_id": self.env.ref("product.product_product_4").id,
            "product_uom_qty": 1.0,
            "price_unit": 100.0,
        })
        sol.write({
            "mfg_custom_cost_explosion_total": 80.0,
            "mfg_custom_target_margin_percent": 20.0,
        })
        sol.invalidate_recordset()
        self.assertAlmostEqual(sol.mfg_custom_suggested_price, 100.0, places=2)

    def test_03_suggested_price_zero_when_margin_100(self):
        """target_margin=100 → suggested_price=0。"""
        so = self.env["sale.order"].create({
            "partner_id": self.env.ref("base.res_partner_4").id,
        })
        sol = self.env["sale.order.line"].create({
            "order_id": so.id,
            "product_id": self.env.ref("product.product_product_4").id,
            "product_uom_qty": 1.0,
            "price_unit": 100.0,
        })
        sol.write({
            "mfg_custom_cost_explosion_total": 50.0,
            "mfg_custom_target_margin_percent": 100.0,
        })
        sol.invalidate_recordset()
        self.assertEqual(sol.mfg_custom_suggested_price, 0.0)

    def test_04_subtotal_stored(self):
        """建立後 subtotal 應自動 store=True 計算。"""
        line = self.CostLine.create({
            "product_id": self.env.ref("product.product_product_4").id,
            "product_qty": 2.0,
            "unit_cost": 50.0,
            "cost_type": "labor",
        })
        line.flush_recordset()
        self.assertAlmostEqual(line.read(["subtotal"])[0]["subtotal"], 100.0, places=2)

    def test_05_wizard_requires_at_least_one_line(self):
        """wizard 無勾選任何行時 explode 應拋錯。"""
        wizard = self.env["mfg_custom.quote.cost.wizard"].create({})
        with self.assertRaises(Exception):
            wizard.action_explode()
