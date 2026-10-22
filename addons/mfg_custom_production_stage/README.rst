MFG Custom - Production Stage & Yield Rate
==========================================

為 ``mrp.production`` 加入生產階段區分與得料率自動計算。

功能
----

* **生產階段** ``mfg_custom_production_stage``：樣品 / 小批量 / 量產
* **階段變更日誌** ``mrp.production.stage.log``：記錄每次階段切換
* **變更生產階段** 按鈕：開啟確認視窗（可填變更原因）後套用新階段
* **得料率** ``mfg_custom_yield_rate``：由 ``move_finished_ids`` 與 ``move_raw_ids`` 自動計算
* **期望得料率** ``mfg_custom_expected_yield_rate``：BOM 級預設值
* **BOM 預設階段** ``mfg_custom_default_production_stage``：在 BOM 上預設新建 MO 使用的階段
* **問題点 / 品檢計數**：安裝對應模組後自動統計並啟用 smart button
* **每日 cron** 重算得料率（每日 23:00）

依賴
----

* ``mfg_custom_base``：共用群組、序號、mail mixin
* ``mrp``：核心製造模組
* ``stock``：庫存模組（得料率需用 stock.move）

關聯模組
--------

* ``mfg_custom_issue``（選擇性）：問題点計數與 smart button
* ``mfg_custom_quality``（選擇性）：品檢計數與 smart button
* ``plm_custom_feasibility``（選擇性）：樣品單關聯欄位

三者皆以「延遲參考」方式保留欄位／介面：安裝後自動生效，未安裝時欄位顯示為空
或計數為 0，不會造成錯誤。

安裝
----

直接安裝此模組即可，後續問題点／品檢／樣品評估模組建好後不需要重灌。
