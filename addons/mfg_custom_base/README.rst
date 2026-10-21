MFG Custom - Base
=================

為整個 mfg_custom_\* 與 plm_custom_\* 模組群提供基礎設施：

* 抽象 mixin ``mfg_custom.model.mixin`` （mail.thread + 公司 + 編號 + 標籤 + 優先順序）
* 共用安全群組（User / Manager / Engineering / Quality）
* 共用序號（``mfg_custom.sequence.mixin``）
* 共用 mail.message.subtype

此模組**不包含**任何業務邏輯，僅作為後續 10 個業務模組的基礎。

依賴
----

* ``mail`` — 提供 mail.thread 基礎

安裝
----

直接安裝此模組，後續 mfg_custom_\* 模組皆會自動相依。
