# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class MfgQualityPointLine(models.Model):
    """品檢點的逐項規格（量測項目之上下限、單位、是否關鍵項）。

    與 ``mfg_custom.quality.point`` 形成一對多：
    一個品檢點可包含多個檢查項；品檢單啟動時會將此處的規格複製到
    ``mfg_custom.quality.check.line``，再由檢驗員填入量測值。
    """

    _name = "mfg_custom.quality.point.line"
    _description = "MFG 品檢點檢項"
    _order = "sequence, id"

    point_id = fields.Many2one(
        "mfg_custom.quality.point",
        "品檢點",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(default=10, index=True)
    name = fields.Char("檢查項", required=True)
    spec_value = fields.Char("規格值", help="文字型規格（例如「無刮傷」、「≥ 80」）。")
    uom_id = fields.Many2one(
        "uom.uom",
        "單位",
        help="量測項使用；目視／文件核對可留空。",
    )
    min_value = fields.Float("下限")
    max_value = fields.Float("上限")
    is_critical = fields.Boolean(
        "關鍵項",
        default=False,
        index=True,
        help="勾選後，若該項不合格則不可「通過」整張品檢單。",
    )
    notes = fields.Text("備註")

    _line_value_range_idx = models.Index(
        "(point_id, sequence)",
    )

    @api.constrains("min_value", "max_value")
    def _check_value_range(self):
        for rec in self:
            if (
                rec.min_value
                and rec.max_value
                and rec.min_value > rec.max_value
            ):
                raise ValidationError(
                    self.env._(
                        "檢項「%(name)s」的下限 (%(min)s) 不可大於上限 (%(max)s)。",
                        name=rec.name,
                        min=rec.min_value,
                        max=rec.max_value,
                    ),
                )
