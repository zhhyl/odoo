# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.tests import tagged
from odoo.tests.common import BaseCommon


@tagged("post_install", "-at_install")
class TestPlmFeasibilityWizard(BaseCommon):
    """測試從銷售訂單建立可行性評估的 wizard。"""

    _test_user_groups = (
        "base.group_user",
        "mfg_custom_base.group_manager",
    )

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.SaleOrder = cls.env["sale.order"]
        cls.Wizard = cls.env["plm_custom.feasibility.wizard"]
        cls.Feasibility = cls.env["plm_custom.feasibility"]
        cls.partner = cls.env["res.partner"].create({"name": "Wizard Customer"})
        cls.product = cls.env["product.product"].create({"name": "Wizard Product"})

    def _make_so(self):
        return self.SaleOrder.create({
            "partner_id": self.partner.id,
            "order_line": [
                (0, 0, {
                    "product_id": self.product.id,
                    "product_uom_qty": 5,
                }),
            ],
        })

    def test_01_wizard_create_from_so(self):
        """wizard 從 SO 建立 → feasibility 帶正確 partner/product。"""
        so = self._make_so()
        wizard = self.Wizard.create({
            "source_model": "sale.order",
            "source_id": so.id,
            "product_id": self.product.id,
            "product_qty": 5.0,
        })
        result = wizard.action_create_feasibility()
        self.assertEqual(result["res_model"], "plm_custom.feasibility")
        self.assertEqual(result["type"], "ir.actions.act_window")

        new_id = result["res_id"]
        rec = self.Feasibility.browse(new_id)
        self.assertEqual(rec.partner_id, self.partner)
        self.assertEqual(rec.product_id, self.product)
        self.assertEqual(rec.product_qty, 5.0)
        self.assertEqual(rec.source_model, "sale.order")
        self.assertEqual(rec.source_id, so.id)
        self.assertEqual(rec.state, "draft")

    def test_02_sale_order_button_opens_wizard(self):
        """SO 上的 action_open_feasibility_wizard 應建立 wizard。"""
        so = self._make_so()
        result = so.action_open_feasibility_wizard()
        self.assertEqual(result["res_model"], "plm_custom.feasibility.wizard")
        self.assertEqual(result["target"], "new")
        wiz = self.env["plm_custom.feasibility.wizard"].browse(result["res_id"])
        self.assertEqual(wiz.source_model, "sale.order")
        self.assertEqual(wiz.source_id, so.id)
        # 預設帶入第一筆 SO line 的產品與數量
        self.assertEqual(wiz.product_id, self.product)
        self.assertEqual(wiz.product_qty, 5.0)

    def test_03_sale_order_feasibility_count(self):
        """feasibility_count 應隨 feasibility 建立而增加。"""
        so = self._make_so()
        self.assertEqual(so.feasibility_count, 0)
        self.Feasibility.create({
            "source_model": "sale.order",
            "source_id": so.id,
            "partner_id": self.partner.id,
            "product_id": self.product.id,
        })
        self.assertEqual(so.feasibility_count, 1)
