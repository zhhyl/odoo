MFG Custom - Purchase Approval
===============================

把 ``purchase.order``（RFQ）掛上本專案的通用簽核引擎
``mfg_custom.approval.mixin``，讓採購單可以直接送出多層簽核。

功能
----

* **表單按鈕**：採購單表單上多出「送出簽核 / 核准目前關卡 / 駁回 / 取消簽核」
  與「簽核狀態」statusbar。
* **送審前檢查**：送出簽核前會檢查單據狀態、是否有料、是否已指定供應商。
* **確認訂單閘門**：有匹配簽核規則但尚未核准時，按「確認訂單」會被擋下。
* **清單與篩選**：採購單清單顯示簽核狀態 badge；篩選器可依「待簽核」篩選。

簽核引擎既有能力一併適用
------------------------

* 多層關卡（``mfg_custom.approval.step``），核准人可為指定人員 / 指定群組 / 單據欄位
* 關卡金額門檻（最小 / 最大金額），預設對應 ``purchase.order`` 的 ``amount_total``
* 簽核期限（``due_days``）與每日 cron 逾期提醒
* Chatter 訊息與 email 通知
* 駁回後重新送出簽核可重啟流程

設定
----

安裝後到 **MFG Custom > 設定 > 簽核規則** 新增一條規則：

* **適用單據類型**：選「採購訂單」
* **適用條件 (domain)**：留空代表所有採購單都要簽核；可寫條件限定範圍，例如
  ``[("amount_total", ">=", 500000)]``
  （可用欄位：``amount_total``、``company_id``、``state``、``partner_id``、
  ``date_order``、``user_id``、``currency_id``）
* **簽核關卡**：新增關卡並挑選核准人。可用本模組提供的「採購簽核者」群組，
  或直接沿用 Odoo 原生的「採購：Administrator」/「採購：User」。

與 Odoo 內建「to approve」的關係
--------------------------------

Odoo 內建的採購單雙人覆核（``res.company.po_double_validation``，狀態 ``to approve``）
**完全保留不動**。兩者定位不同：

* Odoo 內建：金額覆核，1~2 關，核准者限採購經理
* 本模組：多部門業務簽核，關卡數與核准人由簽核規則定義

因此流程順序是「先完成本模組的簽核 → 再按確認訂單」。若公司同時啟用了內建的
「Levels of Approvals = Get 2 levels of approvals」，按確認訂單後仍會進入
``to approve`` 狀態，需採購經理再核一次；只要一套的話，把該設定改成
「Confirm purchase orders in one step」即可。

本模組**不會**改動採購單的原生狀態（``draft`` / ``sent`` / ``to approve`` /
``purchase`` / ``done`` / ``cancel``），簽核進度一律看「簽核狀態」欄位。

依賴
----

* ``mfg_custom_approval`` — 通用多層簽核引擎
* ``purchase`` — 採購單
* ``mail`` — chatter 通知
