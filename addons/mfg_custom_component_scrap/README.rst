MFG Custom - Component Scrap Stat
=================================

以 SQL View 聚合「生產相關的報廢單」，用於分析每個 BOM 子件在每張 MO 中的
標準用量 / 實際消耗 / 報廢數量 / 報廢率 / 有效得料率，協助業務、品保做 RCA。

資料來源
--------

``stock.move`` 滿足下列條件的記錄：

* ``is_scrap = TRUE``
* ``state = 'done'``
* ``raw_material_production_id IS NOT NULL``

對應到原本 stock.scrap 流程的「生產報廢」單（Odoo 20.0 廢止 stock.scrap，
改走 ``stock.move(is_scrap=True)`` 旗標）。

計算欄位
--------

* ``standard_qty``：BOM 子件用量 * (MO 數量 / BOM 數量)
* ``actual_consumed_qty``：同 MO、同產品的非報廢 stock.move (state=done) 數量加總
* ``scrap_rate``：scrapped_qty / standard_qty * 100（百分比）
* ``effective_yield``：100 - scrap_rate（百分比）

依賴
----

* ``mfg_custom_base``：共用安全群組（user / manager）
* ``mrp``：BOM、MO 模型
* ``stock``：stock.move（含 ``is_scrap`` 旗標與 ``scrap_reason_tag_ids``）
* ``mfg_custom_production_stage``：在 MFG Custom 選單下顯示子選單

選單位置
--------

MFG Custom → 報表 → BOM 子件損耗

提供 list / pivot / graph / search view：

* **list**：每筆 scrap × BOM 子件；可依 MO、零件、BOM、日期篩選
* **pivot**：(零件 × BOM) × (平均報廢率 / 總報廢數 / 平均有效得料率)
* **graph**：(零件) × 總報廢數（bar）
* **search**：依日期、零件、BOM、MO、報廢原因標籤過濾
