# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models


class PlmFeasibilityWizard(models.TransientModel):
    """從銷售訂單 / 銷售明細建立可行性評估的 wizard.

    由 SO 或 SO line 上的「建立可行性評估」按鈕觸發，
    預先帶入客戶、產品、數量等資訊，確認後建立 ``plm_custom.feasibility``。
    """

    _name = "plm_custom.feasibility.wizard"
    _description = "PLM Custom 可行性評估建立 wizard"

    source_model = fields.Selection(
        [
            ("sale.order", "銷售訂單"),
            ("sale.order.line", "銷售明細"),
        ],
        string="來源",
        required=True,
    )
    source_id = fields.Integer(
        "來源 ID",
        required=True,
    )
    product_id = fields.Many2one(
        "product.product",
        "產品",
        required=True,
    )
    product_qty = fields.Float(
        "預估數量",
        digits="Product Unit",
        default=1.0,
        required=True,
    )
    bom_id = fields.Many2one(
        "mrp.bom",
        "候選 BOM",
        domain="[('product_tmpl_id', '=', product_id.product_tmpl_id)]",
    )

    def action_create_feasibility(self):
        """建立可行性評估並返回 form view。"""
        self.ensure_one()
        vals = self._prepare_feasibility_vals()
        feasibility = self.env["plm_custom.feasibility"].create(vals)
        return {
            "type": "ir.actions.act_window",
            "res_model": "plm_custom.feasibility",
            "res_id": feasibility.id,
            "view_mode": "form",
            "view_id": self.env.ref(
                "plm_custom_feasibility.plm_feasibility_view_form"
            ).id,
            "target": "current",
        }

    def _prepare_feasibility_vals(self):
        """依 wizard 內容組裝可行性評估 vals。"""
        self.ensure_one()
        if self.source_model == "sale.order":
            source = self.env["sale.order"].browse(self.source_id)
            partner = source.partner_id
        elif self.source_model == "sale.order.line":
            source = self.env["sale.order.line"].browse(self.source_id)
            partner = source.order_partner_id or source.order_id.partner_id
        else:  # pragma: no cover - 防禦性
            partner = self.env["res.partner"].browse()
        return {
            "source_model": self.source_model,
            "source_id": self.source_id,
            "partner_id": partner.id,
            "product_id": self.product_id.id,
            "product_qty": self.product_qty,
            "bom_id": self.bom_id.id or False,
            "user_id": self.env.user.id,
        }
