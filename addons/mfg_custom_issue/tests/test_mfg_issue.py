# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged("post_install", "-at_install", "mfg_custom", "plm_custom")
class TestMfgCustomIssue(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Issue = cls.env["mfg_custom.issue"]
        cls.Stage = cls.env["mfg_custom.issue.stage"]
        cls.Action = cls.env["mfg_custom.issue.action"]
        cls.user = cls.env.ref("base.user_admin")
        # 確保至少有「開立」與「已結案」兩個 stage
        cls.open_stage = cls.Stage.search([("is_closed", "=", False), ("fold", "=", False)], order="sequence", limit=1)
        cls.closed_stage = cls.Stage.search([("is_closed", "=", True)], limit=1)

    def test_01_create_with_defaults(self):
        issue = self.Issue.create({
            "subject": "測試問題点",
            "description": "<p>測試現象</p>",
            "issue_type": "defect",
            "user_id": self.user.id,
        })
        self.assertTrue(issue.name and issue.name != "New")
        self.assertTrue(issue.code and issue.code != "New")
        self.assertEqual(issue.state, "open")

    def test_02_state_open_by_default(self):
        issue = self.Issue.create({
            "subject": "X",
            "description": "<p>X</p>",
            "issue_type": "defect",
            "stage_id": self.open_stage.id,
        })
        self.assertEqual(issue.state, "open")

    def test_03_state_closed_when_stage_is_closed(self):
        issue = self.Issue.create({
            "subject": "X",
            "description": "<p>X</p>",
            "issue_type": "defect",
            "stage_id": self.closed_stage.id,
        })
        self.assertEqual(issue.state, "closed")
        self.assertTrue(issue.closed_date)

    def test_04_action_close(self):
        issue = self.Issue.create({
            "subject": "X",
            "description": "<p>X</p>",
            "issue_type": "defect",
            "stage_id": self.open_stage.id,
        })
        issue.action_close()
        self.assertEqual(issue.state, "closed")
        self.assertEqual(issue.stage_id, self.closed_stage)

    def test_05_action_reopen(self):
        issue = self.Issue.create({
            "subject": "X",
            "description": "<p>X</p>",
            "issue_type": "defect",
            "stage_id": self.closed_stage.id,
        })
        issue.action_reopen()
        self.assertIn(issue.state, ("open", "analyzing"))
        self.assertFalse(issue.closed_date)

    def test_06_action_create_under_mo(self):
        """從 MO 建立 issue。"""
        # 測試庫沒有 demo 資料，自行建立產品與 BOM
        product = self.env["product.product"].create({
            "name": "問題點測試產品",
            "type": "consu",
            "is_storable": True,
        })
        bom = self.env["mrp.bom"].create({
            "product_id": product.id,
            "product_tmpl_id": product.product_tmpl_id.id,
            "product_qty": 1.0,
            "uom_id": product.uom_id.id,
            "type": "normal",
        })
        mo = self.env["mrp.production"].create({
            "product_id": product.id,
            "product_qty": 1.0,
            "bom_id": bom.id,
            "uom_id": product.uom_id.id,
        })
        issue = self.Issue.create({
            "subject": "MO 端建立",
            "description": "<p>X</p>",
            "issue_type": "defect",
            "production_id": mo.id,
            "product_id": product.id,
        })
        self.assertEqual(issue.production_id, mo)
        self.assertEqual(mo.mfg_custom_issue_count, 1)

    def test_07_priority_index(self):
        """高 priority issue 在 _order 中排前面。"""
        issue_a = self.Issue.create({
            "subject": "低優先",
            "description": "<p>X</p>",
            "issue_type": "defect",
            "priority": "0",
        })
        issue_b = self.Issue.create({
            "subject": "緊急",
            "description": "<p>X</p>",
            "issue_type": "defect",
            "priority": "3",
        })
        # mfg_custom.issue 的 _order 是 "priority desc, create_date desc"
        ordered = self.Issue.search([("id", "in", [issue_a.id, issue_b.id])])
        self.assertEqual(ordered[0], issue_b)

    def test_08_action_set_state(self):
        issue = self.Issue.create({
            "subject": "X",
            "description": "<p>X</p>",
            "issue_type": "defect",
        })
        action = self.Action.create({
            "issue_id": issue.id,
            "name": "測試對策",
            "owner_id": self.user.id,
            "deadline": "2026-12-31",
        })
        action.action_set_state("done")
        self.assertEqual(action.state, "done")
        self.assertTrue(action.done_date)


@tagged("post_install", "-at_install", "mfg_custom", "plm_custom")
class TestMfgIssueApproval(TransactionCase):
    """測試問題点的簽核引擎回寫。

    問題点的 ``state`` 由 ``stage_id`` 推導，因此簽核結果一律以「移動階段」
    的方式回寫：核准 → 結案、駁回 → 分析中、取消 → 開立。
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Issue = cls.env["mfg_custom.issue"]
        cls.Stage = cls.env["mfg_custom.issue.stage"]
        cls.Rule = cls.env["mfg_custom.approval.rule"]
        cls.approver = new_test_user(
            cls.env,
            login="issue_approver",
            groups="base.group_user,mfg_custom_base.group_manager",
        )
        cls.open_stage = cls.Stage.search(
            [("is_closed", "=", False), ("fold", "=", False)],
            order="sequence",
            limit=1,
        )
        cls.analyzing_stage = cls.Stage.search(
            [("name", "=", "分析中"), ("is_closed", "=", False)],
            limit=1,
        )
        cls.implementing_stage = cls.Stage.search(
            [("fold", "=", True), ("is_closed", "=", False)],
            order="sequence",
            limit=1,
        )
        cls.closed_stage = cls.Stage.search([("is_closed", "=", True)], limit=1)
        # 測試規則 sequence=1 → 優先於種子規則「問題點結案審核」
        cls.rule = cls.Rule.create({
            "name": "問題點測試簽核規則",
            "model_id": cls.env["ir.model"]._get("mfg_custom.issue").id,
            "sequence": 1,
            "step_ids": [
                Command.create({
                    "name": "測試核准",
                    "approver_mode": "user",
                    "user_ids": [Command.set([cls.approver.id])],
                }),
            ],
        })

    def _new_issue(self, **extra):
        vals = {
            "subject": "簽核測試問題点",
            "description": "<p>測試現象</p>",
            "issue_type": "defect",
            "stage_id": self.implementing_stage.id,
        }
        vals.update(extra)
        return self.Issue.create(vals)

    def test_01_before_submit_blocks_closed_issue(self):
        """已結案的問題点不可再送出簽核。"""
        issue = self._new_issue(stage_id=self.closed_stage.id)
        with self.assertRaises(UserError):
            issue.action_submit_for_approval()

    def test_02_approved_moves_to_closed_stage(self):
        """簽核全部通過 → 移至結案階段，state 變 closed。"""
        issue = self._new_issue()
        issue.action_submit_for_approval()
        self.assertEqual(issue.approval_state, "pending")
        issue.approval_request_id.with_user(self.approver).action_approve()
        issue.invalidate_recordset()
        self.assertEqual(issue.stage_id, self.closed_stage)
        self.assertEqual(issue.state, "closed")
        self.assertTrue(issue.closed_date)
        self.assertEqual(issue.approval_state, "approved")

    def test_03_rejected_moves_to_analyzing_stage(self):
        """簽核駁回 → 退回「分析中」階段，state 回到 open。"""
        issue = self._new_issue()
        issue.action_submit_for_approval()
        issue.approval_request_id.with_user(self.approver).action_reject(
            reason="分析資料不足",
        )
        issue.invalidate_recordset()
        self.assertEqual(issue.stage_id, self.analyzing_stage)
        self.assertEqual(issue.state, "open")
        self.assertEqual(issue.approval_state, "rejected")

    def test_04_cancelled_moves_to_open_stage(self):
        """簽核取消 → 退回「開立」階段。"""
        issue = self._new_issue()
        issue.action_submit_for_approval()
        issue.action_cancel_approval()
        issue.invalidate_recordset()
        self.assertEqual(issue.stage_id, self.open_stage)
        self.assertEqual(issue.state, "open")
        self.assertFalse(issue.closed_date)
        self.assertEqual(issue.approval_state, "not_required")
