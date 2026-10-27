# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models


class AccountPaymentRegister(models.TransientModel):
    """付款精靈：建立付款前檢查關聯採購單的審批狀態。

    會計端「登記付款」的主要路徑是這個精靈，與帳單上的「Pay」按鈕
    （``account.move.action_force_register_payment()``）是兩條不同的路徑，
    兩邊都要檢查才不會漏掉。
    """

    _inherit = "account.payment.register"

    def action_create_payments(self):
        """建立付款前先做審批閘門檢查。"""
        self.line_ids.move_id._mfg_check_payment_approval()
        return super().action_create_payments()
