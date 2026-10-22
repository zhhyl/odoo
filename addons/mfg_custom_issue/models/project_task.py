# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class ProjectTask(models.Model):
    """擴充 project.task：與 mfg_custom.issue 反向連結。

    僅做反向 reference，未強制 task 必須有 issue；提供 smart button 給
    PLM/PM 在專案管理介面直接看到相關產線問題点。
    """

    _inherit = "project.task"

    mfg_custom_issue_ids = fields.Many2many(
        "mfg_custom.issue",
        "project_task_mfg_issue_rel",
        "task_id",
        "issue_id",
        "問題点",
        help="與此 task 關聯的產線問題点；通常由 MO 端建立後自動同步。",
    )
    mfg_custom_issue_count = fields.Integer(
        "問題点數",
        compute="_compute_mfg_custom_issue_count",
    )

    @api.depends("mfg_custom_issue_ids")
    def _compute_mfg_custom_issue_count(self):
        for task in self:
            task.mfg_custom_issue_count = len(task.mfg_custom_issue_ids)

    def action_view_mfg_custom_issues(self):
        """從 task 開啟相關問題点。"""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            # 本模組實際存在的 action 為 mfg_issue_action_kanban / mfg_issue_action_tree
            "mfg_custom_issue.mfg_issue_action_kanban",
        )
        action["domain"] = [("id", "in", self.mfg_custom_issue_ids.ids)]
        action["context"] = {
            "default_user_id": self.user_ids[:1].id if self.user_ids else False,
        }
        action["views"] = [(False, "kanban"), (False, "list"), (False, "form")]
        return action
