# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install", "mfg_custom", "plm_custom")
class TestMfgPurchaseApproval(TransactionCase):
    """測試採購單（RFQ）接入通用多層簽核引擎。

    重點：
    * 沒有匹配規則時，採購單維持 Odoo 原生行為（可直接確認訂單）
    * 有匹配規則但未完成簽核時，不得轉為正式訂單
    * 簽核流程本身（送出 / 核准 / 駁回 / 重送）沿用引擎既有行為
    * 簽核**不會**改動 purchase.order 原生的 state
    """

    # Odoo 20 的測試框架以受限使用者執行測試（群組取自 _test_user_groups）
    _test_user_groups = (
        "base.group_user",
        "base.group_partner_manager",
        "product.group_product_manager",
        "purchase.group_purchase_user",
        "mfg_custom_base.group_user",
        "mfg_custom_base.group_manager",
    )

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.PO = cls.env["purchase.order"]
        cls.Rule = cls.env["mfg_custom.approval.rule"]
        cls.Step = cls.env["mfg_custom.approval.step"]

        cls.partner = cls.env["res.partner"].create({
            "name": "MFG 測試供應商",
            "email": "mfg_supplier@example.com",
        })
        cls.product = cls.env["product.product"].create({
            "name": "MFG 測試採購品",
            "type": "consu",
            "purchase_ok": True,
            "standard_price": 1000.0,
        })
        cls.approver = new_test_user(
            cls.env,
            login="po_approver",
            groups="base.group_user,mfg_custom_base.group_user,purchase.group_purchase_user",
        )
        # sequence=1 → 優先於其他規則
        cls.rule = cls.Rule.create({
            "name": "採購單測試簽核規則",
            "model_id": cls.env["ir.model"]._get("purchase.order").id,
            "sequence": 1,
            "step_ids": [
                Command.create({
                    "name": "測試核准",
                    "approver_mode": "user",
                    "user_ids": [Command.set([cls.approver.id])],
                }),
            ],
        })

    # ------------------------------------------------------------------
    # 輔助
    # ------------------------------------------------------------------
    def _new_order(self, qty=1.0, price=1000.0):
        """建立一張草稿狀態的採購單（自備資料，不依賴 demo 資料）。"""
        product = self.env["product.product"].create({
            "name": "MFG 測試品 %.2f" % price,
            "type": "consu",
            "purchase_ok": True,
            "standard_price": price,
        })
        return self.PO.create({
            "partner_id": self.partner.id,
            "order_line": [Command.create({
                "product_id": product.id,
                "product_qty": qty,
                "price_unit": price,
            })],
        })

    def _approve_all(self, order):
        """以核准人身分把所有關卡簽完。"""
        order.with_user(self.approver).action_approve_current_step()

    # ------------------------------------------------------------------
    # 案例
    # ------------------------------------------------------------------
    def test_01_no_matching_rule_can_confirm(self):
        """沒有任何匹配規則時，採購單維持原生行為可直接確認訂單。"""
        self.rule.active = False
        order = self._new_order()
        self.assertFalse(order.approval_rule_id)
        order.button_confirm()
        self.assertEqual(order.state, "purchase")

    def test_02_confirm_blocked_without_approval(self):
        """有匹配規則但尚未送審時，不得確認訂單。"""
        order = self._new_order()
        self.assertTrue(order.approval_rule_id)
        with self.assertRaises(UserError):
            order.button_confirm()
        self.assertEqual(order.state, "draft")

    def test_03_submit_creates_request_and_pending_state(self):
        """送出簽核後建立簽核單，approval_state 變為待簽核。"""
        order = self._new_order()
        order.action_submit_for_approval()
        self.assertEqual(order.approval_state, "pending")
        self.assertTrue(order.approval_request_id)
        self.assertEqual(order.approval_request_id.res_model, "purchase.order")
        self.assertEqual(order.approval_request_id.res_id, order.id)

    def test_04_approved_then_confirm_succeeds(self):
        """簽核全部通過後可確認訂單。"""
        order = self._new_order()
        order.action_submit_for_approval()
        self._approve_all(order)
        self.assertEqual(order.approval_state, "approved")
        order.button_confirm()
        self.assertEqual(order.state, "purchase")

    def test_05_confirm_blocked_while_pending(self):
        """簽核進行中不得確認訂單。"""
        order = self._new_order()
        order.action_submit_for_approval()
        with self.assertRaises(UserError):
            order.button_confirm()
        self.assertEqual(order.state, "draft")

    def test_06_rejected_blocks_confirm(self):
        """簽核被駁回後不得確認訂單。"""
        order = self._new_order()
        order.action_submit_for_approval()
        order.with_user(self.approver).action_reject_current_step(reason="價格過高")
        self.assertEqual(order.approval_state, "rejected")
        with self.assertRaises(UserError):
            order.button_confirm()

    def test_07_resubmit_after_reject_restarts_flow(self):
        """駁回後重新送出簽核可重啟流程。"""
        order = self._new_order()
        order.action_submit_for_approval()
        order.with_user(self.approver).action_reject_current_step(reason="請補充報價")
        request = order.approval_request_id
        order.action_submit_for_approval()
        self.assertEqual(order.approval_request_id, request)
        self.assertEqual(order.approval_state, "pending")

    def test_08_before_submit_validations(self):
        """送出簽核前的業務檢查。"""
        # 沒有明細
        empty_order = self.PO.create({"partner_id": self.partner.id})
        with self.assertRaises(UserError):
            empty_order.action_submit_for_approval()

        # 狀態不是 draft / sent
        order = self._new_order()
        order.action_submit_for_approval()
        self._approve_all(order)
        order.button_confirm()
        self.assertEqual(order.state, "purchase")
        with self.assertRaises(UserError):
            order.action_submit_for_approval()

    def test_09_approval_does_not_change_purchase_state(self):
        """簽核流程不得改動 purchase.order 原生的 state。"""
        order = self._new_order()
        order.action_submit_for_approval()
        self.assertEqual(order.state, "draft")
        self._approve_all(order)
        self.assertEqual(order.state, "draft")
        self.assertEqual(order.approval_state, "approved")

        # 駁回路徑另開一張單：已核准的簽核單不可再駁回
        rejected = self._new_order()
        rejected.action_submit_for_approval()
        rejected.with_user(self.approver).action_reject_current_step(reason="退回")
        self.assertEqual(rejected.state, "draft")
        self.assertEqual(rejected.approval_state, "rejected")

    def test_10_rule_domain_limits_which_orders_need_approval(self):
        """規則的適用條件可限定只有大額採購單需要簽核。"""
        # 停用通用的測試規則，改用有金額條件的規則
        self.rule.active = False
        domain_rule = self.Rule.create({
            "name": "大額採購簽核規則",
            "model_id": self.env["ir.model"]._get("purchase.order").id,
            "sequence": 0,
            "domain": "[('amount_total', '>=', 1000000)]",
            "step_ids": [
                Command.create({
                    "name": "大額核准",
                    "approver_mode": "user",
                    "user_ids": [Command.set([self.approver.id])],
                }),
            ],
        })
        small_order = self._new_order(price=1000.0)
        self.assertFalse(small_order.approval_rule_id)
        small_order.button_confirm()
        self.assertEqual(small_order.state, "purchase")

        big_order = self._new_order(price=2000000.0)
        self.assertEqual(big_order.approval_rule_id, domain_rule)
        with self.assertRaises(UserError):
            big_order.button_confirm()

    def test_11_step_amount_threshold(self):
        """關卡的金額門檻可讓不符金額的關卡不啟用。"""
        amount_field = self.env["ir.model.fields"]._get("purchase.order", "amount_total")
        self.assertTrue(amount_field, "purchase.order 應有 amount_total 欄位")
        self.rule.step_ids.write({
            "amount_field_id": amount_field.id,
            "min_amount": 1000000.0,
        })
        small_order = self._new_order(price=1000.0)
        # 沒有任何啟用的關卡 → 送出簽核時引擎會擋下
        with self.assertRaises(UserError):
            small_order.action_submit_for_approval()

    def test_12_approval_state_badge_values(self):
        """approval_state 的各個取值正確切換。"""
        order = self._new_order()
        self.assertEqual(order.approval_state, "not_required")
        order.action_submit_for_approval()
        self.assertEqual(order.approval_state, "pending")
        self._approve_all(order)
        self.assertEqual(order.approval_state, "approved")


@tagged("post_install", "-at_install", "mfg_custom", "plm_custom")
class TestMfgPurchasePaymentApproval(TransactionCase):
    """測試「付款前必須先通過採購單審批」的閘門。

    重點：
    * 只有「有匹配簽核規則」的採購單才受管制；沒有規則時付款流程完全不變
    * 未核准時，帳單的「Pay」與付款精靈都會被擋下
    * 已核准時放行；全域開關與管理員放行是安全閥
    """

    # Odoo 20 的測試框架以受限使用者執行測試（群組取自 _test_user_groups）
    _test_user_groups = (
        "base.group_user",
        "base.group_partner_manager",
        "product.group_product_manager",
        "purchase.group_purchase_user",
        "account.group_account_invoice",
        "account.group_account_readonly",
        "mfg_custom_base.group_user",
        "mfg_custom_base.group_manager",
    )

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.PO = cls.env["purchase.order"]
        cls.Move = cls.env["account.move"]
        cls.Rule = cls.env["mfg_custom.approval.rule"]

        cls.partner = cls.env["res.partner"].create({
            "name": "MFG 付款測試供應商",
            "email": "mfg_pay_supplier@example.com",
        })
        cls.product = cls.env["product.product"].create({
            "name": "MFG 付款測試品",
            "type": "consu",
            "purchase_ok": True,
            "standard_price": 500.0,
        })
        cls.approver = new_test_user(
            cls.env,
            login="pay_approver",
            groups="base.group_user,mfg_custom_base.group_user,purchase.group_purchase_user",
        )
        cls.rule = cls.Rule.create({
            "name": "付款測試簽核規則",
            "model_id": cls.env["ir.model"]._get("purchase.order").id,
            "sequence": 1,
            "step_ids": [
                Command.create({
                    "name": "測試核准",
                    "approver_mode": "user",
                    "user_ids": [Command.set([cls.approver.id])],
                }),
            ],
        })

    # ------------------------------------------------------------------
    # 輔助
    # ------------------------------------------------------------------
    def _new_order(self, price=500.0):
        product = self.env["product.product"].create({
            "name": "MFG 付款測試品 %.2f" % price,
            "type": "consu",
            "purchase_ok": True,
            "standard_price": price,
        })
        return self.PO.create({
            "partner_id": self.partner.id,
            "order_line": [Command.create({
                "product_id": product.id,
                "product_qty": 1,
                "price_unit": price,
            })],
        })

    def _approved_order(self, price=500.0):
        """一張已通過審批的採購單（state=purchase，可開立帳單）。"""
        order = self._new_order(price=price)
        order.action_submit_for_approval()
        order.with_user(self.approver).action_approve_current_step()
        self.assertEqual(order.approval_state, "approved")
        order.button_confirm()
        return order

    def _new_bill(self, order):
        """依採購單建立一張廠商帳單（明細層掛上 purchase_line_id）。"""
        line = order.order_line[0]
        return self.Move.create({
            "move_type": "in_invoice",
            "partner_id": order.partner_id.id,
            "invoice_date": fields.Date.context_today(self),
            "invoice_line_ids": [Command.create({
                "product_id": line.product_id.id,
                "quantity": line.product_qty,
                "price_unit": line.price_unit,
                "purchase_line_id": line.id,
            })],
        })

    # ------------------------------------------------------------------
    # 案例
    # ------------------------------------------------------------------
    def test_01_no_rule_payment_unaffected(self):
        """沒有簽核規則的採購單 → 付款完全不受管制（既有流程零影響）。

        沒有規則時連「送出簽核」都會被引擎擋下（正確行為），
        所以這裡的採購單維持 draft、從未進入審批流程。
        """
        self.rule.active = False
        order = self._new_order()
        self.assertFalse(order.approval_rule_id)
        bill = self._new_bill(order)
        self.assertFalse(bill.mfg_approval_blocked)
        # 不拋錯
        bill._mfg_check_payment_approval()

    def test_02_pending_po_blocks_payment(self):
        """採購單審批中 → 帳單付款被擋。"""
        order = self._new_order()
        order.action_submit_for_approval()
        self.assertEqual(order.approval_state, "pending")
        bill = self._new_bill(order)
        self.assertTrue(bill.mfg_approval_blocked)
        self.assertIn(order.display_name, bill.mfg_approval_blocked_message)
        with self.assertRaises(UserError):
            bill._mfg_check_payment_approval()
        with self.assertRaises(UserError):
            bill.action_force_register_payment()

    def test_03_approved_po_allows_payment(self):
        """採購單已核准 → 付款放行。"""
        order = self._approved_order()
        bill = self._new_bill(order)
        self.assertFalse(bill.mfg_approval_blocked)
        bill._mfg_check_payment_approval()

    def test_04_one_of_many_pos_pending_blocks(self):
        """一張帳單關聯多張 PO，只要有一張未核准就擋。"""
        approved = self._approved_order()
        pending = self._new_order()
        pending.action_submit_for_approval()
        bill = self._new_bill(approved)
        # 把第二張 PO 的明細掛到同一張帳單上
        pending_line = pending.order_line[0]
        bill.write({
            "invoice_line_ids": [Command.create({
                "product_id": pending_line.product_id.id,
                "quantity": pending_line.product_qty,
                "price_unit": pending_line.price_unit,
                "purchase_line_id": pending_line.id,
            })],
        })
        self.assertTrue(bill.mfg_approval_blocked)
        with self.assertRaises(UserError):
            bill._mfg_check_payment_approval()

    def test_05_gate_can_be_disabled_by_config(self):
        """系統參數可全域停用閘門。"""
        self.env["ir.config_parameter"].sudo().set_bool(
            "mfg_custom_purchase_approval.block_payment_without_approval", False,
        )
        order = self._new_order()
        order.action_submit_for_approval()
        bill = self._new_bill(order)
        # 閘門停用 → 不擋
        bill._mfg_check_payment_approval()

    def test_06_manager_can_bypass_with_record(self):
        """管理員可放行，且帳單 chatter 留下放行紀錄。"""
        order = self._new_order()
        order.action_submit_for_approval()
        bill = self._new_bill(order)
        manager = new_test_user(
            self.env,
            login="pay_manager",
            groups=(
                "base.group_user,"
                "account.group_account_readonly,"
                "mfg_custom_base.group_manager"
            ),
        )
        bill.with_user(manager)._mfg_check_payment_approval()
        self.assertTrue(
            bill.message_ids.filtered(lambda m: "管理員放行" in (m.body or "")),
            "管理員放行後應在 chatter 留下紀錄",
        )

    def test_07_payment_register_wizard_blocked(self):
        """付款精靈同樣受管制。"""
        order = self._new_order()
        order.action_submit_for_approval()
        bill = self._new_bill(order)
        wizard = self.env["account.payment.register"].with_context(
            active_model="account.move",
            active_ids=bill.ids,
        ).create({})
        self.assertTrue(wizard.line_ids)
        with self.assertRaises(UserError):
            wizard.action_create_payments()

    def test_08_refund_move_not_gated(self):
        """貸項通知單（退款）不受採購單審批管制。"""
        order = self._new_order()
        order.action_submit_for_approval()
        line = order.order_line[0]
        refund = self.Move.create({
            "move_type": "in_refund",
            "partner_id": order.partner_id.id,
            "invoice_date": fields.Date.context_today(self),
            "invoice_line_ids": [Command.create({
                "product_id": line.product_id.id,
                "quantity": line.product_qty,
                "price_unit": line.price_unit,
                "purchase_line_id": line.id,
            })],
        })
        self.assertFalse(refund.mfg_approval_blocked)
        refund._mfg_check_payment_approval()

    def test_09_approval_line_ids_visible_on_po(self):
        """PO 上的審批紀錄與簽核單一致。"""
        order = self._new_order()
        order.action_submit_for_approval()
        request = order.approval_request_id
        self.assertEqual(order.approval_line_ids, request.line_ids)
        self.assertTrue(order.approval_line_ids)
        # 核准後決策與核准人應更新在 PO 的審批紀錄上
        order.with_user(self.approver).action_approve_current_step()
        line = order.approval_line_ids[0]
        self.assertEqual(line.decision, "approved")
        self.assertEqual(line.user_id, self.approver)
        self.assertTrue(line.decision_date)

    def test_10_action_open_approval_request(self):
        """PO 上可開啟對應的簽核單。"""
        order = self._new_order()
        order.action_submit_for_approval()
        action = order.action_open_approval_request()
        self.assertEqual(action["res_model"], "mfg_custom.approval.request")
        self.assertEqual(action["res_id"], order.approval_request_id.id)
        self.assertEqual(action["view_mode"], "form")

    def test_11_alert_refreshes_after_approval(self):
        """PO 核准後，帳單上的警示要跟著解除（compute 相依性）。

        沒有宣告 @api.depends 時，非 stored 的 compute 會在快取中留著舊值，
        導致「PO 已核准但帳單仍顯示被擋」。
        """
        order = self._new_order()
        order.action_submit_for_approval()
        bill = self._new_bill(order)
        self.assertTrue(bill.mfg_approval_blocked)
        order.with_user(self.approver).action_approve_current_step()
        # 同一個 transaction 內重讀 → 相依性必須讓警示跟著更新
        self.assertEqual(order.approval_state, "approved")
        self.assertFalse(bill.mfg_approval_blocked)
