# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class MfgApprovalTestModel(models.Model):
    """Concrete test model used by approval tests.

    Inherits both ``mfg_custom.model.mixin`` (mail.thread + base fields) and
    ``mfg_custom.approval.mixin`` so the test can exercise the full approval
    flow (submit / approve / reject) end-to-end.
    """

    _name = "mfg_custom.approval.test.model"
    _description = "Approval Test Model"
    _inherit = ["mfg_custom.model.mixin", "mfg_custom.approval.mixin"]

    amount_total = fields.Float(default=0.0)
    approver_user_id = fields.Many2one("res.users")
    state = fields.Selection(
        [("draft", "Draft"), ("confirmed", "Confirmed")],
        default="draft",
    )
