# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import Command, api, models


class ResUsers(models.Model):
    """使用者：自動加入 MFG Custom 共用群組。

    ``mfg_custom_base.group_user`` 是 MFG / PLM Custom 所有功能的授權基礎
    （選單可見性、資料讀寫權限、簽核引擎的通知對象）。若沒有自動指派，
    新建的內部使用者會看不到整個「MFG Custom」選單樹，也無法被指派為
    簽核關卡的簽核者。
    """

    _inherit = "res.users"

    @api.model
    def _mfg_custom_user_group(self):
        """回傳新使用者要自動加入的 MFG Custom 群組（找不到則略過）。"""
        return self.env.ref(
            "mfg_custom_base.group_user",
            raise_if_not_found=False,
        )

    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        group = self._mfg_custom_user_group()
        if not group:
            return users
        for user in users:
            # 只自動加入「內部使用者」（share=False）；Portal / 公開使用者不給
            if user.share or group in user.all_group_ids:
                continue
            user.write({"group_ids": [Command.link(group.id)]})
        return users
