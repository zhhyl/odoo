# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command


class MrpBomVersion(models.Model):
    """BOM 版本快照主檔。

    不可變更（locked=True）的 BOM 快照；含明細、工序、副產品三類子記錄。
    ``plm_custom.eco`` 模組完成後，可由 ``eco_id`` 反向追溯觸發來源。
    """

    _name = "mrp.bom.version"
    _description = "BOM 版本快照"
    _inherit = ["mail.thread"]
    _order = "snapshot_date desc, id desc"
    _rec_name = "display_name"

    name = fields.Char(
        default="New",
        readonly=True,
        copy=False,
    )
    bom_id = fields.Many2one(
        "mrp.bom",
        "BOM",
        required=True,
        index=True,
        ondelete="restrict",
    )
    version = fields.Char(
        "版本",
        required=True,
        help="BOM 邏輯版本字串（與 mrp.bom.plm_custom_version 一致）。",
    )
    snapshot_date = fields.Datetime(
        "快照時間",
        required=True,
        index=True,
        default=fields.Datetime.now,
    )
    user_id = fields.Many2one(
        "res.users",
        "建立者",
        required=True,
        default=lambda self: self.env.user,
    )
    reason = fields.Selection(
        [
            ("eco", "ECO 觸發"),
            ("manual", "手動建立"),
            ("milestone", "里程碑"),
        ],
        "觸發原因",
        default="manual",
        required=True,
    )
    eco_id = fields.Reference(
        "來源 ECO",
        selection=[("plm_custom.eco", "ECO")],
        # 由 plm_custom_eco 模組補上 ondelete：set null
        help="由 ECO 觸發時對應的 ECO 單據。plm_custom_eco 模組未安裝時為空。",
    )
    note = fields.Text("備註")
    line_ids = fields.One2many(
        "mrp.bom.version.line",
        "version_id",
        "BOM 明細快照",
    )
    operation_ids = fields.One2many(
        "mrp.bom.version.operation",
        "version_id",
        "工序快照",
    )
    byproduct_ids = fields.One2many(
        "mrp.bom.version.byproduct",
        "version_id",
        "副產品快照",
    )
    product_qty = fields.Float(
        "產量",
        digits="Product Unit",
        readonly=True,
    )
    product_uom_id = fields.Many2one(
        "uom.uom",
        "單位",
        readonly=True,
    )
    company_id = fields.Many2one(
        "res.company",
        "公司",
        related="bom_id.company_id",
        store=True,
        index=True,
    )
    display_name = fields.Char(
        compute="_compute_display_name",
        store=True,
    )
    locked = fields.Boolean(
        "已鎖定",
        default=True,
        readonly=True,
        help="快照建立後即鎖定，不允許修改明細 / 工序 / 副產品。",
    )

    _bom_version_idx = models.Index("(bom_id, version)")
    _snapshot_date_idx = models.Index("(snapshot_date, bom_id)")

    # ------------------------------------------------------------------
    # 顯示
    # ------------------------------------------------------------------

    @api.depends("name", "version", "bom_id")
    def _compute_display_name(self):
        for rec in self:
            code = rec.name or rec.bom_id.code or ""
            version = rec.version or ""
            rec.display_name = f"{code}/{version}" if version else code

    # ------------------------------------------------------------------
    # CRUD 保護：鎖定後不可寫、不可刪明細 / 工序 / 副產品
    # ------------------------------------------------------------------

    def write(self, vals):
        locked_fields = {
            "line_ids",
            "operation_ids",
            "byproduct_ids",
            "bom_id",
            "version",
            "product_qty",
            "product_uom_id",
            "snapshot_date",
            "locked",
        }
        if locked_fields.intersection(vals):
            raise UserError(
                self.env._(
                    "快照已鎖定，不可修改：%s。若需更新，請建立新快照。",
                    ", ".join(sorted(locked_fields.intersection(vals))),
                )
            )
        return super().write(vals)

    def unlink(self):
        if not self.env.user.has_group("mfg_custom_base.group_manager"):
            raise UserError(self.env._("僅 Manager 可刪除 BOM 快照。"))
        return super().unlink()

    # ------------------------------------------------------------------
    # 序列化：BOM → snapshot
    # ------------------------------------------------------------------

    @api.model
    def create_from_bom(self, bom):
        """建立一筆不可變快照，並把 BOM 的明細 / 工序 / 副產品全部序列化。"""
        bom = bom._origin  # 規避 NewId
        sequence = self.env["ir.sequence"].next_by_code(
            "plm_custom_bom_version.sequence"
        ) or "/"
        line_vals = []
        for line in bom.bom_line_ids:
            line_vals.append(
                Command.create(
                    {
                        "product_id": line.product_id.id,
                        "product_qty": line.product_qty,
                        "product_uom_id": line.uom_id.id,
                        "product_cost": line.product_id.standard_price,
                        "sequence": line.sequence,
                    }
                )
            )
        operation_vals = []
        for op in bom.operation_ids:
            operation_vals.append(
                Command.create(
                    {
                        "name": op.name,
                        "workcenter_id": op.workcenter_id.id,
                        "time_cycle": op.time_cycle_manual,
                        "cost": op.cost,
                        "sequence": op.sequence,
                    }
                )
            )
        byproduct_vals = []
        for bp in bom.byproduct_ids:
            byproduct_vals.append(
                Command.create(
                    {
                        "product_id": bp.product_id.id,
                        "product_qty": bp.product_qty,
                        "product_uom_id": bp.uom_id.id,
                    }
                )
            )
        version = self.create(
            {
                "name": sequence,
                "bom_id": bom.id,
                "version": bom.plm_custom_version,
                "reason": "manual",
                "line_ids": line_vals,
                "operation_ids": operation_vals,
                "byproduct_ids": byproduct_vals,
                "product_qty": bom.product_qty,
                "product_uom_id": bom.uom_id.id,
            }
        )
        bom.message_post(
            body=self.env._(
                "已建立版本快照 %s，含 %s 條明細。",
                version.display_name,
                len(version.line_ids),
            )
        )
        return version
