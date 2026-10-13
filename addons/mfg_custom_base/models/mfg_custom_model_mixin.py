# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class MfgCustomModelMixin(models.AbstractModel):
    """MFG Custom 共用 mixin.

    為所有 MFG / PLM Custom 自建模組提供：

    * ``mail.thread`` 追蹤 + chatter
    * 公司隔離欄位 ``company_id``
    * 自動序號 ``code``（預設由 ``mfg_custom.sequence.mixin`` 帶出，可被子模型覆寫）
    * ``active`` 歸檔旗標
    * ``tag_ids`` 標籤
    * ``priority`` 優先順序（0=低、1=中、2=高、3=緊急）
    """

    _name = "mfg_custom.model.mixin"
    _description = "MFG Custom 共用 mixin"
    _inherit = ["mail.thread"]

    company_id = fields.Many2one(
        "res.company",
        "公司",
        index=True,
        default=lambda self: self.env.company,
    )
    code = fields.Char(
        "編號",
        copy=False,
        index=True,
        default=lambda self: self.env["ir.sequence"].next_by_code("mfg_custom.sequence.mixin"),
    )
    active = fields.Boolean(default=True)
    tag_ids = fields.Many2many("mfg_custom.tag", string="標籤")
    priority = fields.Selection(
        [
            ("0", "低"),
            ("1", "中"),
            ("2", "高"),
            ("3", "緊急"),
        ],
        string="優先順序",
        default="1",
        index=True,
        tracking=True,
    )
    user_id = fields.Many2one(
        "res.users",
        "負責人",
        default=lambda self: self.env.user,
        tracking=True,
        help="此單的主要負責人；可由 mail.activity 指派給其他人。",
    )
    notes = fields.Text("備註")

    _code_company_uniq = models.Constraint(
        "UNIQUE(code, company_id)",
        "同公司內編號不可重複。",
    )
    _code_company_idx = models.Index("(company_id, code)")

    def name_get(self):
        """預設顯示為「code - 自動名稱」。子模型可覆寫。"""
        result = []
        for rec in self:
            name = rec.code or rec.display_name or ""
            result.append((rec.id, name))
        return result

    @api.constrains("priority")
    def _check_priority(self):
        for rec in self:
            if rec.priority not in {k for k, _ in self._fields["priority"].selection}:
                raise ValidationError(
                    self.env._("無效的優先順序值：%s", rec.priority)
                )

    def action_archive(self):
        """歸檔所有勾選的記錄（複寫以統一 archive 行為）。"""
        return super().action_archive()

    def action_unarchive(self):
        return super().action_unarchive()
