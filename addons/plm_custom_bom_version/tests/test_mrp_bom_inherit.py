# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestMrpBomInherit(TransactionCase):
    """測試 mrp.bom 的 PLM Custom 擴充欄位與快照動作。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Bom = cls.env["mrp.bom"]
        cls.product = cls.env["product.product"].create(
            {
                "name": "PLM Inherit FG",
                "type": "consu",
                "is_storable": True,
            }
        )
        cls.bom = cls.Bom.create(
            {
                "product_tmpl_id": cls.product.product_tmpl_id.id,
                "product_id": cls.product.id,
                "product_qty": 1.0,
            }
        )

    def test_01_default_version(self):
        """新 BOM 預設 plm_custom_version='1.0'、plm_custom_is_current=True。"""
        self.assertEqual(self.bom.plm_custom_version, "1.0")
        self.assertTrue(self.bom.plm_custom_is_current)
        self.assertEqual(self.bom.plm_custom_version_count, 0)

    def test_02_snapshot_action_increments_count(self):
        """呼叫 action_snapshot 後，plm_custom_version_count +1。"""
        before = self.bom.plm_custom_version_count
        self.bom.action_snapshot()
        self.assertEqual(self.bom.plm_custom_version_count, before + 1)
        # 重新計算後，current_version 應指向最新快照
        self.assertTrue(self.bom.plm_custom_current_version_id)

    def test_03_action_view_versions_returns_action(self):
        """action_view_versions 應回傳 action dict 並帶上正確 domain。"""
        self.bom.action_snapshot()
        action = self.bom.action_view_versions()
        self.assertEqual(action["res_model"], "mrp.bom.version")
        self.assertIn(("bom_id", "=", self.bom.id), action["domain"])
