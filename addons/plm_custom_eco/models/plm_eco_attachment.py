# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class PlmCustomEcoAttachment(models.Model):
    """ECO 相關附件。"""

    _name = "plm_custom.eco.attachment"
    _description = "PLM Custom ECO 附件"
    _order = "eco_id, role, id"

    eco_id = fields.Many2one(
        "plm_custom.eco",
        required=True,
        ondelete="cascade",
        index=True,
    )
    attachment_id = fields.Many2one(
        "ir.attachment",
        "附件",
        required=True,
        ondelete="cascade",
    )
    role = fields.Selection(
        [
            ("old_spec", "舊版規格"),
            ("new_spec", "新版規格"),
            ("evidence", "佐證"),
            ("acknowledgement", "客戶回簽"),
        ],
        required=True,
    )
    note = fields.Char("備註")
