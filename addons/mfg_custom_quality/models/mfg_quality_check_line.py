# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class MfgQualityCheckLine(models.Model):
    """品檢單的逐項檢驗結果。

    由 ``mfg_custom.quality.check.action_start()`` 從對應品檢點帶入規格
    （名稱、上下限、單位），檢驗員再填入 ``measured_value`` 及 ``result``。

    ``result`` 的判定與 ``measured_value`` 對上下限比較，於 ``@api.onchange``
    中給出預設（正式判定仍以檢驗員輸入為準）。
    """

    _name = "mfg_custom.quality.check.line"
    _description = "MFG 品檢結果"
    _order = "sequence, id"

    check_id = fields.Many2one(
        "mfg_custom.quality.check",
        "品檢單",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(default=10)
    name = fields.Char("檢查項", required=True)
    spec_value = fields.Char("規格值")
    min_value = fields.Float("下限")
    max_value = fields.Float("上限")
    measured_value = fields.Float("量測值", digits="Product Unit")
    uom_id = fields.Many2one("uom.uom", "單位")
    result = fields.Selection(
        [
            ("pending", "待驗"),
            ("ok", "合格"),
            ("fail", "不合格"),
            ("na", "不適用"),
        ],
        string="判定",
        default="pending",
        required=True,
        index=True,
    )
    note = fields.Char("備註")
    is_critical = fields.Boolean("關鍵項", index=True)

    _line_check_idx = models.Index("(check_id, sequence)")

    @api.constrains("measured_value", "min_value", "max_value")
    def _check_measured_range(self):
        """僅驗證若上下限皆已填，量測值至少有填或標示 N/A。

        上下限是否真正越界由「判定」欄位決定，不由 SQL 強制 —
        因為「目視 / 文件核對」等項目上下限為 0，無法用 SQL 表達。
        """
        for rec in self:
            if (
                rec.min_value
                and rec.max_value
                and rec.min_value > rec.max_value
            ):
                raise ValidationError(
                    self.env._(
                        "檢項「%(name)s」下限 (%(min)s) 不可大於上限 (%(max)s)。",
                        name=rec.name,
                        min=rec.min_value,
                        max=rec.max_value,
                    ),
                )

    @api.onchange("measured_value", "min_value", "max_value")
    def _onchange_measured_value(self):
        """當品檢員輸入量測值時，依上下限給預設判定。

        上下限為 0 視為「未設定限值」，不自動變更 ``result``。
        """
        if not (self.min_value or self.max_value):
            return
        value = self.measured_value
        out_of_range = False
        if self.min_value and value < self.min_value:
            out_of_range = True
        if self.max_value and value > self.max_value:
            out_of_range = True
        if out_of_range and self.result == "pending":
            self.result = "fail"
        elif not out_of_range and self.result == "pending":
            self.result = "ok"
