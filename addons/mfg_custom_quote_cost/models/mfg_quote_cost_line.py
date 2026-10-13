# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class MfgCustomQuoteCostLine(models.Model):
    """報價成本展開明細.

    儲存從 BOM 遞迴展開的每一筆成本項目（材料、委外、人工、製造費用、包裝、其他）。
    """

    _name = "mfg_custom.quote.cost.line"
    _description = "報價成本展開明細"
    _order = "sale_order_line_id, level, sequence, id"

    sale_order_line_id = fields.Many2one(
        "sale.order.line",
        required=True,
        ondelete="cascade",
        index=True,
    )
    level = fields.Integer(
        "層級",
        default=0,
        help="BOM 展開層級，0=主件本身。",
    )
    sequence = fields.Integer(default=10)
    product_id = fields.Many2one(
        "product.product",
        "元件",
        required=True,
    )
    product_qty = fields.Float(
        "數量",
        digits="Product Unit",
        required=True,
    )
    uom_id = fields.Many2one("uom.uom", "單位")
    unit_cost = fields.Monetary(
        "單價",
        currency_field="currency_id",
    )
    subtotal = fields.Monetary(
        "小計",
        currency_field="currency_id",
        compute="_compute_subtotal",
        store=True,
    )
    cost_type = fields.Selection(
        [
            ("material", "材料"),
            ("subcontract", "委外加工"),
            ("labor", "人工"),
            ("overhead", "製造費用"),
            ("packaging", "包裝"),
            ("other", "其他"),
        ],
        string="成本類型",
        required=True,
        index=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        default=lambda self: self.env.company.currency_id,
    )
    source = fields.Selection(
        [("bom", "BOM 自動"), ("manual", "手動加成")],
        default="bom",
        required=True,
    )
    note = fields.Char("備註")

    _cost_line_level_idx = models.Index("(sale_order_line_id, level, cost_type)")

    @api.depends("unit_cost", "product_qty")
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.unit_cost * line.product_qty
