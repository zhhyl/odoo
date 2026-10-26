# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import Command
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
