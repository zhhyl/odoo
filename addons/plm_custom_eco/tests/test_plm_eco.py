# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


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
        eco = self._create_eco()
        eco.action_start_analysis()
        eco.write({"state": "pending_approval"})
        eco.action_reject()
        self.assertEqual(eco.state, "rejected")
