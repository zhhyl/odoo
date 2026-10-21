# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    "name": "MFG Custom - Quality Inspection",
    "version": "20.0.1.1.0",
    "category": "Manufacturing/MFG Custom",
    "sequence": 356,
    "summary": "品檢點 + 品檢單 + 結果（Community 無 quality 模組之替代）",
    "description": """
MFG Custom - Quality Inspection
===============================

以 `mfg_custom_base` 為基礎，提供 Community 版缺漏的品質檢驗流程：

* **品檢點 (``mfg_custom.quality.point``)** — 規格書：適用產品／工序／抽樣數，
  含可逐項定義上下限的檢查項目 (``quality.point.line``)。
* **品檢單 (``mfg_custom.quality.check``)** — 檢驗過程單：可連結至 MO、工序、
  入庫單、批號；支援 ``draft → in_progress → passed / failed / conditional`` 等
  狀態流轉；不合格自動建立改善單（待 ``mfg_custom_issue`` 模組上線後生效）。
* **檢驗結果 (``mfg_custom.quality.check.line``)** — 量測值與合格／不合格判定。

行為
----

* 啟動品檢時，自動從品檢點帶入檢項規格。
* 任何關鍵項 (``is_critical``) 不合格 → ``action_pass`` 拋 ``UserError``。
* 不合格會留下原因，可選擇關聯至 ``mfg_custom.issue`` 模組產生的改善單。

整合點
------

* **MO** 的 form view：新增「品檢單」智慧按鈕。
* **入庫單** 的 form view：新增「品檢單」智慧按鈕。
""",
    "depends": ["mfg_custom_base", "mfg_custom_approval", "mrp", "stock"],
    "data": [
        "security/ir.access.csv",
        "data/ir_sequence_data.xml",
        "data/mail_subtype_data.xml",
        "data/mail_template_data.xml",
        "views/mfg_quality_point_views.xml",
        "views/mfg_quality_check_views.xml",
        "views/mrp_production_views.xml",
        "views/stock_picking_views.xml",
        "views/mfg_quality_menus.xml",
        "data/mfg_approval_rule_data.xml",
    ],
    "installable": True,
    "auto_install": False,
    "author": "Your Company",
    "license": "LGPL-3",
}
