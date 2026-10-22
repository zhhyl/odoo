# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


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
            ("skipped", "略過"),
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

    def write(self, vals):
        """只有簽核者本人（或管理員）可以變更簽核決策。"""
        decision_fields = {"decision", "decision_date", "comment"}
        if decision_fields & set(vals):
            for line in self:
                if not line._can_manage():
                    raise AccessError(
                        self.env._(
                            "您只能變更自己的簽核紀錄（關卡 %s）",
                            line.step_id.display_name,
                        )
                    )
        return super().write(vals)

    def _engine_write(self, vals):
        """簽核引擎內部寫入（略過 ``write()`` 的保護）。

        以底線開頭，無法透過 RPC 呼叫，僅供引擎內部使用
        （例如關卡由一人核准後，自動略過其他人的待簽紀錄）。
        """
        return super().write(vals)

    def unlink(self):
        """只有申請人（或管理員）可以刪除簽核紀錄。"""
        for line in self:
            is_requester = (
                line.request_id.requester_id
                and line.request_id.requester_id == self.env.user
            )
            if not is_requester and not line._can_manage():
                raise AccessError(
                    self.env._("您只能刪除自己提出的簽核申請之紀錄")
                )
        return super().unlink()

    def _can_manage(self):
        """目前使用者是否可管理（修改 / 刪除）這筆簽核紀錄。"""
        self.ensure_one()
        return (
            self.env.user == self.user_id
            or self.env.user.has_group("mfg_custom_base.group_manager")
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
