# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, fields, models


class MfgCustomIssueAction(models.Model):
    """問題点改善行動。"""

    _name = "mfg_custom.issue.action"
    _description = "MFG Custom 問題点改善行動"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "deadline, id"

    issue_id = fields.Many2one(
        "mfg_custom.issue",
        required=True,
        ondelete="cascade",
        index=True,
    )
    name = fields.Char("對策", required=True)
    description = fields.Html("說明")
    owner_id = fields.Many2one(
        "res.users",
        "負責人",
        required=True,
    )
    deadline = fields.Date("期限", required=True)
    state = fields.Selection(
        [
            ("todo", "待執行"),
            ("doing", "執行中"),
            ("done", "已完成"),
            ("verify", "驗證中"),
            ("verified", "已驗證"),
            ("cancelled", "取消"),
        ],
        default="todo",
        required=True,
        index=True,
    )
    verification_note = fields.Html("驗證結果")
    done_date = fields.Date("完成日")
    notes = fields.Text("備註")

    def action_set_state(self, new_state):
        for action in self:
            vals = {"state": new_state}
            if new_state == "done" and not action.done_date:
                vals["done_date"] = fields.Date.today()
            action.write(vals)
