# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    "name": "MFG Custom - Quote BOM Cost Explosion",
    "version": "20.0.1.0.0",
    "category": "Manufacturing/MFG Custom",
    "sequence": 359,
    "summary": "SO line 自動從 BOM 展成本 / 加工費 / 包裝費，產生報價底價",
    "description": """
MFG Custom - Quote BOM Cost Explosion
=====================================

報價階段的 BOM 成本自動展開：

* SO line 從主 BOM 遞迴展開所有元件
* 每筆元件帶入標準成本、計算小計
* 工序成本 =（``time_cycle`` × 數量 ÷ 60）× ``workcenter.costs_hour``
* 自動計算 ``成本底價`` 與 ``建議報價`` （依目標毛利率）

取代 OCA ``sale_mrp_cost`` （不需 backport）。
""",
    "depends": ["mfg_custom_base", "sale", "sale_mrp", "mrp"],
    "data": [
        "security/ir.access.csv",
        "data/mail_subtype_data.xml",
        "views/sale_order_line_views.xml",
        "wizard/mfg_quote_cost_wizard_views.xml",
        "views/mfg_quote_cost_menus.xml",
    ],
    "installable": True,
    "auto_install": False,
    "author": "Your Company",
    "license": "LGPL-3",
}
