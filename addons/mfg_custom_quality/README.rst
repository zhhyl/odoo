MFG Custom - Quality Inspection
===============================

以 `mfg_custom_base` 為基礎，提供 Community 版缺漏的品質檢驗流程：

* 品檢點（規格書）+ 品檢細項（上下限）
* 品檢單（MO／工序／入庫單關聯）+ 檢驗結果（量測值）
* 放行審核：品檢單送出簽核後由通用簽核引擎（``mfg_custom_approval``）多層核准
* 不合格可關聯問題点（``mfg_custom_issue``）；目前不會自動建立改善單，需自行
  建立問題点後回填「對應改善單」欄位
* 判定不合格時以電子郵件通知 MO 負責人／入庫單負責人／檢驗員（依序取第一個
  有信箱者）

品檢單的狀態流程
----------------

檢驗流程：

* ``draft`` （待執行）→ 按「開始檢驗」→ ``in_progress`` （檢驗中）
* ``in_progress`` 判定後 → ``passed`` （合格）／``failed`` （不合格）／
  ``conditional`` （特採）
* ``in_progress`` 可按「重置回待執行」回到 ``draft``
* ``draft`` / ``in_progress`` 可按「取消」→ ``cancelled`` （取消）；
  已判定（合格／不合格／特採／已放行）的品檢單不可取消

放行審核（簽核引擎）：

* 只有 ``in_progress`` / ``passed`` / ``conditional`` 狀態可按「送出簽核」
* 所有關卡核准後 → ``approved`` （已放行），並在 chatter 留下放行訊息
* 簽核被駁回 → 退回 ``in_progress`` （檢驗中）
* 簽核被取消 → 退回 ``draft`` （待執行）
* 示範規則為「品保部核准 → 管理部核准」兩關，管理者可在
  **MFG Custom > 設定 > 簽核規則** 自行調整

依賴
----

* ``mfg_custom_base`` — 共用 mixin、群組、序號
* ``mfg_custom_approval`` — 放行審核用的通用簽核引擎
* ``mrp`` — ``mrp.production`` / ``mrp.workorder`` / ``mrp.workcenter``
* ``stock`` — ``stock.picking`` / ``stock.lot``

安裝
----

直接 ``./odoo-bin -i mfg_custom_quality`` 即可。

主要選單：MFG Custom → 品檢（品檢點 / 待執行品檢 / 品檢歷史）。

測試
----

::

    ./odoo-bin -d testdb --test-enable --stop-after-init \
        --test-tags=/mfg_custom_quality \
        --addons-path=addons,odoo/addons -i mfg_custom_quality
