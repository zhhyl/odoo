# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models
from odoo.exceptions import UserError


class PurchaseOrder(models.Model):
    """採購單（RFQ）接入通用多層簽核引擎。

    本模組把 ``purchase.order`` 掛上 ``mfg_custom.approval.mixin``，因此採購單
    可直接送出簽核、核准、駁回，並在簽核完成前無法轉為正式訂單。

    設計原則
    --------

    * **不動 Odoo 原生的 ``state``**。``purchase.order`` 的狀態只有
      ``draft / sent / to approve / purchase / done / cancel``，若塞入自訂的
      「已核准 / 已駁回」會污染原生狀態機（``button_cancel`` 的可取消集合是寫死的、
      報表與 portal 模板都依賴原生 state）。簽核進度改由 mixin 既有的
      ``approval_state`` 欄位對外呈現。
    * **不動 Odoo 原生的雙人覆核機制**（``to approve`` 狀態）。兩者語意不同：
      內建是金額覆核且核准者限採購經理；本模組是多部門業務簽核。
      管理員若只要一套，把 ``res.company.po_double_validation`` 設為
      ``one_step`` 即可。
    * **不覆寫 ``button_approve`` / ``_approval_allowed``**，避免與內建機制打架。
    """

    # 順序有意義：簽核 mixin 必須排在 ``purchase.order`` 之前。
    #
    # ``purchase.order`` 本身已直接繼承 ``mail.thread``，而
    # ``mfg_custom.approval.mixin`` 也繼承 ``mail.thread``。若把 mixin 排在
    # ``purchase.order`` 之後，基底清單會變成
    # ``... mail.thread ... base, mfg_custom.approval.mixin``，與 mixin 自身
    # MRO（mixin → mail.thread → base）形成循環，Odoo 會在載入 registry 時拋出
    # ``TypeError: Cannot create a consistent method resolution order``。
    #
    # 把 mixin 排在最前面即與 Odoo 核心的做法一致 —— 例如 ``account.move``
    # 把 ``mail.thread.main.attachment``（同樣繼承 mail.thread）排在基底清單前段。
    _inherit = ["mfg_custom.approval.mixin", "purchase.order"]

    # ------------------------------------------------------------------
    # 判斷是否需要簽核
    # ------------------------------------------------------------------
    def _mfg_requires_approval(self):
        """本單（recordset）是否有匹配的簽核規則。

        沒有任何規則 = 不需簽核，維持 Odoo 原生行為。

        ``approval_rule_id`` 是**非 stored** 的 compute，逐筆取用會各跑一次
        ``_match_rule()``；這裡對整個 recordset 一次取用，避免在迴圈中變成
        N 次查詢。
        """
        return bool(self.mapped("approval_rule_id"))

    # ------------------------------------------------------------------
    # 簽核引擎回呼
    # ------------------------------------------------------------------
    def _approval_before_submit(self):
        """送出簽核前的業務檢查。

        在此擋下不適合送審的採購單，讓使用者在送出前就收到明確錯誤，
        而不是送出後才被簽核引擎擋住。
        """
        for order in self:
            if order.state not in ("draft", "sent"):
                raise UserError(
                    self.env._("只有草稿或已寄出的採購單可以送出簽核。"),
                )
            if not order.order_line:
                raise UserError(
                    self.env._("採購單 %s 沒有任何明細，無法送出簽核。",
                               order.display_name),
                )
            if not order.partner_id:
                raise UserError(
                    self.env._("採購單 %s 尚未指定供應商，無法送出簽核。",
                               order.display_name),
                )
        return True

    def _approval_on_approved(self):
        """所有關卡通過時通知使用者可以確認訂單。

        不改 ``state`` —— 轉正式訂單仍由使用者按「確認訂單」決定。
        """
        for order in self:
            order.message_post(
                body=self.env._(
                    "採購單簽核已全部通過，可按「確認訂單」轉為正式訂單。",
                ),
                subtype_xmlid="mfg_custom_approval.mt_mfg_approval_state_changed",
            )
        return True

    def _approval_on_rejected(self):
        """簽核被駁回時說明如何重新送審。"""
        for order in self:
            order.message_post(
                body=self.env._(
                    "採購單簽核已被駁回，請修正後重新送出簽核。",
                ),
                subtype_xmlid="mfg_custom_approval.mt_mfg_approval_state_changed",
            )
        return True

    def _approval_on_cancelled(self):
        """簽核被取消時通知使用者。"""
        for order in self:
            order.message_post(
                body=self.env._("採購單簽核已取消。"),
                subtype_xmlid="mfg_custom_approval.mt_mfg_approval_state_changed",
            )
        return True

    # ------------------------------------------------------------------
    # 送出簽核前的關卡：未完成簽核不得轉正式訂單
    # ------------------------------------------------------------------
    def button_confirm(self):
        """確認訂單前檢查簽核狀態。

        有匹配簽核規則但尚未核准時擋下；其餘情況完全走 Odoo 原生流程
        （包含內建的 ``to approve`` 雙人覆核邏輯）。
        """
        # 一次算出每張單是否需要簽核。``approval_rule_id`` 是非 stored 的 compute，
        # 逐筆取用會各跑一次 ``_match_rule()``；用 read() 一次讀回整組，
        # 由 ORM 一次算完所有單據，避免 N 次查詢。
        needs_approval = {
            data["id"]: bool(data["approval_rule_id"])
            for data in self.read(["approval_rule_id"])
        }
        # Odoo 20 的 Selection label 需依語系翻譯，用 _description_selection 取
        state_labels = dict(
            self._fields["approval_state"]._description_selection(self.env),
        )
        for order in self:
            if order.state not in ("draft", "sent"):
                continue
            if needs_approval.get(order.id) and order.approval_state != "approved":
                raise UserError(self.env._(
                    "採購單 %s 需先完成簽核才能確認訂單（目前簽核狀態：%s）。",
                    order.display_name,
                    state_labels.get(order.approval_state, order.approval_state),
                ))
        return super().button_confirm()
