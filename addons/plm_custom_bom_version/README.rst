PLM Custom - BOM Version Snapshot
==================================

為 ``mrp.bom`` 提供 immutable 版本快照機制，取代 OCA ``mrp_bom_version``：

* BOM 可手動或 ECO 觸發「凍結快照」
* 快照為 immutable（防止事後竄改）
* 提供「現行快照」smart button 與「歷史版本」清單
* 快照含明細、工序、副產品三類子記錄
* 支援 ``plm_custom.eco`` （plm_custom_eco 模組）的反向追溯

模型
----

* ``mrp.bom.version`` — BOM 快照主檔
* ``mrp.bom.version.line`` — 快照 BOM 明細（元件 / 數量 / 單位 / 當時成本）
* ``mrp.bom.version.operation`` — 快照工序（工序 / 工作中心 / 工時 / 成本）
* ``mrp.bom.version.byproduct`` — 快照副產品
* ``mrp.bom`` 擴充欄位：``plm_custom_version``、``plm_custom_is_current``、
  ``plm_custom_version_ids``、``plm_custom_current_version_id``、
  ``plm_custom_version_count``

權限
----

* ``mfg_custom_base.group_user`` — 唯讀
* ``mfg_custom_base.group_manager`` — CRUD

依賴
----

* ``mfg_custom_base``
* ``mrp``

安裝
----

直接安裝此模組即可，後續 ``plm_custom_eco`` 模組會建立 ``plm_custom.eco`` 模型
並補上快照反向追溯的 ``ondelete`` 行為。
