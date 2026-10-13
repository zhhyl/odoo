# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class MfgAttachmentTag(models.Model):
    """MFG / PLM 附件標籤.

    用來在 ``ir.attachment`` 上分類、篩選、群組化（例：客戶機密、待校圖、發行通知）。

    命名沿用模組前綴，與 ``mfg_custom_base`` 的 ``mfg_custom.tag`` 平行：
    本模型專屬附件版本控管，避免污染共用標籤字典。
    """

    _name = "mfg_custom.attachment.tag"
    _description = "MFG 附件標籤"
    _order = "name"

    name = fields.Char(required=True, translate=True)
    color = fields.Integer("顏色索引")
    description = fields.Char("說明")
    active = fields.Boolean(default=True)
