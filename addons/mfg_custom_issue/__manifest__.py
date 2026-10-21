# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    "name": "MFG Custom - Production Issue",
    "version": "20.0.1.1.0",
    "category": "Manufacturing/MFG Custom",
    "sequence": 358,
    "summary": "產線問題点收集 + 改善追蹤 + 對應 ECO / 8D 報告（取代 Enterprise helpdesk）",
    "description": """
MFG Custom - Production Issue
=============================

產線問題点管理系統（取代 Enterprise ``helpdesk``）：

* Kanban 看板（依 stage 自動分組）
* 8D 流程欄位（D1~D7）
* 改善行動追蹤（deadline、負責人、驗證）
* 從 mrp.production / mfg_custom.quality.check 自動建立
* 可升級為 ECO（plm_custom.eco）
* 多部門協作：MO、工序、工作中心、產品、批號、品檢
""",
    "depends": [
        "mfg_custom_approval",
        "mfg_custom_base",
        "mfg_custom_production_stage",
        "mfg_custom_quality",
        "mrp",
        "project",
    ],
    "data": [
        "security/ir.access.csv",
        "data/ir_sequence_data.xml",
        "data/mail_subtype_data.xml",
        "data/mail_template_data.xml",
        "data/mfg_issue_stage_data.xml",
        "views/mfg_issue_stage_views.xml",
        "views/mfg_issue_views.xml",
        "views/mrp_production_views.xml",
        "views/mfg_issue_menus.xml",
        "data/mfg_approval_rule_data.xml",
    ],
    "installable": True,
    "auto_install": False,
    "author": "Your Company",
    "license": "LGPL-3",
}
