# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    """廠商帳單：付款前檢查關聯採購單的審批狀態。

    設計原則
    --------

    * **只有在管理員明確建立「採購訂單」簽核規則時才會管制。**
      沒有匹配規則的採購單，其 ``approval_rule_id`` 為空 → 不在管制範圍 →
      付款流程與沒有本功能時完全相同。
    * **不採用 Odoo 內建的 ``payment_state='blocked'``**。該欄位是
      ``compute + store + readonly``（``addons/account/models/account_move.py``），
      採購單的審批狀態變動不會觸發帳單重算，手動寫入也會被 compute 覆蓋 →
      不可靠。這裡改以純 Python 閘門實作，風格與
      ``mfg_custom_purchase_approval/models/purchase_order.py`` 的
      ``button_confirm()`` 審批 gate 一致。
    * **只擋廠商帳單（``in_invoice``）**。貸項通知單（``in_refund``）是退款作業，
      不受採購單審批狀態管制。
    """

    _inherit = "account.move"

    mfg_approval_blocked = fields.Boolean(
        compute="_compute_mfg_approval_blocked",
        string="PO 審批未通過",
        help="本帳單關聯的採購單中有尚未通過審批者，付款時會被擋下。",
    )
    mfg_approval_blocked_message = fields.Text(
        compute="_compute_mfg_approval_blocked",
        string="PO 審批未通過原因",
    )

    # ------------------------------------------------------------------
    # 找出阻擋付款的採購單
    # ------------------------------------------------------------------
    def _mfg_approval_purchase_orders(self):
        """本組帳單關聯的採購單（只取廠商帳單）。

        判斷式必須走**明細層**：``account.move.line.purchase_line_id.order_id``。
        不可用 ``account.move.purchase_id`` —— 它是 ``store=False``，且
        ``addons/purchase/models/account_invoice.py`` 的
        ``_onchange_purchase_auto_complete()`` 會在複製完資料後把它清成
        False，資料庫層幾乎永遠是空的，會誤判成「沒有關聯採購單」而漏擋。
        """
        if not self:
            return self.env["purchase.order"]
        moves = self.filtered(lambda m: m.move_type == "in_invoice")
        return moves.mapped("line_ids.purchase_line_id.order_id")

    def _mfg_approval_blocked_purchase_orders(self):
        """回傳阻擋付款的採購單。

        只有「有匹配簽核規則」且「尚未核准」的採購單才在結果內 ——
        沒有簽核規則的採購單完全不受管制。
        """
        orders = self._mfg_approval_purchase_orders()
        if not orders:
            return orders
        # ``approval_rule_id`` 是非 stored 的 compute，逐筆取用會各跑一次
        # _match_rule()；一次 read 讓 ORM 整組算完，避免 N 次查詢。
        # 用 sudo 讀取，避免付款者沒有採購單讀取權限時直接拋 AccessError。
        data = orders.sudo().read(["approval_rule_id", "approval_state"])
        rule_map = {d["id"]: bool(d["approval_rule_id"]) for d in data}
        state_map = {d["id"]: d["approval_state"] for d in data}
        return orders.filtered(
            lambda po: rule_map.get(po.id) and state_map.get(po.id) != "approved",
        )

    def _mfg_approval_blocked_message(self, blocked_orders):
        """組出給使用者看的阻擋說明（含該去哪裡送審）。"""
        state_labels = dict(
            self.env["purchase.order"]._fields["approval_state"]
            ._description_selection(self.env),
        )
        lines = []
        for po in blocked_orders:
            # 用 sudo 讀取顯示名稱：付款者可能沒有採購單的讀取權限，
            # 但帳單的 invoice_origin 本來就會顯示採購單編號，不構成額外揭露。
            lines.append("%s：%s" % (
                po.sudo().display_name,
                state_labels.get(po.sudo().approval_state, po.approval_state),
            ))
        return self.env._(
            "以下採購單尚未通過審批，無法付款：\n%s\n\n"
            "請先於採購單上按「送出簽核」並完成審批；"
            "若情況緊急，可由 MFG Custom 管理員放行。",
            "\n".join(lines),
        )

    # ------------------------------------------------------------------
    # 付款閘門
    # ------------------------------------------------------------------
    def _mfg_check_payment_approval(self):
        """付款前的審批閘門：關聯採購單未核准時擋下。

        安全閥
        ------
        1. 全域開關 ``mfg_custom_purchase_approval.block_payment_without_approval``
           （預設 True = 啟用）。設為 False 即完全停用。
        2. 管理員（``mfg_custom_base.group_manager``）可放行，並在 chatter 留痕。
           放行資格由**伺服器端群組**判定 —— 不採信 client 傳來的 context，
           否則任何人都能自行帶入旗標繞過閘門。
        """
        if not self.env["ir.config_parameter"].sudo().get_bool(
            "mfg_custom_purchase_approval.block_payment_without_approval", True,
        ):
            return
        blocked_orders = self._mfg_approval_blocked_purchase_orders()
        if not blocked_orders:
            return
        message = self._mfg_approval_blocked_message(blocked_orders)
        if self.env.user.has_group("mfg_custom_base.group_manager"):
            for move in self:
                move.message_post(
                    body=self.env._(
                        "管理員放行：略過採購單審批檢查。\n%s", message,
                    ),
                )
            return
        raise UserError(message)

    def action_force_register_payment(self):
        """帳單上的「Pay」按鈕。

        ``action_register_payment()`` 會委派到本方法，因此覆寫本方法即可同時
        涵蓋表單與清單的付款按鈕。
        """
        self._mfg_check_payment_approval()
        return super().action_force_register_payment()

    # ------------------------------------------------------------------
    # 警示欄位
    # ------------------------------------------------------------------
    def _compute_mfg_approval_blocked(self):
        for move in self:
            blocked_orders = move._mfg_approval_blocked_purchase_orders()
            move.mfg_approval_blocked = bool(blocked_orders)
            move.mfg_approval_blocked_message = (
                move._mfg_approval_blocked_message(blocked_orders)
                if blocked_orders else False
            )
