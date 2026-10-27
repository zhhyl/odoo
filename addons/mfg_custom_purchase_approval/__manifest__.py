# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    "name": "MFG Custom - Purchase Approval",
    "version": "20.0.1.0.0",
    "category": "Manufacturing/MFG Custom",
    "sequence": 362,
    "summary": "讓採購單（RFQ）可走通用多層簽核引擎",
    "description": """
MFG Custom - Purchase Approval
===============================

把 ``purchase.order``（RFQ）掛上本專案的通用簽核引擎
``mfg_custom.approval.mixin``，讓採購單可以直接送出多層簽核。

提供
----

* 採購單表單上的「送出簽核 / 核准目前關卡 / 駁回 / 取消簽核」按鈕與「簽核狀態」statusbar
* 送出簽核前的業務檢查（單據狀態、是否有料、是否已指定供應商）
* 未完成簽核時**無法**按「確認訂單」轉為正式訂單
* 簽核引擎既有的能力一併適用：簽核關卡金額門檻、簽核期限、每日逾期提醒、
  chatter 與 email 通知、重新送出簽核以重啟流程

與 Odoo 內建「to approve」的關係
--------------------------------

Odoo 內建的採購單雙人覆核（``res.company.po_double_validation``，狀態 ``to approve``）
**完全保留不動**。兩者定位不同：

* Odoo 內建：金額覆核，1~2 關，核准者限 ``purchase.group_purchase_manager``
* 本模組：多部門業務簽核，關卡數與核准人由「MFG Custom > 設定 > 簽核規則」定義

順序為「先完成本模組的簽核 → 再按確認訂單」。若公司同時啟用了內建的
「Levels of Approvals = Get 2 levels of approvals」，按確認訂單後仍會進入
``to approve`` 狀態需採購經理再核一次；只要一者可把該設定改為
「Confirm purchase orders in one step」。

安裝
----

安裝後在「MFG Custom > 設定 > 簽核規則」建立規則，
「適用單據類型」下拉會多出「採購訂單」。

規則的「適用條件 (domain)」可用 ``purchase.order`` 上的欄位，例如：

    [("amount_total", ">=", 500000)]

關卡的「最小金額 / 最大金額」預設會對應到 ``purchase.order`` 的 ``amount_total``。
""",
    "depends": ["mfg_custom_approval", "purchase", "mail"],
    "data": [
        "security/mfg_purchase_security.xml",
        "views/purchase_order_views.xml",
        "views/account_move_views.xml",
    ],
    "installable": True,
    "auto_install": False,
    "author": "Your Company",
    "license": "LGPL-3",
}
