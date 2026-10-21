# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    "name": "PLM Custom - Feasibility Assessment",
    "version": "20.0.1.1.0",
    "category": "Manufacturing/PLM Custom",
    "sequence": 354,
    "summary": "跨部門可行性評估（產能/技術/料況/法規/風險五面向評分）",
    "description": """
PLM Custom - Feasibility Assessment
====================================

跨部門可行性評估模組，於產品/訂單階段彙整業務、工程、產線、品保、採購、法規
六個部門評分，自動產出可行性決策結論。

核心模型
--------

* ``plm_custom.feasibility``     — 評估主檔（含五項分數、自動彙總與決策）
* ``plm_custom.feasibility.score`` — 各部門評分明細（每部門一筆、不可重複）
* ``plm_custom.feasibility.wizard`` — 從銷售訂單/明細一鍵開立評估

決策規則
--------

* 五項分數各 0-10，總分 = (sum × 2)，最高 100
* 80 分以上 → 可行 (feasible)
* 60-79   → 可行但有風險 (feasible_with_risk)
* 60 以下 → 不可行 (infeasible)

來源單據
--------

可從「銷售訂單 / 銷售明細 / CRM 機會」建立，亦可手動建立（不限特定來源）。

依賴
----

* ``mfg_custom_base`` — 共用群組（user / manager / engineering / quality）
* ``sale``            — 銷售訂單（從 SO / SO line 建立）
* ``mrp``             — BOM 候選
* ``purchase``        — 採購 / 料況評估

安裝
----

安裝後選單位於「PLM Custom > 可行性評估」。
""",
    "depends": ["mfg_custom_base", "mfg_custom_approval", "sale", "mrp", "purchase"],
    "data": [
        "security/ir.access.csv",
        "data/ir_sequence_data.xml",
        "data/mail_subtype_data.xml",
        "data/mail_template_data.xml",
        "views/plm_feasibility_views.xml",
        "views/plm_feasibility_score_views.xml",
        "wizard/plm_feasibility_wizard_views.xml",
        "views/plm_feasibility_menus.xml",
        "views/sale_order_views.xml",
        "data/mfg_approval_rule_data.xml",
    ],
    "installable": True,
    "auto_install": False,
    "author": "Your Company",
    "license": "LGPL-3",
}
