# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    "name": "MFG Custom - Production Stage & Yield Rate",
    "version": "20.0.1.0.0",
    "category": "Manufacturing/MFG Custom",
    "sequence": 355,
    "summary": "mrp.production 加上 production_stage、得料率、樣品單關聯",
    "description": """
MFG Custom - Production Stage & Yield Rate
==========================================

為製造工單 (``mrp.production``) 加上：

* 生產階段 ``mfg_custom_production_stage``：樣品 / 小批量 / 量產
* 階段變更日誌 ``mrp.production.stage.log``（含變更人/時間/原因）
* 自動得料率 ``mfg_custom_yield_rate`` 與期望得料率比較
* BOM 預設生產階段 ``mfg_custom_default_production_stage``（BOM 表頭）
* 樣品單關聯欄位（待 plm_custom_feasibility 模組安裝後即可使用）
* 每日 cron 重算得料率
""",
    "depends": ["mfg_custom_base", "mrp", "stock"],
    "data": [
        "security/ir.access.csv",
        "data/mail_subtype_data.xml",
        "views/mrp_production_views.xml",
        "views/mrp_bom_views.xml",
        "views/mfg_stage_menus.xml",
    ],
    "installable": True,
    "auto_install": False,
    "author": "Your Company",
    "license": "LGPL-3",
}
