# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, fields, models
from odoo.exceptions import UserError


class MrpBomVersionLine(models.Model):
    """BOM 快照的明細子記錄。

    由 ``mrp.bom.version.create_from_bom()`` 自動建立；屬於 immutable 快照的一部
    分，禁止寫入與刪除（由 ``mrp.bom.version`` 上的 write 攔截，但同時也禁止直
    接對子記錄操作）。
    """

    _name = "mrp.bom.version.line"
    _description = "BOM 版本快照明細"
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
        "元件",
        required=True,
    )
    product_qty = fields.Float(
        "數量",
        digits="Product Unit",
        required=True,
    )
    product_uom_id = fields.Many2one(
        "uom.uom",
        "單位",
    )
    product_cost = fields.Float(
        "當時標準成本",
        digits="Product Price",
        help="快照當下的 standard_price，方便事後比較成本差異。",
    )
    sequence = fields.Integer("Sequence", default=1)

    _line_version_idx = models.Index("(version_id, product_id)")

    # 快照子記錄為 immutable，禁止寫入與刪除。
    def write(self, vals):
        raise UserError(self.env._("BOM 快照明細不可修改。"))

    def unlink(self):
        raise UserError(self.env._("BOM 快照明細不可刪除。"))
