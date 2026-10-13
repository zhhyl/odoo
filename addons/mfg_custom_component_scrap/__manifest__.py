# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    "name": "MFG Custom - Component Scrap Stat",
    "version": "20.0.1.0.0",
    "category": "Manufacturing/MFG Custom",
    "sequence": 361,
    "summary": "聚合 BOM 子件報廢統計（哪個零件最常壞、報廢率、影響良率）",
    "description": """
MFG Custom - Component Scrap Stat
=================================

以 SQL View 聚合 ``stock.move(is_scrap=True, state='done', raw_material_production_id)``，
提供「每張 MO × 每個 BOM 子件」的報廢分析：

* 標準用量（從 BOM 推算）
* 實際消耗（從同 MO 的非報廢 stock.move 加總）
* 報廢數量
* 報廢率（%）
* 有效得料率（%）

提供 list / pivot / graph / search view，給業務、品保做 RCA（root cause analysis）。

注意
----

* 需搭配 ``mfg_custom_production_stage`` 才能在 mfg_custom 選單下顯示。
* Odoo 20.0 的 ``stock.scrap`` 已改為 ``stock.move(is_scrap=True)`` 旗標；本模組的 SQL
  僅過濾 ``is_scrap = TRUE`` 的 stock.move，與原始 stock.scrap 流程等價。
* 報廢率 = 報廢數量 / 標準用量；標準用量 = BOM 子件用量 * (MO 數量 / BOM 數量)。
* 若 BOM 子件不存在或標準用量 = 0，報廢率視為 0、有效得料率視為 100。
""",
    "depends": [
        "mfg_custom_base",
        "mrp",
        "stock",
        "mfg_custom_production_stage",
    ],
    "data": [
        "security/ir.access.csv",
        "views/mfg_component_scrap_stat_views.xml",
    ],
    "installable": True,
    "auto_install": False,
    "author": "Your Company",
    "license": "LGPL-3",
}
