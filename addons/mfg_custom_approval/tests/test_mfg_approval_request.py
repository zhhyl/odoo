# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged("post_install", "-at_install", "mfg_custom", "plm_custom")
class TestMfgApprovalRequest(TransactionCase):
    """測試簽核申請的 state machine：循序核准、駁回短路、群組模式。"""

    _test_user_groups = (
        "base.group_user",
        "mfg_custom_base.group_manager",
    )

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Rule = cls.env["mfg_custom.approval.rule"]
        cls.Request = cls.env["mfg_custom.approval.request"]
        cls.Line = cls.env["mfg_custom.approval.line"]
        cls.TestModel = cls.env["mfg_custom.approval.test.model"]
        # 建立 4 個 plain user，作為步驟簽核者
        cls.user_a = new_test_user(cls.env, login="approval_a", groups="base.group_user")
        cls.user_b = new_test_user(cls.env, login="approval_b", groups="base.group_user")
        cls.user_c = new_test_user(cls.env, login="approval_c", groups="base.group_user")
        cls.user_d = new_test_user(cls.env, login="approval_d", groups="base.group_user")

    def _make_rule(self, steps):
        return self.Rule.create({
            "name": "Test Rule",
            "res_model": "mfg_custom.approval.test.model",
            "step_ids": [Command.create(s) for s in steps],
        })

    def _submit(self, vals=None):
        vals = vals or {}
        rec = self.TestModel.create(vals)
        rec.action_submit_for_approval()
        return rec, rec.approval_request_id

    # ------------------------------------------------------------------
    # test_sequential_approval_full_pass
    # ------------------------------------------------------------------

    def test_sequential_approval_full_pass(self):
        """三個 user-mode 關卡依序簽完，request 進入 approved。"""
        rule = self._make_rule([
            {"name": "S1", "approver_mode": "user", "user_ids": [Command.set([self.user_a.id])]},
            {"name": "S2", "approver_mode": "user", "user_ids": [Command.set([self.user_b.id])]},
            {"name": "S3", "approver_mode": "user", "user_ids": [Command.set([self.user_c.id])]},
        ])
        _rec, req = self._submit()
        self.assertEqual(req.state, "pending")
        self.assertEqual(req.current_step_no, 1)

        # 切換到 A 並核准
        req.with_user(self.user_a).action_approve()
        self.assertEqual(req.state, "pending")
        self.assertEqual(req.current_step_no, 2)

        # 切換到 B 並核准
        req.with_user(self.user_b).action_approve()
        self.assertEqual(req.state, "pending")
        self.assertEqual(req.current_step_no, 3)

        # 切換到 C 並核准
        req.with_user(self.user_c).action_approve()
        self.assertEqual(req.state, "approved")

    # ------------------------------------------------------------------
    # test_reject_short_circuits
    # ------------------------------------------------------------------

    def test_reject_short_circuits(self):
        """任一關卡駁回後，request 直接進入 rejected，後續關卡不再觸發。"""
        rule = self._make_rule([
            {"name": "S1", "approver_mode": "user", "user_ids": [Command.set([self.user_a.id])]},
            {"name": "S2", "approver_mode": "user", "user_ids": [Command.set([self.user_b.id])]},
        ])
        _rec, req = self._submit()
        req.with_user(self.user_a).action_reject(reason="資料不全")
        self.assertEqual(req.state, "rejected")
        self.assertEqual(req.reason, "資料不全")
        # 後續關卡不可再簽
        with self.assertRaises(UserError):
            req.with_user(self.user_b).action_approve()

    # ------------------------------------------------------------------
    # test_group_any_of
    # ------------------------------------------------------------------

    def test_group_any_of(self):
        """approver_mode=group：任一群組成員核准即可過關。"""
        grp = self.env["res.groups"].create({"name": "Test Approver Group"})
        self.user_a.group_ids = [Command.link(grp.id)]
        self.user_b.group_ids = [Command.link(grp.id)]
        self.user_c.group_ids = [Command.link(grp.id)]
        self._make_rule([
            {
                "name": "G-Any",
                "approver_mode": "group",
                "group_id": grp.id,
            },
        ])
        _rec, req = self._submit()
        # 3 個人都應該在 line 名單中
        step_lines = req.line_ids.filtered(lambda ln: ln.step_id.name == "G-Any")
        self.assertEqual(len(step_lines), 3)
        # A 簽完即過關
        req.with_user(self.user_a).action_approve()
        self.assertEqual(req.state, "approved")

    # ------------------------------------------------------------------
    # test_group_all_required
    # ------------------------------------------------------------------

    def test_group_all_required(self):
        """approver_mode=group_all：全員皆要核可才過關。"""
        grp = self.env["res.groups"].create({"name": "Test All-Required Group"})
        self.user_a.group_ids = [Command.link(grp.id)]
        self.user_b.group_ids = [Command.link(grp.id)]
        self._make_rule([
            {
                "name": "G-All",
                "approver_mode": "group_all",
                "group_id": grp.id,
            },
        ])
        _rec, req = self._submit()
        # A 簽完仍 pending
        req.with_user(self.user_a).action_approve()
        self.assertEqual(req.state, "pending")
        # B 簽完才 approved
        req.with_user(self.user_b).action_approve()
        self.assertEqual(req.state, "approved")

    # ------------------------------------------------------------------
    # test_field_mode
    # ------------------------------------------------------------------

    def test_field_mode_uses_record_user(self):
        """approver_mode=field：簽核者由單據上的 approver_user_id 決定。"""
        self._make_rule([
            {
                "name": "Field",
                "approver_mode": "field",
                "approver_field": "approver_user_id",
            },
        ])
        rec = self.TestModel.create({"approver_user_id": self.user_d.id})
        rec.action_submit_for_approval()
        req = rec.approval_request_id
        self.assertEqual(len(req.line_ids), 1)
        self.assertEqual(req.line_ids.user_id, self.user_d)
        req.with_user(self.user_d).action_approve()
        self.assertEqual(req.state, "approved")

    # ------------------------------------------------------------------
    # test_unauthorized_user_cannot_approve
    # ------------------------------------------------------------------

    def test_unauthorized_user_cannot_approve(self):
        """非本關卡簽核者不可核准。"""
        self._make_rule([
            {"name": "S1", "approver_mode": "user", "user_ids": [Command.set([self.user_a.id])]},
        ])
        _rec, req = self._submit()
        with self.assertRaises(UserError):
            req.with_user(self.user_b).action_approve()
