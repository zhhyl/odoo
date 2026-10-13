# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    "name": "PLM Custom - Engineering Change Order",
    "version": "20.0.1.0.0",
    "category": "Manufacturing/PLM Custom",
    "sequence": 357,
    "summary": "工程變更單 + BOM/路線/客戶規格影響分析 + 多層簽核 + 自動升版",
    "description": """
PLM Custom - Engineering Change Order
=====================================

完整的工程變更單 (ECO/ECN) 系統（取代 Enterprise ``plm``）：

* 申請 → 影響分析 → 待簽核 → 核准/駁回 → 套用 → 取消
* 自動影響分析（展開未完成 SO / 庫存 / 未關 MO / 相關附件）
* 觸發來源：客戶/內部/供應商/問題点/法規
* 套用時自動：
    - 凍結舊 BOM 快照
    - 升版 BOM version
    - 升版附件版本（透過 mfg_custom_attachment_version）
* 可從問題点升級
* 多層簽核（透過 mfg_custom_approval）
""",
    "depends": [
        "mfg_custom_base",
        "mfg_custom_approval",
        "mfg_custom_attachment_version",
        "plm_custom_bom_version",
        "plm_custom_feasibility",
        "mfg_custom_production_stage",
        "mfg_custom_quality",
        "mfg_custom_issue",
        "mrp",
        "mail",
    ],
    "data": [
        "security/ir.access.csv",
        "data/ir_sequence_data.xml",
        "data/mail_subtype_data.xml",
        "data/mail_template_data.xml",
        "views/plm_eco_views.xml",
        "views/plm_eco_line_views.xml",
        "views/plm_eco_attachment_views.xml",
        "views/mrp_bom_views.xml",
        "views/sale_order_views.xml",
        "views/plm_eco_menus.xml",
    ],
    "installable": True,
    "auto_install": False,
    "author": "Your Company",
    "license": "LGPL-3",
}
