PLM Custom - Feasibility Assessment
====================================

跨部門可行性評估模組。在接到潛在訂單或客戶詢問時，由業務/工程/產線/品保/採購/法規
六個部門各自評分 0-10，模組自動彙總為「可行 / 可行但有風險 / 不可行」三類決策結論。

模型
----

* ``plm_custom.feasibility`` — 評估主檔（含 5 個面向分數與自動彙總）
* ``plm_custom.feasibility.score`` — 評分明細（每部門一筆）
* ``plm_custom.feasibility.wizard`` — 從銷售訂單/明細一鍵開立評估的 wizard

決策規則
--------

* 總分 = 五項分數加總 × 2（滿分 100）
* >= 80 → 可行 (feasible)
* 60-79 → 可行但有風險 (feasible_with_risk)
* < 60  → 不可行 (infeasible)

來源
----

可從銷售訂單、銷售明細或手動建立；亦可透過 wizard 從 SO / SO line 直接帶入客戶與產品。

依賴
----

* mfg_custom_base
* sale
* mrp
* purchase
