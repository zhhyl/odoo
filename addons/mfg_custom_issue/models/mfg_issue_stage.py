# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, fields, models


class MfgCustomIssueStage(models.Model):
    """產線問題点階段。"""

    _name = "mfg_custom.issue.stage"
    _description = "MFG Custom 問題点階段"
    _order = "sequence, id"

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    fold = fields.Boolean(
        "收合",
        help="看板收合狀態。已收合的 stage 在 kanban 預設為摺疊狀態。",
    )
    is_closed = fields.Boolean("結案階段", default=False)
    color = fields.Integer()

    def _default_sequence(self):
        return (self.search([], order="sequence desc", limit=1).sequence or 0) + 10
