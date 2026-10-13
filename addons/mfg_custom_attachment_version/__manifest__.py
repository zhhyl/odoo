# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    "name": "MFG Custom - Attachment Version",
    "version": "20.0.1.0.0",
    "category": "Manufacturing/MFG Custom",
    "sequence": 352,
    "summary": "ir.attachment 擴增版本 / 文件分類 / 受控狀態（取代部分 PLM DMS）",
    "description": """
MFG Custom - Attachment Version
===============================

為 ``ir.attachment`` 增加版本（version）、文件分類（doc_type）、受控狀態（doc_state），
在不引入 Enterprise ``documents`` 模組的前提下提供輕量 PLM / DMS 機制。

本模組覆蓋的場景
----------------

* 客戶規格書 / 圖面 / 承認書等外部文件，皆掛在對應單據的 ``ir.attachment`` 上。
* 同一份「檔名」在同一單據（``res_model + res_id``）上傳新版時，自動遞增版本號。
* 新版文件被「發行」時，自動把同群組舊版切到 ``已停用（obsolete）``。
* 由 ECO 流程觸發的「跳版」輔助方法：`_mfg_custom_bump_version`。

文件類型（``mfg_custom_doc_type``）
---------------------------------

``customer_spec`` / ``drawing`` / ``acknowledgement`` / ``coa`` /
``tool_drawing`` / ``internal`` / ``other``。

文件狀態（``mfg_custom_doc_state``）
----------------------------------

``draft`` → ``in_review`` → ``released``；被取代或退版時轉為 ``obsolete``。
""",
    "depends": ["mfg_custom_base", "mail"],
    "data": [
        "security/ir.access.csv",
        "data/mail_subtype_data.xml",
        "views/ir_attachment_views.xml",
        "views/mfg_attachment_menus.xml",
    ],
    "installable": True,
    "auto_install": False,
    "author": "Your Company",
    "license": "LGPL-3",
}
