# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class MfgApprovalRequest(models.Model):
    """簽核申請.

    一份 ``approval.request`` 對應到一筆業務單據（透過 ``res_model`` / ``res_id``）。
    內含多個 ``approval.step`` 與多筆 ``approval.line``，組成一個有狀態的工作流。
    """

    _name = "mfg_custom.approval.request"
    _description = "MFG Custom 簽核申請"
    _inherit = ["mail.thread"]
    _order = "id desc"
    _rec_name = "name"

    name = fields.Char(
        "單號",
        default="New",
        readonly=True,
        copy=False,
    )
    rule_id = fields.Many2one(
        "mfg_custom.approval.rule",
        "簽核規則",
        required=True,
        ondelete="restrict",
    )
    res_model = fields.Char(
        "業務模型",
        required=True,
        index=True,
        help="被簽核的單據所屬技術模型。",
    )
    res_id = fields.Integer(
        "業務單據 ID",
        required=True,
        index=True,
    )
    state = fields.Selection(
        [
            ("draft", "草稿"),
            ("pending", "待簽核"),
            ("approved", "全部核准"),
            ("rejected", "被駁回"),
            ("cancelled", "取消"),
        ],
        default="pending",
        required=True,
        index=True,
        tracking=True,
    )
    line_ids = fields.One2many(
        "mfg_custom.approval.line",
        "request_id",
        "簽核紀錄",
    )
    current_step_id = fields.Many2one(
        "mfg_custom.approval.step",
        "當前關卡",
        compute="_compute_current_step",
        store=True,
    )
    current_step_no = fields.Integer(
        "當前關卡編號",
        compute="_compute_current_step",
        store=True,
    )
    reason = fields.Text("駁回原因", tracking=True)
    company_id = fields.Many2one(
        "res.company",
        "公司",
        default=lambda self: self.env.company,
        index=True,
    )
    requester_id = fields.Many2one(
        "res.users",
        "申請人",
        default=lambda self: self.env.user,
        tracking=True,
    )
    submit_date = fields.Datetime(
        "送出時間",
        default=fields.Datetime.now,
    )
    pending_approver_emails = fields.Char(
        "待簽核者信箱",
        compute="_compute_pending_approver_emails",
        help="目前待簽關卡的簽核者信箱，供通知信使用。",
    )
    res_display_name = fields.Char(
        "業務單據",
        compute="_compute_res_display_name",
        help="被簽核的業務單據名稱。",
    )

    _req_idx = models.Index("(state, res_model, res_id)")

    # 僅允許簽核引擎內部寫入的欄位。
    # 這些欄位決定「這張單走了哪些關卡、現在是什麼狀態」，
    # 一般使用者若能直接改寫等同跳過所有簽核關卡，因此一律拒絕。
    _engine_only_fields = {
        "state",
        "rule_id",
        "res_model",
        "res_id",
        "line_ids",
        "current_step_id",
        "current_step_no",
    }

    def write(self, vals):
        """拒絕直接改寫簽核流程欄位。

        簽核狀態只能透過「送出簽核 / 核准 / 駁回 / 取消」等動作推進，
        避免使用者直接改 ``state`` 就把未簽核的單據變成已核准。
        """
        forbidden = self._engine_only_fields & set(vals)
        if forbidden:
            raise AccessError(
                self.env._(
                    "簽核流程欄位（%s）不可直接修改，請使用送出簽核／核准／駁回等操作。",
                    "、".join(sorted(forbidden)),
                )
            )
        return super().write(vals)

    def _engine_write(self, vals):
        """簽核引擎內部寫入（略過 ``write()`` 的保護）。

        以底線開頭，無法透過 RPC 呼叫，僅供引擎內部使用。
        """
        return super().write(vals)

    def unlink(self):
        """只有申請人或管理員可以刪除簽核申請。"""
        for rec in self:
            is_requester = bool(
                rec.requester_id and rec.requester_id == self.env.user
            )
            if not is_requester and not self.env.user.has_group(
                "mfg_custom_base.group_manager"
            ):
                raise AccessError(
                    self.env._("只有申請人或管理員可以刪除簽核申請")
                )
        return super().unlink()

    @api.constrains("res_model")
    def _check_res_model_exists(self):
        for rec in self:
            if rec.res_model and rec.res_model not in self.env:
                raise ValidationError(
                    self.env._("業務模型 %s 不存在", rec.res_model)
                )

    @api.depends(
        "line_ids.user_id",
        "line_ids.decision",
        "line_ids.step_id",
        "current_step_id",
    )
    def _compute_pending_approver_emails(self):
        """目前關卡的待簽核者信箱（供通知信使用）。

        只取「當前關卡」的待簽核者，避免在送出簽核時就一次寄給後續所有關卡。
        """
        for rec in self:
            step = rec.current_step_id
            lines = rec.line_ids.filtered(
                lambda ln: ln.decision == "pending"
                and (not step or ln.step_id == step)
            )
            users = lines.mapped("user_id")
            rec.pending_approver_emails = ", ".join(
                [email for email in users.mapped("email") if email]
            )

    @api.depends("res_model", "res_id")
    def _compute_res_display_name(self):
        for rec in self:
            record = rec._get_res_record()
            # 以 sudo 讀取：簽核單本身對一般使用者可讀，
            # 不應因核准者無權讀取該業務單據而開不起簽核單。
            rec.res_display_name = (
                record.sudo().display_name
                if record and record.exists()
                else False
            )

    def action_open_res_record(self):
        """開啟被簽核的業務單據，方便簽核者檢視內容。

        回傳 action dict（不寫入資料庫，避免每次點擊都產生一筆 action 紀錄）。
        """
        self.ensure_one()
        record = self._get_res_record()
        if not record or not record.exists():
            raise UserError(self.env._("對應的業務單據已不存在"))
        return {
            "type": "ir.actions.act_window",
            "name": record.display_name or self.res_model,
            "res_model": self.res_model,
            "res_id": record.id,
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "current",
        }

    @api.model_create_multi
    def _check_no_active_duplicate(self, vals_list):
        """避免同一單據同時存在多份進行中的申請。"""
        for vals in vals_list:
            if vals.get("state", "pending") != "pending":
                continue
            domain = [
                ("res_model", "=", vals.get("res_model")),
                ("res_id", "=", vals.get("res_id")),
                ("state", "=", "pending"),
            ]
            company = vals.get("company_id")
            if company:
                domain.append(("company_id", "=", company))
            if self.search_count(domain):
                raise ValidationError(
                    self.env._("此單據已有進行中的簽核申請，請先取消或重置後再送出")
                )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "mfg_custom.approval.request"
                ) or "New"
        self._check_no_active_duplicate(vals_list)
        # 先驗證關卡與簽核者：避免寫入後才失敗，在資料庫留下孤兒簽核單
        for vals in vals_list:
            self._validate_steps(vals)
        records = super().create(vals_list)
        for rec in records:
            rec._build_lines()
            rec._notify_approvers()
        return records

    def _validate_steps(self, vals):
        """建立前檢查規則的關卡是否適用於此單據、且每個必要關卡都找得到簽核者。"""
        rule = self.env["mfg_custom.approval.rule"].browse(vals.get("rule_id"))
        if not rule.exists():
            raise UserError(self.env._("找不到對應的簽核規則"))
        res_model = vals.get("res_model")
        res_id = vals.get("res_id")
        if not res_model or not res_id:
            raise UserError(self.env._("簽核申請必須指定業務單據"))
        record = self.env[res_model].browse(res_id)
        self._resolve_steps_for_record(rule, record)
        return True

    # ------------------------------------------------------------------
    # Compute: 當前關卡
    # ------------------------------------------------------------------

    @api.depends("line_ids.decision", "line_ids.step_id", "rule_id.step_ids")
    def _compute_current_step(self):
        Step = self.env["mfg_custom.approval.step"]
        for rec in self:
            step = Step.browse()
            no = 0
            # 關卡編號以規則中的順序為準；只考慮「實際建立了簽核紀錄」的關卡
            # （金額門檻不符、或非必要而略過的關卡不算）。
            steps = rec.rule_id.step_ids.sorted("sequence")
            effective = rec._get_effective_steps()
            for idx, s in enumerate(steps, start=1):
                if s not in effective:
                    continue
                # 已完成的關卡（任一核准即可 / 全員核准）直接略過，
                # 否則同一關卡其他人員的待簽紀錄會讓流程卡在這一關。
                if rec._is_step_done(s):
                    continue
                if rec.line_ids.filtered(
                    lambda ln, s=s: ln.step_id == s and ln.decision == "pending"
                ):
                    step = s
                    no = idx
                    break
            if not step and effective:
                # 沒有待簽關卡：顯示第一個尚未完成的關卡
                for idx, s in enumerate(steps, start=1):
                    if s in effective and not rec._is_step_done(s):
                        step = s
                        no = idx
                        break
                if not step:
                    step = effective.sorted("sequence")[0]
                    no = 1
            rec.current_step_id = step
            rec.current_step_no = no

    # ------------------------------------------------------------------
    # Public actions
    # ------------------------------------------------------------------

    def action_approve(self):
        """由當前使用者核准目前關卡。"""
        for rec in self:
            rec._check_can_decide()
            step = rec.current_step_id
            if not step:
                raise UserError(self.env._("找不到當前關卡"))
            line = rec._get_pending_line()
            if not line:
                raise UserError(
                    self.env._("您不在本關卡的簽核者名單中，或已簽過")
                )
            line.write({
                "decision": "approved",
                "decision_date": fields.Datetime.now(),
            })
            rec._close_other_pending_lines(step)
            rec._post_step_progress_message(step)
            rec._check_all_approved()

    def action_reject(self, reason=""):
        """由當前使用者駁回目前關卡，整張申請進入 rejected 狀態。"""
        for rec in self:
            rec._check_can_decide()
            step = rec.current_step_id
            if not step:
                raise UserError(self.env._("找不到當前關卡"))
            line = rec._get_pending_line()
            if not line:
                raise UserError(
                    self.env._("您不在本關卡的簽核者名單中，或已簽過")
                )
            # 用區域變數，避免多筆資料時沿用前一筆的駁回原因
            rec_reason = reason or rec.reason
            line.write({
                "decision": "rejected",
                "decision_date": fields.Datetime.now(),
                "comment": rec_reason or line.comment,
            })
            if rec_reason:
                rec.write({"reason": rec_reason})
            rec._post_step_progress_message(step, note=rec_reason, approved=False)
            rec._engine_write({"state": "rejected"})
            rec._notify_business_record("_approval_on_rejected")
            rec._notify_decision()

    def action_cancel(self):
        """申請人主動取消整份簽核單。"""
        for rec in self:
            if rec.state in ("approved", "rejected", "cancelled"):
                continue
            rec._engine_write({"state": "cancelled"})
            rec.sudo().message_post(
                body=self.env._("簽核申請已取消"),
                subtype_xmlid="mfg_custom_approval.mt_mfg_approval_request_state",
            )
            rec._notify_business_record("_approval_on_cancelled")
            rec._notify_decision()

    def action_reset_to_draft(self):
        """將已取消或被駁回的申請重新打回 draft 並重建 line（供重送簽核用）。"""
        for rec in self:
            if rec.state not in ("cancelled", "rejected"):
                raise UserError(
                    self.env._("僅有「已取消」或「被駁回」狀態可重置為草稿")
                )
            rec._restart()

    def _restart(self, rule=None):
        """重啟簽核流程：清除既有紀錄並依規則重新建立簽核者。

        用於「駁回後重送」與「核准後再走第二輪簽核」。
        """
        self.ensure_one()
        # 簽核單本身擁有這些紀錄，重啟流程時由簽核單端刪除
        self.line_ids.sudo().unlink()
        vals = {
            "state": "draft",
            "reason": False,
            "submit_date": fields.Datetime.now(),
        }
        if rule:
            vals["rule_id"] = rule.id
        self._engine_write(vals)
        self._build_lines()
        self._engine_write({"state": "pending"})
        self._notify_approvers()
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_pending_line(self):
        """取得當前使用者在本關卡尚未決策的簽核紀錄。"""
        self.ensure_one()
        step = self.current_step_id
        return self.line_ids.filtered(
            lambda ln: ln.step_id == step
            and ln.user_id == self.env.user
            and ln.decision == "pending"
        )[:1]

    def _check_can_decide(self):
        for rec in self:
            if rec.state != "pending":
                raise UserError(
                    self.env._("簽核單狀態為 %s，無法簽核", rec.state)
                )
            record = rec._get_res_record()
            if not record or not record.exists():
                raise UserError(
                    self.env._("對應的業務單據已不存在，無法簽核")
                )

    def _get_res_record(self):
        self.ensure_one()
        if not self.res_model or not self.res_id:
            return self.env[self.res_model].browse()
        return self.env[self.res_model].browse(self.res_id)

    def _get_effective_steps(self):
        """回傳本申請實際有簽核者的關卡。

        金額門檻不符、或非必要而略過的關卡不會建立簽核紀錄，
        因此不會出現在此清單，也不會阻擋整體核准。
        """
        self.ensure_one()
        return self.rule_id.step_ids.filtered(
            lambda s: self.line_ids.filtered(lambda ln: ln.step_id == s)
        )

    def _resolve_steps_for_record(self, rule, record):
        """解析規則在此單據上的有效關卡與簽核者。

        :return: ``(active_steps, {step: users})``
        :raise UserError: 沒有適用關卡、必要關卡找不到簽核者時。
        """
        active_steps = rule.step_ids.sorted("sequence").filtered(
            lambda s: s._is_active_for_record(record)
        )
        if not active_steps:
            raise UserError(
                self.env._(
                    "簽核規則「%s」沒有適用於此單據的簽核關卡，此單據不需簽核。",
                    rule.display_name,
                )
            )
        resolved = {}
        for step in active_steps:
            users = step._resolve_approver_users(record)
            if not users:
                if step.required:
                    raise UserError(
                        self.env._(
                            "簽核規則「%s」的關卡「%s」找不到可用的簽核者，"
                            "請檢查群組成員或單據上的簽核者欄位。",
                            rule.display_name,
                            step.display_name,
                        )
                    )
                # 非必要關卡：找不到簽核者時略過
                continue
            resolved[step] = users
        if not resolved:
            raise UserError(
                self.env._(
                    "簽核規則「%s」的關卡都沒有設定簽核者，無法送出簽核。"
                    "請於【MFG Custom > 設定 > 簽核規則】補齊關卡的簽核者。",
                    rule.display_name,
                )
            )
        return active_steps, resolved

    def _build_lines(self):
        """依 ``rule_id.step_ids`` 建立 ``line_ids``。"""
        for rec in self:
            record = rec._get_res_record()
            _active_steps, resolved = rec._resolve_steps_for_record(
                rec.rule_id, record
            )
            LineVals = []
            for step, users in resolved.items():
                for user in users:
                    LineVals.append({
                        "request_id": rec.id,
                        "step_id": step.id,
                        "user_id": user.id,
                        "decision": "pending",
                    })
            self.env["mfg_custom.approval.line"].create(LineVals)
        return True

    def _close_other_pending_lines(self, step):
        """「任一核准即可」的關卡：其他人員的待簽紀錄一併結案。

        若不結案，這些待簽紀錄會讓「當前關卡」一直停在同一關，
        下一個關卡的簽核者永遠輪不到（見 ``_compute_current_step``）。
        """
        self.ensure_one()
        if step.approver_mode == "group_all":
            return False
        others = self.line_ids.filtered(
            lambda ln: ln.step_id == step and ln.decision == "pending"
        )
        if not others:
            return False
        others._engine_write({
            "decision": "skipped",
            "decision_date": fields.Datetime.now(),
            "comment": self.env._("本關卡已由其他簽核者核准，自動略過。"),
        })
        return True

    def _check_all_approved(self):
        """若所有有效關卡皆已通過，將 request 設為 approved。"""
        for rec in self:
            active_steps = rec._get_effective_steps()
            all_done = True
            for step in active_steps:
                if not rec._is_step_done(step):
                    all_done = False
                    break
            if all_done:
                rec._engine_write({"state": "approved"})
                rec._post_final_approved_message()
                rec._notify_business_record("_approval_on_approved")
                rec._notify_decision()

    def _is_step_done(self, step):
        """判斷指定關卡是否已通過。"""
        self.ensure_one()
        step_lines = self.line_ids.filtered(lambda ln: ln.step_id == step)
        if not step_lines:
            return False
        if step.approver_mode == "group_all":
            return all(ln.decision == "approved" for ln in step_lines)
        return any(ln.decision == "approved" for ln in step_lines)

    def _notify_business_record(self, hook_name):
        """在業務單據上觸發 mixin 的狀態回寫 hook（若該單據有掛 mixin）。"""
        for rec in self:
            record = rec._get_res_record()
            if not record or not record.exists():
                continue
            hook = getattr(record, hook_name, None)
            if callable(hook):
                hook()

    def _notify_approvers(self):
        """通知目前關卡的簽核者有待辦（只通知當前關卡，不會一次寄給後續關卡）。"""
        for rec in self:
            if rec.state != "pending" or not rec.pending_approver_emails:
                continue
            template = self.env.ref(
                "mfg_custom_approval.mail_template_mfg_approval_request",
                raise_if_not_found=False,
            )
            if template:
                template.send_mail(rec.id, force_send=False)

    def _notify_decision(self):
        """通知申請人簽核結果。"""
        for rec in self:
            if not rec.requester_id.email:
                continue
            template = self.env.ref(
                "mfg_custom_approval.mail_template_mfg_approval_decided",
                raise_if_not_found=False,
            )
            if template:
                template.send_mail(rec.id, force_send=False)

    def _post_step_progress_message(self, step, note="", approved=True):
        """在 chatter 紀錄當前關卡進度。

        業務單據與簽核單各自留一份紀錄：業務單據記錄流程進度，
        簽核單則記錄「哪個關卡由誰做了什麼決定」。
        """
        self.ensure_one()
        record = self._get_res_record()
        if record and hasattr(record, "message_post"):
            body = self.env._(
                "關卡 %s 已由 %s 簽核",
                step.display_name,
                self.env.user.display_name,
            )
            if note:
                body += self.env._("\n意見：%s", note)
            record.sudo().message_post(
                body=body,
                subtype_xmlid="mfg_custom_approval.mt_mfg_approval_state_changed",
            )
        if approved:
            request_body = self.env._(
                "關卡「%s」已由 %s 核准",
                step.display_name,
                self.env.user.display_name,
            )
        else:
            request_body = self.env._(
                "關卡「%s」已由 %s 駁回",
                step.display_name,
                self.env.user.display_name,
            )
        if note:
            request_body += self.env._("\n意見：%s", note)
        self.sudo().message_post(
            body=request_body,
            subtype_xmlid="mfg_custom_approval.mt_mfg_approval_request_state",
        )

    def _post_final_approved_message(self):
        self.ensure_one()
        record = self._get_res_record()
        if record and hasattr(record, "message_post"):
            record.sudo().message_post(
                body=self.env._("所有簽核關卡皆已通過，狀態：已核准"),
                subtype_xmlid="mfg_custom_approval.mt_mfg_approval_state_changed",
            )
        self.sudo().message_post(
            body=self.env._("所有簽核關卡皆已通過，狀態：已核准"),
            subtype_xmlid="mfg_custom_approval.mt_mfg_approval_request_state",
        )
