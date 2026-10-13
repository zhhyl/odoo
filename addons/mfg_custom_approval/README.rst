MFG Custom - Multi-level Approval
=================================

通用多層簽核引擎。為 MFG / PLM Custom 模組群提供可掛載於任意業務模型
（plm_custom.eco、sale.order、mrp.production 等）的多層簽核工作流程。

功能
----

* 抽象 mixin：``mfg_custom.approval.mixin`` 為其他模型提供「送出簽核 / 簽核 / 駁回」按鈕
  以及 ``approval_state`` 計算欄位。
* 簽核規則：可依 ``res_model`` 與 domain 過濾，符合條件的單據才走此規則。
* 簽核關卡：四種 approver 模式
    - ``user``：指定人員（任一核准即可）
    - ``group``：指定群組（任一成員核准即可）
    - ``group_all``：指定群組（全員皆要核可）
    - ``field``：由單據上的 Many2one res.users 欄位決定簽核者
* 金額門檻：可針對單據上的金額欄位（預設 ``amount_total``）設定上下限。
* 簽核申請：完整 state machine（draft / pending / approved / rejected / cancelled）。
* 簽核紀錄：保留每關卡的決策者、時間、意見，可於 chatter 顯示。

依賴
----

* ``mfg_custom_base`` — 共用群組（User / Manager / Engineering / Quality）
* ``mail`` — chatter、追蹤、mail template

安裝
----

直接安裝此模組即可。下游模組（如 ``plm_custom_eco``）只需在模型中
``_inherit = ["mfg_custom.model.mixin", "mfg_custom.approval.mixin"]``
即可取得簽核功能。
