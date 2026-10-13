# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class MrpBom(models.Model):
    """擴充 mrp.bom：加入 BOM 預設生產階段欄位。"""

    _inherit = "mrp.bom"

    mfg_custom_default_production_stage = fields.Selection(
        [
            ("sample", "樣品"),
            ("pilot", "小批量 / 試量產"),
            ("mass", "量產"),
        ],
        string="預設生產階段",
        default="mass",
        help="新建以此 BOM 為基準的 MO 時，自動帶入的生產階段。",
    )
