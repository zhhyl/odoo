# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import Command
from odoo.tests import tagged
from odoo.tests.common import BaseCommon, new_test_user


@tagged("post_install", "-at_install")
class TestMfgApprovalMixin(BaseCommon):
    """測試 ``mfg_custom.approval.mixin`` 的 ``approval_state`` 與動作按鈕。"""

    _test_user_groups = (
        "base.group_user",
        "mfg_custom_base.group_manager",
    )

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Rule = cls.env["mfg_custom.approval.rule"]
        cls.TestModel = cls.env["mfg_custom.approval.test.model"]
        cls.user_a = new_test_user(cls.env, login="mixin_a", groups="base.group_user")

    def _make_single_user_rule(self):
        return self.Rule.create({
            "name": "Single",
            "res_model": "mfg_custom.approval.test.model",
            "step_ids": [
                Command.create({
                    "name": "Only",
                    "approver_mode": "user",
                    "user_ids": [Command.set([self.user_a.id])],
                }),
            ],
        })

    def test_mixin_state_field(self):
        """``approval_state`` 隨 request.state 正確切換。"""
        rec = self.TestModel.create({})
        # 初始：未送簽
        self.assertEqual(rec.approval_state, "not_required")
        self.assertFalse(rec.approval_request_id)

        # 送簽 → pending
        self._make_single_user_rule()
        rec.action_submit_for_approval()
        rec.invalidate_recordset()
        self.assertEqual(rec.approval_state, "pending")
        self.assertTrue(rec.approval_request_id)

        # 核准 → approved
        rec.approval_request_id.with_user(self.user_a).action_approve()
        rec.invalidate_recordset()
        self.assertEqual(rec.approval_state, "approved")

    def test_mixin_submit_creates_request(self):
        """``action_submit_for_approval`` 應建立一筆 pending request。"""
        self._make_single_user_rule()
        rec = self.TestModel.create({})
        rec.action_submit_for_approval()
        self.assertTrue(rec.approval_request_id)
        self.assertEqual(rec.approval_request_id.state, "pending")
        self.assertEqual(rec.approval_request_id.res_model, self.TestModel._name)
        self.assertEqual(rec.approval_request_id.res_id, rec.id)

    def test_mixin_cancel_approval(self):
        """``action_cancel_approval`` 應把 request 切到 cancelled。"""
        self._make_single_user_rule()
        rec = self.TestModel.create({})
        rec.action_submit_for_approval()
        rec.action_cancel_approval()
        self.assertEqual(rec.approval_request_id.state, "cancelled")
        rec.invalidate_recordset()
        self.assertEqual(rec.approval_state, "not_required")

    def test_mixin_reject_from_mixin(self):
        """``action_reject_current_step`` 應透過 mixin 把 request 駁回。"""
        self._make_single_user_rule()
        rec = self.TestModel.create({})
        rec.action_submit_for_approval()
        rec.with_user(self.user_a).action_reject_current_step(reason="缺件")
        self.assertEqual(rec.approval_request_id.state, "rejected")
        self.assertEqual(rec.approval_request_id.reason, "缺件")
