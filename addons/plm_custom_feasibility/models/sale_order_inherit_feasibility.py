# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    """為 ``sale.order`` 加上「建立可行性評估」入口。

    從 SO form 上的 smart button 點擊後，會帶入客戶、預設產品與數量，
    並開啟 ``plm_custom.feasibility.wizard`` 讓使用者確認後建立評估單。
    """

    _inherit = "sale.order"

    feasibility_count = fields.Integer(
        "可行性評估數",
        compute="_compute_feasibility_count",
    )

    def _compute_feasibility_count(self):
        Feasibility = self.env["plm_custom.feasibility"]
        for order in self:
            order.feasibility_count = Feasibility.search_count(
                [
                    ("source_model", "=", "sale.order"),
                    ("source_id", "=", order.id),
                ]
            )

    def action_open_feasibility_wizard(self):
        """從 SO 開啟可行性評估 wizard。"""
        self.ensure_one()
        if not self.partner_id:
            raise UserError(self.env._("此銷售訂單未指定客戶，無法建立可行性評估"))
        # 預設帶第一筆明細的產品與數量（若無則留空，由 wizard 補）
        product = self.env["product.product"]
        qty = 1.0
        if self.order_line:
            first_line = self.order_line[0]
            if first_line.product_id:
                product = first_line.product_id
            if first_line.product_uom_qty:
                qty = first_line.product_uom_qty
        wizard = self.env["plm_custom.feasibility.wizard"].create({
            "source_model": "sale.order",
            "source_id": self.id,
            "product_id": product.id,
            "product_qty": qty,
        })
        return {
            "type": "ir.actions.act_window",
            "res_model": "plm_custom.feasibility.wizard",
            "res_id": wizard.id,
            "view_mode": "form",
            "view_id": self.env.ref(
                "plm_custom_feasibility.plm_feasibility_wizard_view_form"
            ).id,
            "target": "new",
            "context": dict(self.env.context),
        }

    def action_view_feasibility(self):
        """從 SO 檢視既有的可行性評估（若無則提示）。"""
        self.ensure_one()
        feasibilities = self.env["plm_custom.feasibility"].search(
            [
                ("source_model", "=", "sale.order"),
                ("source_id", "=", self.id),
            ]
        )
        if not feasibilities:
            raise UserError(self.env._("此銷售訂單尚未建立可行性評估"))
        return {
            "type": "ir.actions.act_window",
            "res_model": "plm_custom.feasibility",
            "view_mode": "list,form",
            "domain": [("id", "in", feasibilities.ids)],
            "context": dict(self.env.context),
        }
