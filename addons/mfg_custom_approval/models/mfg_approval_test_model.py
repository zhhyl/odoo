# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class MfgApprovalTestModel(models.Model):
    """Concrete test model used by approval tests.

    Inherits both ``mfg_custom.model.mixin`` (mail.thread + base fields) and
    ``mfg_custom.approval.mixin`` so the test can exercise the full approval
    flow (submit / approve / reject) end-to-end.

    NOTE：依 Odoo 慣例，測試用的模型必須放在模組的 ``models/`` 目錄，
    否則在 post_install 階段才 import 會來不及註冊到 registry。
    """

    _name = "mfg_custom.approval.test.model"
    _description = "Approval Test Model"
    # 測試用模型：不出現在簽核規則的「適用單據類型」下拉選項中
    # （見 mfg_custom.approval.rule._get_approvable_models）
    _mfg_custom_approval_hidden = True
    _inherit = ["mfg_custom.model.mixin", "mfg_custom.approval.mixin"]

    amount_total = fields.Float(default=0.0)
    approver_user_id = fields.Many2one("res.users")
    state = fields.Selection(
        [("draft", "Draft"), ("confirmed", "Confirmed")],
        default="draft",
    )
