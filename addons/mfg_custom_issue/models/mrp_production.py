# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    mfg_custom_issue_ids = fields.One2many(
        "mfg_custom.issue",
        "production_id",
        "問題点",
    )
    mfg_custom_issue_count = fields.Integer(
        "問題点數",
        compute="_compute_mfg_custom_issue_count",
    )

    @api.depends("mfg_custom_issue_ids")
    def _compute_mfg_custom_issue_count(self):
        for mo in self:
            mo.mfg_custom_issue_count = len(mo.mfg_custom_issue_ids)

    def action_view_mfg_custom_issues(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "問題点",
            "res_model": "mfg_custom.issue",
            "view_mode": "kanban,list,form",
            "domain": [("production_id", "=", self.id)],
            "context": {
                "default_production_id": self.id,
                "default_product_id": self.product_id.id,
            },
        }

    def action_create_mfg_custom_issue(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "建立問題点",
            "res_model": "mfg_custom.issue",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_production_id": self.id,
                "default_product_id": self.product_id.id,
                "default_workorder_id": False,
            },
        }
