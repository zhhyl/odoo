# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, fields, models


class PlmCustomEcoLine(models.Model):
    """ECO 影響清單。"""

    _name = "plm_custom.eco.line"
    _description = "PLM Custom ECO 影響清單"
    _order = "eco_id, impact_type, id"

    eco_id = fields.Many2one(
        "plm_custom.eco",
        required=True,
        ondelete="cascade",
        index=True,
    )
    impact_type = fields.Selection(
        [
            ("sale", "銷售"),
            ("production", "生產"),
            ("inventory", "庫存"),
            ("document", "文件"),
            ("supplier", "供應商"),
            ("other", "其他"),
        ],
        required=True,
        index=True,
    )
    res_model = fields.Char("影響對象 Model", required=True)
    res_id = fields.Integer("影響對象 ID", required=True)
    description = fields.Char("說明", required=True)
    handled = fields.Boolean("已處置", default=False, index=True)
    handler_id = fields.Many2one("res.users", "處置者")

    _line_eco_idx = models.Index("(eco_id, impact_type, handled)")
