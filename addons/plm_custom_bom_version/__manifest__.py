# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    "name": "PLM Custom - BOM Version Snapshot",
    "version": "20.0.1.0.0",
    "category": "Manufacturing/PLM Custom",
    "sequence": 353,
    "summary": "BOM 版本快照（手動或 ECO 觸發凍結、比對、復原）",
    "description": """
PLM Custom - BOM Version Snapshot
=================================

為 ``mrp.bom`` 提供 immutable 版本快照機制，取代 OCA ``mrp_bom_version``：

* BOM 可手動或 ECO 觸發「凍結快照」
* 快照為 immutable（防止事後竄改）
* 提供「現行快照」smart button 與「歷史版本」清單
* 快照含明細、工序、副產品三類子記錄
* 支援 ``plm_custom.eco``（plm_custom_eco 模組）的反向追溯

依賴
----

* ``mfg_custom_base`` — 共用群組、序號、mail subtype
* ``mrp`` — ``mrp.bom``、``mrp.bom.line``、``mrp.routing.workcenter``、``mrp.bom.byproduct``
""",
    "depends": ["mfg_custom_base", "mrp"],
    "data": [
        "security/ir.access.csv",
        "data/ir_sequence_data.xml",
        "data/mail_subtype_data.xml",
        "views/mrp_bom_version_views.xml",
        "views/mrp_bom_version_line_views.xml",
        "views/mrp_bom_views.xml",
        "views/mrp_bom_menus.xml",
    ],
    "installable": True,
    "auto_install": False,
    "author": "Your Company",
    "license": "LGPL-3",
}
