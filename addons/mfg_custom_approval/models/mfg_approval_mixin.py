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
    # 繼承 mail.thread：簽核流程需要發送 chatter 訊息與通知信，
    # 且與其它 mixin（mail.activity.mixin / rating.mixin）的 MRO 相容。
    _inherit = ["mail.thread"]

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
    approval_rule_id = fields.Many2one(
        "mfg_custom.approval.rule",
        "簽核規則",
        compute="_compute_approval_rule",
        help="依目前單據內容符合的簽核規則（尚未送出簽核時也能預覽）。",
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

    @api.depends_context("company")
    def _compute_approval_rule(self):
        """預覽此單據符合的簽核規則（僅顯示用，不會建立任何紀錄）。"""
        Rule = self.env["mfg_custom.approval.rule"]
        for rec in self:
            rec.approval_rule_id = Rule._match_rule(rec._name, rec)

    def _get_approval_rule_domain(self):
        """子模型可覆寫：回傳用以匹配 ``approval.rule`` 的額外 domain。

        預設回傳空 list。回傳值會以 AND 方式加入 rule 本身的 domain，
        由 ``mfg_custom.approval.rule._match_rule()`` 呼叫。
        """
        return []

    def _approval_before_submit(self):
        """送出簽核前的業務檢查 hook（預設無動作）。

        子模型可覆寫此方法做送簽前的資料檢查，檢查不通過時應 raise UserError。
        """
        return True

    def _approval_on_approved(self):
        """簽核全部通過時的業務回寫 hook（預設無動作）。

        子模型可覆寫此方法，把業務單據的狀態更新為「已核准」等。
        引擎只會在 request 真的進入 approved 狀態後呼叫本方法。
        """
        return True

    def _approval_on_rejected(self):
        """簽核被駁回時的業務回寫 hook（預設無動作）。"""
        return True

    def _approval_on_cancelled(self):
        """簽核被取消時的業務回寫 hook（預設無動作）。"""
        return True

    def action_submit_for_approval(self, rule=None):
        """送出簽核：建立 ``mfg_custom.approval.request`` 並掛回 mixin。

        若本單已有簽核單且不在「待簽核」狀態（已駁回 / 已取消 / 已核准），
        會直接重用該簽核單並重啟流程，讓使用者不需要重建單據。

        :param rule: 可指定 ``mfg_custom.approval.rule`` 紀錄；
                     若未提供則依 ``_match_rule`` 自動尋找。
        """
        for rec in self:
            request = rec.approval_request_id
            if request and request.state == "pending":
                raise UserError(
                    self.env._(
                        "此單已有進行中的簽核申請：%s", request.display_name
                    )
                )
            # 用區域變數，避免多筆資料時沿用前一筆的簽核規則
            rec_rule = rule
            if not rec_rule:
                rec_rule = self.env["mfg_custom.approval.rule"]._match_rule(
                    rec._name, rec
                )
            if not rec_rule:
                raise UserError(
                    self.env._(
                        "此單據（%s）尚未設定簽核規則，無法送出簽核。\n"
                        "請聯絡管理員於【MFG Custom > 設定 > 簽核規則】建立規則。",
                        rec._name,
                    )
                )
            rec._approval_before_submit()
            if request and request.exists():
                # 重用既有簽核單：重啟流程（駁回後重送 / 核准後再走第二輪）
                request._restart(rule=rec_rule)
                rec.approval_request_id = request
                rec.sudo().message_post(
                    body=self.env._(
                        "已重新送出簽核申請：%s（%d 個關卡）",
                        request.display_name,
                        len(rec_rule.step_ids),
                    ),
                    subtype_xmlid="mfg_custom_approval.mt_mfg_approval_state_changed",
                )
                continue
            request = self.env["mfg_custom.approval.request"].create({
                "rule_id": rec_rule.id,
                "res_model": rec._name,
                "res_id": rec.id,
            })
            rec.approval_request_id = request
            rec.sudo().message_post(
                body=self.env._(
                    "已送出簽核申請：%s（%d 個關卡）",
                    request.display_name,
                    len(rec_rule.step_ids),
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
                    self.env._(
                        "簽核單已是 %s 狀態，無法取消", rec.approval_request_id.state
                    )
                )
            if rec.approval_request_id.state == "rejected":
                # 已駁回的簽核單請改用「重新送出簽核」重啟流程
                raise UserError(
                    self.env._(
                        "簽核單已被駁回，請直接重新送出簽核以重啟流程。"
                    )
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
