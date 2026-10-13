# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, fields, models
from odoo.exceptions import UserError


class MrpBomVersionOperation(models.Model):
    """BOM 快照的工序子記錄。

    由 ``mrp.bom.version.create_from_bom()`` 自動建立，immutable。
    """

    _name = "mrp.bom.version.operation"
    _description = "BOM 版本快照工序"
    _order = "sequence, id"
    _rec_name = "name"

    version_id = fields.Many2one(
        "mrp.bom.version",
        "快照",
        required=True,
        index=True,
        ondelete="cascade",
    )
    name = fields.Char("工序名稱", required=True)
    workcenter_id = fields.Many2one(
        "mrp.workcenter",
        "工作中心",
    )
    time_cycle = fields.Float(
        "工時（分鐘）",
        help="快照當下的 time_cycle_manual。",
    )
    cost = fields.Float(
        "工序成本",
        help="快照當下由 workcenter.costs_hour 計算的成本。",
    )
    sequence = fields.Integer("Sequence", default=100)

    def write(self, vals):
        raise UserError(self.env._("BOM 快照工序不可修改。"))

    def unlink(self):
        raise UserError(self.env._("BOM 快照工序不可刪除。"))
