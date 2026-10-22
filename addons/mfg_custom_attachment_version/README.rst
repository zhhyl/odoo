MFG Custom - Attachment Version
===============================

為 ``ir.attachment`` 增加版本（version）、文件分類（doc_type）、受控狀態（doc_state），
在不引入 Enterprise ``documents`` 模組的前提下提供輕量 PLM / DMS 機制。

功能
----

* **版本遞增**：同 ``res_model + res_id + name`` 群組內，上傳新檔時自動 ``+1`` 版本號。
* **受控狀態** ``draft / in_review / released / obsolete``；新版被「發行」時自動把舊版切到 ``obsolete``。
* **ECO 跳版** ``_mfg_custom_bump_version``：建立新版本並把自身 ``mfg_custom_superseded_by_id`` 指到新版。
* **文件分類** ``customer_spec / drawing / acknowledgement / coa / tool_drawing / internal / other``。
* **附件標籤** ``mfg_custom.attachment.tag``：作為獨立字典管理。

依賴
----

* ``mfg_custom_base`` — 共用 mixin、群組、選單入口
* ``mail`` — ``mail.thread`` 基礎

安裝
----

直接安裝即可。安裝後可在 **MFG Custom > 設定 > 附件標籤** 維護標籤字典
（僅管理員群組可見），所有 ``ir.attachment`` 的表單也會帶出新增的
版本/類型/狀態/標籤欄位，清單與搜尋器也同步加入這些欄位。
