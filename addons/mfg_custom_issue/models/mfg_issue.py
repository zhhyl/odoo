# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class MfgCustomIssue(models.Model):
    """產線問題点主檔。"""

    _name = "mfg_custom.issue"
    _description = "MFG Custom 產線問題点"
    _inherit = ["mail.activity.mixin", "rating.mixin", "mfg_custom.approval.mixin"]
    _order = "priority desc, create_date desc"
    _mail_post_access = "read"
    _track_duration_field = "stage_id"

    name = fields.Char(default="New", readonly=True, copy=False)
    code = fields.Char(default="New", readonly=True, copy=False)
    subject = fields.Char("主旨", required=True, index=True)
    description = fields.Html("現象描述", required=True)
    stage_id = fields.Many2one(
        "mfg_custom.issue.stage",
        "階段",
        required=True,
        default=lambda self: self._default_stage(),
        tracking=True,
        group_expand="_group_expand_stages",
        index=True,
    )
    state = fields.Selection(
        [
            ("open", "開立"),
            ("analyzing", "分析中"),
            ("implementing", "執行改善"),
            ("closed", "已結案"),
            ("cancelled", "取消"),
        ],
        compute="_compute_state",
        store=True,
        index=True,
    )
    priority = fields.Selection(
        [("0", "低"), ("1", "中"), ("2", "高"), ("3", "緊急")],
        default="1",
        index=True,
        tracking=True,
    )
    issue_type = fields.Selection(
        [
            ("defect", "不良"),
            ("machine", "設備"),
            ("material", "物料"),
            ("process", "製程"),
            ("safety", "安全"),
            ("other", "其他"),
        ],
        required=True,
        index=True,
    )
    production_id = fields.Many2one(
        "mrp.production",
        "相關 MO",
        ondelete="set null",
        index=True,
    )
    workorder_id = fields.Many2one(
        "mrp.workorder",
        "相關工序",
        index=True,
    )
    workcenter_id = fields.Many2one(
        "mrp.workcenter",
        "工作中心",
        index=True,
    )
    product_id = fields.Many2one(
        "product.product",
        "相關產品",
        index=True,
    )
    lot_id = fields.Many2one(
        "stock.lot",
        "批號",
        index=True,
    )
    quality_check_id = fields.Many2one(
        "mfg_custom.quality.check",
        "對應品檢",
        ondelete="set null",
        index=True,
    )
    task_id = fields.Many2one(
        "project.task",
        "對應任務",
        ondelete="set null",
        help="選填：可連結到 project.task 以納入專案排程。",
    )
    # 8D 流程
    d1_team = fields.Html("D1 成立小組")
    d2_problem = fields.Html("D2 問題描述")
    d3_containment = fields.Html("D3 圍堵措施")
    d5_corrective = fields.Html("D5 永久對策")
    d7_prevent = fields.Html("D7 防再發")
    root_cause = fields.Html("根因分析（5Why）")
    # 改善追蹤
    action_ids = fields.One2many(
        "mfg_custom.issue.action",
        "issue_id",
        "改善行動",
    )
    eco_id = fields.Reference(
        # 使用 Reference 而非 Many2one：避免與 plm_custom_eco 模組互依賴
        selection=[("plm_custom.eco", "ECO")],
        string="升級 ECO",
        readonly=True,
        help="本問題被升級為 ECO 時記錄（待 plm_custom_eco 模組安裝後即可使用）。",
    )
    user_id = fields.Many2one(
        "res.users",
        "負責人",
        default=lambda self: self.env.user,
        tracking=True,
    )
    reporter_id = fields.Many2one(
        "res.users",
        "通報人",
        default=lambda self: self.env.user,
    )
    closed_date = fields.Datetime("結案日")
    notes = fields.Text("備註")

    _issue_stage_priority_idx = models.Index(
        "(stage_id, priority, production_id)"
    )

    def _default_stage(self):
        return self.env["mfg_custom.issue.stage"].search(
            [], order="sequence", limit=1
        )

    def _group_expand_stages(self, stages, domain, order=None):
        return self.env["mfg_custom.issue.stage"].search([], order=order or "sequence")

    @api.depends("stage_id.is_closed", "stage_id.fold")
    def _compute_state(self):
        for issue in self:
            stage = issue.stage_id
            if not stage:
                issue.state = "open"
                continue
            if stage.is_closed:
                issue.state = "closed"
                if not issue.closed_date:
                    issue.closed_date = fields.Datetime.now()
            elif stage.fold:
                issue.state = "implementing"
            else:
                issue.state = "open"

    @api.model_create_multi
    def create(self, vals_list):
        """帶出單號（序號 mfg_custom.issue）。"""
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                number = self.env["ir.sequence"].next_by_code(
                    "mfg_custom.issue"
                ) or "New"
                vals["name"] = number
                if vals.get("code", "New") == "New":
                    vals["code"] = number
        issues = super().create(vals_list)
        issues._notify_issue_opened()
        return issues

    def _notify_issue_opened(self):
        """問題點開立時，以電子郵件通知負責人。

        只在開立當下寄一封，之後的狀態異動不另寄信，避免騷擾。
        """
        template = self.env.ref(
            "mfg_custom_issue.mail_template_mfg_issue_open",
            raise_if_not_found=False,
        )
        if not template:
            return
        for issue in self:
            if not issue.user_id or not issue.user_id.email:
                continue
            # 明確指定收件人：既有可能沿用舊版範本設定（use_default_to），
            # 只寄給追隨者會寄不出去
            partners = issue.user_id.partner_id
            template.send_mail(issue.id, force_send=False, email_values={
                "email_to": issue.user_id.email,
                "recipient_ids": [(6, 0, partners.ids)],
            })

    def action_close(self):
        for issue in self:
            closed_stage = self.env["mfg_custom.issue.stage"].search(
                [("is_closed", "=", True)], limit=1
            )
            if not closed_stage:
                raise UserError(
                    self.env._("請先建立一個「結案」階段")
                )
            issue.stage_id = closed_stage

    def action_reopen(self):
        for issue in self:
            open_stage = self.env["mfg_custom.issue.stage"].search(
                [("is_closed", "=", False), ("fold", "=", False)],
                order="sequence",
                limit=1,
            )
            if open_stage:
                issue.stage_id = open_stage
            issue.closed_date = False

    def _get_analyzing_stage(self):
        """取得「分析中」階段。

        先依名稱找「分析中」（來源值或翻譯值）；找不到時退回未結案且未收合
        階段中的第二個（開立 → 分析中 → 圍堵中）。
        """
        Stage = self.env["mfg_custom.issue.stage"]
        names = {"分析中", self.env._("分析中")}
        stage = Stage.search(
            [("name", "in", list(names)), ("is_closed", "=", False)],
            limit=1,
        )
        if stage:
            return stage
        stages = Stage.search(
            [("is_closed", "=", False), ("fold", "=", False)],
            order="sequence",
        )
        return stages[1:2] or stages[:1]

    # ------------------------------------------------------------------
    # 簽核引擎回呼（mixin hooks）
    # ------------------------------------------------------------------

    def _approval_before_submit(self):
        """送出簽核前的業務檢查：已結案的問題点不可再送出簽核。"""
        for issue in self:
            if issue.stage_id.is_closed:
                raise UserError(
                    self.env._(
                        "問題点 %s 已結案，無法再送出簽核。", issue.name
                    )
                )

    def _approval_on_approved(self):
        """所有簽核關卡皆通過時，把問題点移至「結案」階段。

        ``state`` 由 ``stage_id`` 推導（見 ``_compute_state``），因此這裡
        改的是階段而不是直接寫 ``state``；一併寫入 ``closed_date``。
        """
        Stage = self.env["mfg_custom.issue.stage"]
        for issue in self:
            if issue.stage_id.is_closed:
                continue
            closed_stage = Stage.search([("is_closed", "=", True)], limit=1)
            if not closed_stage:
                raise UserError(self.env._("請先建立一個「結案」階段"))
            issue.sudo().write({
                "stage_id": closed_stage.id,
                "closed_date": fields.Datetime.now(),
            })
            issue.sudo().message_post(
                body=self.env._("簽核通過，問題点已結案。"),
                subtype_xmlid="mfg_custom_issue.mt_mfg_issue_state_changed",
            )

    def _approval_on_rejected(self):
        """簽核被駁回時，把問題点退回「分析中」階段。"""
        for issue in self:
            analyzing_stage = self._get_analyzing_stage()
            if not analyzing_stage:
                raise UserError(
                    self.env._("找不到「分析中」階段，請先建立問題点階段")
                )
            issue.sudo().write({
                "stage_id": analyzing_stage.id,
                "closed_date": False,
            })
            issue.sudo().message_post(
                body=self.env._(
                    "簽核駁回，問題点退回「%s」。", analyzing_stage.name
                ),
                subtype_xmlid="mfg_custom_issue.mt_mfg_issue_state_changed",
            )

    def _approval_on_cancelled(self):
        """簽核被取消時，把問題点退回「開立」階段。"""
        Stage = self.env["mfg_custom.issue.stage"]
        for issue in self:
            open_stage = Stage.search(
                [("is_closed", "=", False), ("fold", "=", False)],
                order="sequence",
                limit=1,
            )
            if not open_stage:
                raise UserError(
                    self.env._("找不到「開立」階段，請先建立問題点階段")
                )
            issue.sudo().write({
                "stage_id": open_stage.id,
                "closed_date": False,
            })
            issue.sudo().message_post(
                body=self.env._(
                    "簽核已取消，問題点退回「%s」。", open_stage.name
                ),
                subtype_xmlid="mfg_custom_issue.mt_mfg_issue_state_changed",
            )

    def action_escalate_to_eco(self):
        """升級為 ECO。"""
        self.ensure_one()
        if not self.product_id:
            raise UserError(self.env._("問題点需先關聯產品才能升級為 ECO"))
        bom = self.env["mrp.bom"].search(
            [("product_tmpl_id", "=", self.product_id.product_tmpl_id.id)],
            limit=1,
        )
        if not bom:
            raise UserError(
                self.env._("產品 %s 找不到 BOM，無法升級為 ECO", self.product_id.display_name)
            )
        eco = self.env["plm_custom.eco"].create({
            "type": "process",
            "origin": "issue",
            "source_issue_id": self.id,
            "product_id": self.product_id.id,
            "bom_id": bom.id,
            "from_version": bom.plm_custom_version or "1.0",
            "to_version": "1.1",
            "owner_id": self.user_id.id or self.env.user.id,
            "user_id": self.env.user.id,
            "subject": self.env._("由問題点 %s 升級", self.name),
        })
        self.eco_id = f"plm_custom.eco,{eco.id}"
        self.message_post(
            body=self.env._("已升級為 ECO %s", eco.display_name),
            subtype_xmlid="mfg_custom_issue.mt_mfg_issue_escalated",
        )
