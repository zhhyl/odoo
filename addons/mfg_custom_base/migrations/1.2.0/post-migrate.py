# Part of Odoo. See LICENSE file for full copyright and licensing details.

"""合併重複的「PLM Custom」根選單。

20.0.1.1.0 → 20.0.1.2.0
=======================

``plm_custom_bom_version`` 與 ``plm_custom_feasibility`` 各自建立了一個同名
「PLM Custom」的根選單，掛在「MFG Custom」底下，前端會看到兩個一樣的節點。

現在根選單改由 ``mfg_custom_base`` 統一提供
（``mfg_custom_base.menu_plm_custom_root``），本腳本把舊的兩個根選單
（及其子選單）搬過去並刪除舊記錄。
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

OLD_ROOTS = (
    "plm_custom_bom_version.menu_plm_custom_root",
    "plm_custom_feasibility.menu_plm_custom_root",
)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    new_root = env.ref(
        "mfg_custom_base.menu_plm_custom_root", raise_if_not_found=False
    )
    if not new_root:
        _logger.warning(
            "mfg_custom_base: 找不到新的 PLM Custom 根選單，略過選單合併。"
        )
        return
    for xmlid in OLD_ROOTS:
        old = env.ref(xmlid, raise_if_not_found=False)
        if not old or old.id == new_root.id:
            continue
        # 先把子選單改掛到新的根選單（直接刪除舊根會 cascade 刪掉子選單）
        if old.child_id:
            old.child_id.write({"parent_id": new_root.id})
        # 移除舊的 xmlid 與選單記錄
        env["ir.model.data"].search([
            ("module", "=", xmlid.split(".")[0]),
            ("name", "=", "menu_plm_custom_root"),
        ]).unlink()
        old.unlink()
        _logger.info("mfg_custom_base: 已合併並移除重複的 PLM Custom 根選單 %s。", xmlid)
