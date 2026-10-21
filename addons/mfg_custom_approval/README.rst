MFG Custom - Multi-level Approval
=================================

通用多層簽核引擎。為 MFG / PLM Custom 模組群提供可掛載於任意業務模型
（plm_custom.eco、mfg_custom.issue、mfg_custom.quality.check 等）的多層簽核工作流程。

功能
----

* 抽象 mixin：``mfg_custom.approval.mixin`` 為其他模型提供「送出簽核 / 簽核 / 駁回 / 取消簽核」
  按鈕以及 ``approval_state`` 計算欄位。
* 簽核規則：可依「適用單據類型」與「適用條件」過濾，符合條件的單據才走此規則。
* 簽核關卡：四種 approver 模式
    - ``user``：指定人員（任一核准即可）
    - ``group``：指定群組（任一成員核准即可）
    - ``group_all``：指定群組（全員皆要核可）
    - ``field``：由單據上的 Many2one res.users 欄位決定簽核者
* 金額門檻：可針對單據上的金額欄位設定上下限。
* 簽核申請：完整 state machine（draft / pending / approved / rejected / cancelled）。
* 簽核紀錄：保留每關卡的決策者、時間、意見，可於 chatter 顯示。
* 通知信：送出簽核時通知待簽核者，最終決定時通知申請人。

可設定的流程（不需改程式碼）
----------------------------

「哪些單據要走哪條流程、幾關、門檻多少」全部由管理員在
**MFG Custom > 設定 > 簽核規則** 設定，**不需要寫任何程式碼**：

1. 新增簽核規則
    * 「適用單據類型」：下拉選擇要簽核的單據（只會列出已掛載簽核功能的單據）。
    * 「適用條件」：用右側的條件建構器（domain widget）挑條件；留空代表全部適用。
      例如「風險等級 = 高」→ 只有高風險的 ECO 需要簽核。
2. 在「簽核關卡」分頁新增關卡，依序由上而下核可：
    * 「簽核者設定」選「指定群組」並挑群組（例：品保部 / 工程部 / 管理部），
      或選「由單據欄位決定」並挑單據上的負責人欄位。
    * 「金額門檻」可再限定此關卡只在此金額區間才啟用。
3. 儲存後，符合條件的單據就會出現「送出簽核」按鈕。

簽核者操作
----------

* 單據 form 右上角：「送出簽核」→ 進入待簽核。
* 簽核者登入後到 **MFG Custom > 待我簽核**，可看到待自己處理的簽核申請，
  並可直接「開啟單據」檢視內容後「核准目前關卡」或「駁回」。
* 所有關卡都核准後，單據的簽核狀態才會變成「已核准」；
  任一關卡駁回則整張申請作廢（可修正後重新送出）。

已掛載簽核功能的單據
--------------------

* ``plm_custom.eco`` 工程變更單（含示範規則：高風險兩關、一般變更一關）
* ``mfg_custom.issue`` 產線問題點
* ``mfg_custom.quality.check`` 品檢單
* ``plm_custom.feasibility`` 可行性評估

掛載新單據
----------

在目標模型的 ``_inherit`` 加入 ``"mfg_custom.approval.mixin"``，
並在該模型自己的 form view 內用 xpath 於 ``<header>`` 插入簽核按鈕即可
（**不要**用 ``inherit_id`` 指向 mixin 的 view，否則會造成版面錯亂）。

依賴
----

* ``mfg_custom_base`` — 共用群組（User / Manager / Engineering / Quality）
* ``mail`` — chatter、追蹤、mail template
