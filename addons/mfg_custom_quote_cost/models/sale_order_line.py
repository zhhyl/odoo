# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    mfg_custom_cost_explosion_ids = fields.One2many(
        "mfg_custom.quote.cost.line",
        "sale_order_line_id",
        string="成本展開",
    )
    mfg_custom_cost_explosion_total = fields.Monetary(
        "成本底價",
        compute="_compute_mfg_custom_cost_explosion_total",
        store=True,
        currency_field="currency_id",
    )
    mfg_custom_cost_explosion_date = fields.Datetime("最後展開時間")
    mfg_custom_target_margin_percent = fields.Float(
        "目標毛利率 %",
        default=20.0,
        help="建議報價 = 成本底價 / (1 - 毛利率%)",
    )
    mfg_custom_suggested_price = fields.Monetary(
        "建議報價",
        compute="_compute_mfg_custom_suggested_price",
        store=True,
        currency_field="currency_id",
    )

    @api.depends("mfg_custom_cost_explosion_ids.subtotal")
    def _compute_mfg_custom_cost_explosion_total(self):
        for line in self:
            line.mfg_custom_cost_explosion_total = sum(
                line.mfg_custom_cost_explosion_ids.mapped("subtotal")
            )

    @api.depends(
        "mfg_custom_cost_explosion_total",
        "mfg_custom_target_margin_percent",
    )
    def _compute_mfg_custom_suggested_price(self):
        for line in self:
            margin = line.mfg_custom_target_margin_percent or 0.0
            if 0 <= margin < 100:
                line.mfg_custom_suggested_price = (
                    line.mfg_custom_cost_explosion_total / (1 - margin / 100.0)
                )
            else:
                line.mfg_custom_suggested_price = 0.0

    def action_explode_cost(self):
        """快速入口：呼叫 wizard 展開當前行的成本。"""
        self.ensure_one()
        wizard = self.env["mfg_custom.quote.cost.wizard"].create({
            "sale_order_id": self.order_id.id,
            "line_ids": [(0, 0, {
                "sale_order_line_id": self.id,
                "product_id": self.product_id.id,
                "include": True,
            })],
        })
        return {
            "type": "ir.actions.act_window",
            "res_model": "mfg_custom.quote.cost.wizard",
            "view_mode": "form",
            "res_id": wizard.id,
            "target": "new",
        }
