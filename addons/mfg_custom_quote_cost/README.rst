MFG Custom - Quote BOM Cost Explosion
=====================================

報價階段的 BOM 成本自動展開模組。

* SO line 從主 BOM 遞迴展開所有元件
* 每筆元件帶入標準成本、計算小計
* 工序成本 = ``time_cycle × qty × workcenter.costs_hour``
* 自動計算「成本底價」與「建議報價」（依目標毛利率）

取代 OCA ``sale_mrp_cost``（不需 backport）。
