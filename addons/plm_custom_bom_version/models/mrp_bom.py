# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class MrpBom(models.Model):
    """BOM 擴充：版本快照連結、現行快照、版本計數、快照動作。

    不修改既有邏輯，僅追加 PLM Custom 使用的欄位與方法。
    """

    _inherit = "mrp.bom"

    plm_custom_version = fields.Char(
        "版本",
        default="1.0",
        copy=False,
        required=True,
        help="BOM 邏輯版本，由 ECO 控管遞增（例如 1.0、1.1、2.0）。",
    )
    plm_custom_is_current = fields.Boolean(
        "是否現行版本",
        default=True,
        index=True,
        help="同一 product 群組中，目前生效的 BOM。改版時由 ECO 把舊版設為 False。",
    )
    plm_custom_version_ids = fields.One2many(
        "mrp.bom.version",
        "bom_id",
        "歷史快照",
    )
    plm_custom_current_version_id = fields.Many2one(
        "mrp.bom.version",
        "現行快照",
        compute="_compute_current_version",
        help="快照日期最新的 immutable 快照，作為「現行 BOM 狀態」的歷史佐證。",
    )
    plm_custom_version_count = fields.Integer(
        "版本數",
        compute="_compute_version_count",
    )

    # ------------------------------------------------------------------
    # 計算
    # ------------------------------------------------------------------

    @api.depends("plm_custom_version_ids.snapshot_date")
    def _compute_current_version(self):
        for bom in self:
            versions = bom.plm_custom_version_ids
            if not versions:
                bom.plm_custom_current_version_id = False
                continue
            current = versions.sorted(key=lambda v: v.snapshot_date, reverse=True)[:1]
            bom.plm_custom_current_version_id = current

    @api.depends("plm_custom_version_ids")
    def _compute_version_count(self):
        for bom in self:
            bom.plm_custom_version_count = len(bom.plm_custom_version_ids)

    # ------------------------------------------------------------------
    # 動作
    # ------------------------------------------------------------------

    def action_snapshot(self):
        """凍結 BOM 為 immutable 快照。

        對 self 中每張 BOM 建立一筆 ``mrp.bom.version``，並把該 BOM 的明細 /
        工序 / 副產品全數序列化為快照子記錄。
        """
        self.ensure_one()
        if not self.active:
            raise UserError(self.env._("已歸檔的 BOM 無法建立快照：%s", self.display_name))
        version = self.env["mrp.bom.version"].create_from_bom(self)
        return {
            "type": "ir.actions.act_window",
            "res_model": "mrp.bom.version",
            "res_id": version.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_view_versions(self):
        """打開此 BOM 的歷史快照清單視窗。"""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "plm_custom_bom_version.mrp_bom_version_action"
        )
        action["domain"] = [("bom_id", "=", self.id)]
        action["context"] = {
            "default_bom_id": self.id,
            "search_default_bom_id": self.id,
        }
        return action
