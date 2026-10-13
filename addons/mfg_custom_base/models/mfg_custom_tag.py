# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class MfgCustomTag(models.Model):
    """MFG Custom 共用標籤.

    提供給 ``mfg_custom.model.mixin.tag_ids`` 與其他子模組使用。
    """

    _name = "mfg_custom.tag"
    _description = "MFG Custom 標籤"
    _order = "name"

    name = fields.Char(required=True, translate=True)
    color = fields.Integer("顏色索引")
    description = fields.Char("說明")
    active = fields.Boolean(default=True)
