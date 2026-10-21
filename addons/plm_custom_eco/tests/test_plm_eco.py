# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged("post_install", "-at_install", "mfg_custom", "plm_custom")
class TestPlmCustomEco(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Eco = cls.env["plm_custom.eco"]
        cls.product = cls.env.ref("product.product_product_4")
        cls.bom = cls.env["mrp.bom"].search(
            [("product_tmpl_id", "=", cls.product.product_tmpl_id.id)], limit=1
        )
        cls.user = cls.env.ref("base.user_admin")

    def _make_rule(self, steps=None):
        """建立 ECO 的簽核規則（供測試送簽使用）。"""
        if steps is None:
            steps = [
                {
                    "name": "經理核准",
                    "approver_mode": "group",
                    "group_id": self.env.ref("mfg_custom_base.group_manager").id,
                },
            ]
        return self.env["mfg_custom.approval.rule"].create({
            "name": "ECO 測試規則",
            "model_id": self.env["ir.model"]._get("plm_custom.eco").id,
            "step_ids": [Command.create(s) for s in steps],
        })

    def _ensure_impact_lines(self, eco):
        """確保 ECO 有影響清單（送簽的前置條件）。"""
        if eco.line_ids:
            return
        self.env["plm_custom.eco.line"].create({
            "eco_id": eco.id,
            "impact_type": "other",
            "res_model": "product.product",
            "res_id": eco.product_id.id,
            "description": "測試用影響項目",
        })

    def _create_eco(self, **kwargs):
        vals = {
            "subject": "測試 ECO",
            "type": "process",
            "origin": "internal",
            "product_id": self.product.id,
            "bom_id": self.bom.id if self.bom else self.env["mrp.bom"].create({
                "product_tmpl_id": self.product.product_tmpl_id.id,
                "product_qty": 1.0,
            }).id,
            "from_version": "1.0",
            "to_version": "1.1",
            "owner_id": self.user.id,
        }
        vals.update(kwargs)
        if not self.bom:
            self.bom = self.env["mrp.bom"].browse(vals["bom_id"])
        return self.Eco.create(vals)

    def test_01_create_default_draft(self):
        eco = self._create_eco()
        self.assertEqual(eco.state, "draft")
        self.assertTrue(eco.name.startswith("ECO/"))

    def test_02_version_constraint(self):
        with self.assertRaises(ValidationError):
            self._create_eco(from_version="1.0", to_version="1.0")

    def test_03_state_transition_draft_to_impact(self):
        eco = self._create_eco()
        eco.action_start_analysis()
        self.assertEqual(eco.state, "impact_analysis")

    def test_04_cannot_submit_unfinished(self):
        eco = self._create_eco()
        with self.assertRaises(UserError):
            eco.action_submit_approval()

    def test_05_cannot_apply_before_approved(self):
        eco = self._create_eco()
        eco.action_start_analysis()
        with self.assertRaises(UserError):
            eco.action_apply()

    def test_06_cancel_from_draft(self):
        eco = self._create_eco()
        eco.action_cancel()
        self.assertEqual(eco.state, "cancelled")

    def test_07_cannot_reset_applied(self):
        eco = self._create_eco()
        eco.write({"state": "applied"})
        with self.assertRaises(UserError):
            eco.action_reset_to_draft()

    def test_08_cannot_apply_twice(self):
        eco = self._create_eco()
        eco.write({"state": "applied"})
        with self.assertRaises(UserError):
            eco.action_apply()

    def test_09_reject_sets_state(self):
        """簽核被駁回時，ECO 狀態同步為已駁回。"""
        self._make_rule()
        eco = self._create_eco()
        eco.action_start_analysis()
        self._ensure_impact_lines(eco)
        eco.action_submit_approval()
        self.assertEqual(eco.state, "pending_approval")

        eco.approval_request_id.with_user(self.user).action_reject(reason="資料不全")
        eco.invalidate_recordset()
        self.assertEqual(eco.approval_request_id.state, "rejected")
        self.assertEqual(eco.state, "rejected")

    def test_10_multi_step_keeps_state_until_all_approved(self):
        """多關卡只核准第一關時，ECO 與簽核單都不得變成已核准。"""
        user_a = new_test_user(self.env, login="eco_approver_a", groups="base.group_user")
        user_b = new_test_user(self.env, login="eco_approver_b", groups="base.group_user")
        self._make_rule(steps=[
            {
                "name": "第一關",
                "approver_mode": "user",
                "user_ids": [Command.set([user_a.id])],
            },
            {
                "name": "第二關",
                "approver_mode": "user",
                "user_ids": [Command.set([user_b.id])],
            },
        ])
        eco = self._create_eco()
        eco.action_start_analysis()
        self._ensure_impact_lines(eco)
        eco.action_submit_approval()
        req = eco.approval_request_id
        self.assertEqual(eco.state, "pending_approval")

        # 只核准第一關
        req.with_user(user_a).action_approve()
        eco.invalidate_recordset()
        req.invalidate_recordset()
        self.assertEqual(req.state, "pending")
        self.assertEqual(
            eco.state,
            "pending_approval",
            "只核准第一關時，ECO 不得提前變成已核准",
        )

        # 全部核准後才同步
        req.with_user(user_b).action_approve()
        eco.invalidate_recordset()
        req.invalidate_recordset()
        self.assertEqual(req.state, "approved")
        self.assertEqual(eco.state, "approved")

    def test_11_cannot_apply_before_full_approval(self):
        """簽核尚未全部通過時，ECO 不得套用。"""
        user_a = new_test_user(self.env, login="eco_approver_c", groups="base.group_user")
        user_b = new_test_user(self.env, login="eco_approver_d", groups="base.group_user")
        self._make_rule(steps=[
            {
                "name": "第一關",
                "approver_mode": "user",
                "user_ids": [Command.set([user_a.id])],
            },
            {
                "name": "第二關",
                "approver_mode": "user",
                "user_ids": [Command.set([user_b.id])],
            },
        ])
        eco = self._create_eco()
        eco.action_start_analysis()
        self._ensure_impact_lines(eco)
        eco.action_submit_approval()
        eco.approval_request_id.with_user(user_a).action_approve()
        eco.invalidate_recordset()
        with self.assertRaises(UserError):
            eco.action_apply()
