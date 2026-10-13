# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


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
        product = self.env.ref("product.product_product_4")
        bom = self.env["mrp.bom"].search([("product_tmpl_id", "=", product.product_tmpl_id.id)], limit=1)
        if not bom:
            self.skipTest("需要 mrp demo BOM 才能測試")
        mo = self.env["mrp.production"].create({
            "product_id": product.id,
            "product_qty": 1.0,
            "bom_id": bom.id,
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
