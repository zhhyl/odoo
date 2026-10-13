# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class MfgCustomIssue(models.Model):
    """產線問題点主檔。"""

    _name = "mfg_custom.issue"
    _description = "MFG Custom 產線問題点"
    _inherit = ["mail.thread", "mail.activity.mixin", "rating.mixin"]
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
            body=self.env._("已升級為 ECO %s", eco.display_name)
        )
