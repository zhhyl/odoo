# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, fields, models
from odoo.exceptions import UserError


class MrpBomVersionByproduct(models.Model):
    """BOM 快照的副產品子記錄。

    由 ``mrp.bom.version.create_from_bom()`` 自動建立，immutable。
    """

    _name = "mrp.bom.version.byproduct"
    _description = "BOM 版本快照副產品"
    _order = "sequence, id"
    _rec_name = "product_id"

    version_id = fields.Many2one(
        "mrp.bom.version",
        "快照",
        required=True,
        index=True,
        ondelete="cascade",
    )
    product_id = fields.Many2one(
        "product.product",
        "副產品",
        required=True,
    )
    product_qty = fields.Float(
        "數量",
        digits="Product Unit",
    )
    product_uom_id = fields.Many2one(
        "uom.uom",
        "單位",
    )
    sequence = fields.Integer("Sequence", default=1)

    def write(self, vals):
        raise UserError(self.env._("BOM 快照副產品不可修改。"))

    def unlink(self):
        raise UserError(self.env._("BOM 快照副產品不可刪除。"))
