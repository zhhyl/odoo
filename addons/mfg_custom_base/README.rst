MFG Custom - Base
=================

為整個 ``mfg_custom_*`` 與 ``plm_custom_*`` 模組群提供基礎設施：

* 抽象 mixin ``mfg_custom.model.mixin``
  （mail.thread + 公司 + 編號 + 標籤 + 優先順序 + 負責人 + 備註 + 歸檔旗標）
* 共用安全群組（User / Manager / Engineering / Quality）
* 共用序號：序號代碼 ``mfg_custom.sequence.mixin`` ，供 mixin 的 ``code`` 欄位取用
* 共用 mail.message.subtype（狀態變更預設追蹤）
* 共用標籤字典 ``mfg_custom.tag`` ，維護位置為 **MFG Custom > 設定 > 標籤**

安全群組
--------

四個群組都掛在 ``res.groups.privilege`` 的「MFG Custom」分類下（Odoo 19+ 的
privilege 分組機制），並形成以下隸屬關係：

* ``mfg_custom_base.group_user`` （User）— 一般使用者，隸含 ``base.group_user``；
  可讀取 mfg_custom / plm_custom 模組的資料並填寫被分配的欄位
* ``mfg_custom_base.group_manager`` （Manager）— 管理員，隸含 User；
  可建立／修改／刪除 mfg_custom 與 plm_custom 模組的所有資料
* ``mfg_custom_base.group_engineering`` （Engineering）— 工程部，隸含 User；
  可編輯 BOM、ECO、可行性評估等 PLM 資料
* ``mfg_custom_base.group_quality`` （Quality）— 品保部，隸含 User；
  可編輯品檢單、產線問題点等品質資料

此模組 **不包含** 任何業務邏輯，僅作為後續 10 個業務模組的基礎。

依賴
----

* ``mail`` — 提供 mail.thread 基礎

安裝
----

直接安裝此模組，後續 ``mfg_custom_*`` 模組皆會自動相依。
