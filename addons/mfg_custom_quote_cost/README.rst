MFG Custom - Quote BOM Cost Explosion
=====================================

報價階段的 BOM 成本自動展開模組。

* 由 wizard（``mfg_custom.quote.cost.wizard``）挑選要展開的 SO line，
  從主 BOM 遞迴展開所有元件；結果寫入 SO line 的「成本展開」明細
  （``mfg_custom.quote.cost.line``），可於 **MFG Custom > 報價成本展開** 檢視
* 每筆元件帶入標準成本（``product.standard_price``）、計算小計
* 工序成本 =（``time_cycle`` × 數量 ÷ 60）× ``workcenter.costs_hour``
  （``time_cycle`` 為分鐘數，故先除以 60 換算為小時）
* 自動計算「成本底價」與「建議報價」（依目標毛利率，
  建議報價 = 成本底價 ÷ (1 − 毛利率%)）
* 成本類型可分為材料 / 委外加工 / 人工 / 製造費用 / 包裝 / 其他

取代 OCA ``sale_mrp_cost`` （不需 backport）。
