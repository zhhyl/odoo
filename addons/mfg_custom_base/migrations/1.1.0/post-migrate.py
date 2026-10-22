# Part of Odoo. See LICENSE file for full copyright and licensing details.

"""把既有的內部使用者補上 MFG Custom 共用群組。

20.0.1.0.0 → 20.0.1.1.0
=======================

新增「建立使用者時自動加入 ``mfg_custom_base.group_user``」的行為
（models/res_users.py）。既有資料庫裡已建立的內部使用者不會自動取得，
故於此補上，讓升級後所有內部使用者都能看到 MFG Custom 選單與資料。
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    group = env.ref("mfg_custom_base.group_user", raise_if_not_found=False)
    if not group:
        _logger.warning("mfg_custom_base: 找不到 group_user，略過補群組。")
        return
    users = env["res.users"].search([("share", "=", False)])
    to_add = users.filtered(lambda u: group not in u.all_group_ids)
    if not to_add:
        return
    for user in to_add:
        user.write({"group_ids": [(4, group.id)]})
    _logger.info(
        "mfg_custom_base: 已將 %s 個既有內部使用者加入 MFG Custom 共用群組。",
        len(to_add),
    )
