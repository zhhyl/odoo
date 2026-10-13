# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class MfgApprovalLine(models.Model):
    """簽核紀錄.

    每個 ``approval.request`` 為每個 ``approval.step`` 的每個潛在簽核者建立一筆 line。
    """

    _name = "mfg_custom.approval.line"
    _description = "MFG Custom 簽核紀錄"
    _order = "step_id, user_id, id"

    request_id = fields.Many2one(
        "mfg_custom.approval.request",
        "簽核申請",
        required=True,
        ondelete="cascade",
        index=True,
    )
    step_id = fields.Many2one(
        "mfg_custom.approval.step",
        "簽核關卡",
        required=True,
        index=True,
    )
    user_id = fields.Many2one(
        "res.users",
        "簽核者",
        required=True,
        index=True,
    )
    decision = fields.Selection(
        [
            ("pending", "待簽"),
            ("approved", "核准"),
            ("rejected", "駁回"),
        ],
        default="pending",
        required=True,
        index=True,
    )
    decision_date = fields.Datetime("決策時間")
    comment = fields.Text("意見")

    _line_req_idx = models.Index("(request_id, decision)")
    _line_user_uniq = models.Constraint(
        "UNIQUE(request_id, step_id, user_id)",
        "同一關卡同一簽核者只能有一筆紀錄。",
    )

    @api.constrains("user_id")
    def _check_user_active(self):
        for line in self:
            if not line.user_id.active:
                raise ValidationError(
                    self.env._(
                        "簽核者 %s 已停用，無法作為潛在簽核者",
                        line.user_id.display_name,
                    )
                )

    def name_get(self):
        result = []
        for rec in self:
            label = self.env._(
                "%(step)s / %(user)s",
                step=rec.step_id.display_name or "",
                user=rec.user_id.display_name or "",
            )
            result.append((rec.id, label))
        return result
