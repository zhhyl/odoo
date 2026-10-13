# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class MfgApprovalMixin(models.AbstractModel):
    """MFG Custom 通用簽核 mixin.

    為任何需要走多層簽核的業務模型提供：

    * ``approval_request_id`` 指向一份 ``mfg_custom.approval.request``
    * ``approval_state`` 從 request.state 計算出來（無需簽核 / 待簽核 / 已核准 / 已駁回）
    * ``action_submit_for_approval()`` 建立簽核申請
    * ``action_approve_current_step()`` 簽核當前關卡
    * ``action_reject_current_step()`` 駁回當前關卡

    子模型需在 ``_inherit`` 中加入此 mixin，並在 form view 加上對應按鈕。
    """

    _name = "mfg_custom.approval.mixin"
    _description = "MFG Custom 簽核 mixin"

    approval_request_id = fields.Many2one(
        "mfg_custom.approval.request",
        "簽核單",
        copy=False,
        readonly=True,
        ondelete="set null",
    )
    approval_state = fields.Selection(
        [
            ("not_required", "無需簽核"),
            ("pending", "待簽核"),
            ("approved", "已核准"),
            ("rejected", "已駁回"),
        ],
        string="簽核狀態",
        compute="_compute_approval_state",
        store=True,
        index=True,
    )

    @api.depends("approval_request_id", "approval_request_id.state")
    def _compute_approval_state(self):
        """由所屬簽核申請的 state 推導 approval_state。"""
        state_map = {
            "draft": "pending",
            "pending": "pending",
            "approved": "approved",
            "rejected": "rejected",
            "cancelled": "not_required",
        }
        for rec in self:
            if not rec.approval_request_id:
                rec.approval_state = "not_required"
            else:
                rec.approval_state = state_map.get(
                    rec.approval_request_id.state, "not_required"
                )

    def _get_approval_rule_domain(self):
        """子模型可覆寫：回傳用以匹配 ``approval.rule`` 的額外 domain。

        預設回傳空 list。回傳值會以 AND 方式加入 rule 本身的 domain。
        """
        return []

    def action_submit_for_approval(self, rule=None):
        """送出簽核：建立 ``mfg_custom.approval.request`` 並掛回 mixin。

        :param rule: 可指定 ``mfg_custom.approval.rule`` 紀錄；
                     若未提供則依 ``_match_rule`` 自動尋找。
        """
        for rec in self:
            if rec.approval_request_id and rec.approval_request_id.state == "pending":
                raise UserError(
                    self.env._("此單已有進行中的簽核申請：%s", rec.approval_request_id.display_name)
                )
            if not rule:
                rule = self.env["mfg_custom.approval.rule"]._match_rule(
                    rec._name, rec
                )
            if not rule:
                raise UserError(
                    self.env._("找不到適用於 %s 的簽核規則", rec._name)
                )
            request = self.env["mfg_custom.approval.request"].create({
                "rule_id": rule.id,
                "res_model": rec._name,
                "res_id": rec.id,
            })
            rec.approval_request_id = request
            rec.message_post(
                body=self.env._(
                    "已送出簽核申請：%s（%d 個關卡）",
                    request.display_name,
                    len(rule.step_ids),
                ),
                subtype_xmlid="mfg_custom_approval.mt_mfg_approval_state_changed",
            )

    def action_approve_current_step(self):
        """由 mixin 端呼叫，內部委派給所屬 request。"""
        for rec in self:
            if not rec.approval_request_id:
                raise UserError(self.env._("此單目前沒有簽核申請"))
            rec.approval_request_id.action_approve()

    def action_reject_current_step(self, reason=""):
        """由 mixin 端呼叫，內部委派給所屬 request。"""
        for rec in self:
            if not rec.approval_request_id:
                raise UserError(self.env._("此單目前沒有簽核申請"))
            rec.approval_request_id.action_reject(reason=reason)

    def action_cancel_approval(self):
        """取消整個簽核流程。"""
        for rec in self:
            if not rec.approval_request_id:
                return
            if rec.approval_request_id.state in ("approved", "cancelled"):
                raise UserError(
                    self.env._("簽核單已是 %s 狀態，無法取消", rec.approval_request_id.state)
                )
            rec.approval_request_id.action_cancel()

    @api.constrains("approval_request_id")
    def _check_approval_request_model(self):
        """確保 ``approval_request_id.res_model`` 與 self 一致。"""
        for rec in self:
            if (
                rec.approval_request_id
                and rec.approval_request_id.res_model != rec._name
            ):
                raise ValidationError(
                    self.env._(
                        "簽核申請的 model (%s) 與本單的 model (%s) 不符",
                        rec.approval_request_id.res_model,
                        rec._name,
                    )
                )
