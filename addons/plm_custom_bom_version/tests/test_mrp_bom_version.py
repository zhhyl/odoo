# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install", "mfg_custom", "plm_custom")
class TestMrpBomVersion(TransactionCase):
    """測試 mrp.bom.version 快照主檔與子記錄的 immutable 行為。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Bom = cls.env["mrp.bom"]
        cls.Version = cls.env["mrp.bom.version"]
        cls.Line = cls.env["mrp.bom.version.line"]
        cls.Op = cls.env["mrp.bom.version.operation"]
        cls.Bp = cls.env["mrp.bom.version.byproduct"]
        # 既有 mrp 模組的 demo BOM 應可用；若無，建立一張空白 BOM。
        cls.bom = cls.Bom.search([], limit=1)
        if not cls.bom:
            product = cls.env["product.product"].create(
                {
                    "name": "PLM Test FG",
                    "type": "consu",
                    "is_storable": True,
                }
            )
            component = cls.env["product.product"].create(
                {
                    "name": "PLM Test Component",
                    "type": "consu",
                    "is_storable": True,
                }
            )
            cls.bom = cls.Bom.create(
                {
                    "product_tmpl_id": product.product_tmpl_id.id,
                    "product_id": product.id,
                    "product_qty": 1.0,
                    "bom_line_ids": [
                        (0, 0, {"product_id": component.id, "product_qty": 2.0}),
                    ],
                }
            )
        cls.original_line_count = len(cls.bom.bom_line_ids)

    def test_01_snapshot_creates_versions_and_lines(self):
        """snapshot 後 line_ids 數量等於原 bom line 數。"""
        version = self.Version.create_from_bom(self.bom)
        self.assertTrue(version.id, "snapshot 應有 id")
        self.assertEqual(len(version.line_ids), self.original_line_count)
        self.assertEqual(version.bom_id, self.bom)
        self.assertEqual(version.reason, "manual")

    def test_02_snapshot_locked_immutable(self):
        """snapshot 建立後，修改子記錄應失敗。"""
        version = self.Version.create_from_bom(self.bom)
        line = version.line_ids[:1]
        with self.assertRaises(UserError, msg="快照明細不應允許 write"):
            line.write({"product_qty": 99})
        with self.assertRaises(UserError, msg="快照明細不應允許 unlink"):
            line.unlink()

    def test_03_snapshot_main_locked(self):
        """主檔寫入 locked 欄位應被拒絕。"""
        version = self.Version.create_from_bom(self.bom)
        with self.assertRaises(UserError):
            version.write({"line_ids": [(5, 0, 0)]})

    def test_04_create_from_bom_copies_cost(self):
        """snapshot 應把當時 standard_price 寫到 product_cost。"""
        component = self.bom.bom_line_ids[:1].product_id
        component.standard_price = 12.5
        version = self.Version.create_from_bom(self.bom)
        line = version.line_ids.filtered(lambda l: l.product_id == component)
        self.assertTrue(line, "snapshot 應含對應元件")
        self.assertEqual(line.product_cost, 12.5)
