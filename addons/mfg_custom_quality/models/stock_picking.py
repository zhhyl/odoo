# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    mfg_quality_check_ids = fields.One2many(
        "mfg_custom.quality.check",
        "picking_id",
        "品檢單",
    )
    mfg_quality_check_count = fields.Integer(
        "品檢單數",
        compute="_compute_mfg_quality_check_count",
        store=True,
    )

    def _get_mfg_quality_check_domain(self):
        self.ensure_one()
        return [("picking_id", "=", self.id)]

    def _compute_mfg_quality_check_count(self):
        Check = self.env["mfg_custom.quality.check"]
        for picking in self:
            picking.mfg_quality_check_count = Check.search_count(
                picking._get_mfg_quality_check_domain(),
            )

    def action_view_mfg_quality_checks(self):
        """從入庫單開啟相關品檢單。"""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "mfg_custom_quality.mfg_quality_check_action",
        )
        action["domain"] = self._get_mfg_quality_check_domain()
        action["context"] = {
            "default_picking_id": self.id,
        }
        action["views"] = [(False, "list"), (False, "form")]
        return action
