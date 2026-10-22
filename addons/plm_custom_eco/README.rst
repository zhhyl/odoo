PLM Custom - Engineering Change Order
=====================================

完整的工程變更單 (ECO/ECN) 系統（取代 Enterprise ``plm``）：

* 申請 → 影響分析 → 待簽核 → 核准/駁回 → 套用 → 取消
* 自動影響分析（展開未完成 SO / 庫存 / 未關 MO / 相關附件）
* 觸發來源：客戶/內部/供應商/問題点/法規
* 套用時自動：
    - 凍結舊 BOM 快照
    - 升版 BOM version
    - 升版附件版本（透過 mfg_custom_attachment_version）
* 可從問題点升級
* 多層簽核（透過 mfg_custom_approval）
* 套用後以電子郵件通知 ECO 負責人
