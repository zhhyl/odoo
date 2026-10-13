# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class MrpProductionStageLog(models.Model):
    """記錄 ``mrp.production.mfg_custom_production_stage`` 的每一次變更。

    用於「樣品 → 小批量 → 量產」升版路徑的稽核。
    """

    _name = "mrp.production.stage.log"
    _description = "MO 生產階段變更日誌"
    _order = "timestamp desc, id desc"
    _rec_name = "to_stage"

    production_id = fields.Many2one(
        "mrp.production",
        "製造工單",
        required=True,
        ondelete="cascade",
        index=True,
    )
    from_stage = fields.Selection(
        [
            ("sample", "樣品"),
            ("pilot", "小批量 / 試量產"),
            ("mass", "量產"),
        ],
        "原階段",
    )
    to_stage = fields.Selection(
        [
            ("sample", "樣品"),
            ("pilot", "小批量 / 試量產"),
            ("mass", "量產"),
        ],
        "新階段",
        required=True,
    )
    user_id = fields.Many2one(
        "res.users",
        "變更人",
        default=lambda self: self.env.user,
        index=True,
    )
    timestamp = fields.Datetime(
        "變更時間",
        default=fields.Datetime.now,
        required=True,
    )
    reason = fields.Char("變更原因")

    _log_production_idx = models.Index("(production_id, timestamp)")
