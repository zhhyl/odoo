# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class MfgProductionStageChange(models.TransientModel):
    """變更製造工單生產階段的確認視窗。

    由 MO 表單的「變更生產階段」按鈕開啟；確認後呼叫
    ``mrp.production.action_change_stage()``，階段變更日誌會一併寫入。
    """

    _name = "mfg.production.stage.change"
    _description = "變更 MO 生產階段"

    production_id = fields.Many2one(
        "mrp.production",
        "製造工單",
        required=True,
        readonly=True,
    )
    new_stage = fields.Selection(
        [
            ("sample", "樣品"),
            ("pilot", "小批量 / 試量產"),
            ("mass", "量產"),
        ],
        string="新階段",
        required=True,
        default="mass",
    )
    reason = fields.Char(
        "變更原因",
        help="選填：會記錄在階段變更日誌中。",
    )

    def action_confirm(self):
        """套用新階段（並寫入階段變更日誌）後關閉視窗。"""
        self.ensure_one()
        self.production_id.action_change_stage(self.new_stage, self.reason)
        return {"type": "ir.actions.act_window_close"}
