# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class MfgCustomQuoteCostWizard(models.TransientModel):
    _name = "mfg_custom.quote.cost.wizard"
    _description = "報價 BOM 成本展開"

    sale_order_id = fields.Many2one("sale.order")
    line_ids = fields.One2many(
        "mfg_custom.quote.cost.wizard.line",
        "wizard_id",
        string="要展開的明細",
    )

    def action_explode(self):
        """跑 BOM 展開。"""
        self.ensure_one()
        if not self.line_ids:
            raise UserError(self.env._("請至少勾選一筆明細展開"))
        Bom = self.env["mrp.bom"]
        for line in self.line_ids.filtered("include"):
            sol = line.sale_order_line_id
            bom = Bom._bom_find(
                sol.product_id,
                company_id=sol.company_id.id,
                bom_type="normal",
            )
            if not bom:
                raise UserError(
                    self.env._(
                        "%s 找不到 BOM，無法展開成本",
                        sol.product_id.display_name,
                    )
                )
            cost_lines = self._explode_bom(bom, sol.product_uom_qty, level=0)
            sol.write({
                "mfg_custom_cost_explosion_ids": [(5, 0, 0)] + [
                    (0, 0, v) for v in cost_lines
                ],
                "mfg_custom_cost_explosion_date": fields.Datetime.now(),
            })
        return {"type": "ir.actions.act_window_close"}

    def _explode_bom(self, bom, qty, level, visited=None):
        """遞迴展開 BOM，回傳 cost line vals 清單。"""
        if visited is None:
            visited = set()
        if bom.id in visited:
            return []
        visited = visited | {bom.id}
        lines = []
        for bom_line in bom.bom_line_ids:
            product = bom_line.product_id
            if not product:
                continue
            needed = bom_line.product_qty * qty
            lines.append({
                "level": level + 1,
                "product_id": product.id,
                "product_qty": needed,
                "uom_id": bom_line.product_uom_id.id,
                "unit_cost": product.standard_price,
                "cost_type": "material",
                "source": "bom",
                "note": f"BOM {bom.code or bom.display_name} 第 {level + 1} 層",
            })
            sub_bom = self.env["mrp.bom"]._bom_find(
                product,
                company_id=bom.company_id.id,
                bom_type="normal",
            )
            if sub_bom:
                lines.extend(self._explode_bom(sub_bom, needed, level + 1, visited))
        for op in bom.operation_ids:
            hour_cost = op.workcenter_id.costs_hour if op.workcenter_id else 0.0
            time_hours = (op.time_cycle * qty) / 60.0
            lines.append({
                "level": level + 1,
                "product_id": bom.product_id.id,
                "product_qty": time_hours,
                "uom_id": False,
                "unit_cost": hour_cost,
                "cost_type": "labor",
                "source": "bom",
                "note": self.env._(
                    "工序 %s %.2fmin × %.2f 單位",
                    op.name,
                    op.time_cycle or 0.0,
                    qty,
                ),
            })
        return lines


class MfgCustomQuoteCostWizardLine(models.TransientModel):
    _name = "mfg_custom.quote.cost.wizard.line"
    _description = "報價成本展開 wizard 行"

    wizard_id = fields.Many2one(
        "mfg_custom.quote.cost.wizard",
        required=True,
        ondelete="cascade",
    )
    sale_order_line_id = fields.Many2one(
        "sale.order.line",
        required=True,
    )
    product_id = fields.Many2one("product.product", required=True)
    include = fields.Boolean("展開", default=True)
