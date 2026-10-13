# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install", "mfg_custom", "plm_custom")
class TestMfgCustomBase(TransactionCase):
    """測試 mfg_custom_base 模組的共用 mixin 與基礎設施。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # 為了測試 mixin，建立一個臨時具體模型。
        # 由於抽象模型不可直接 instantiate，這裡改用既有 mfg_custom.tag 驗證 mixin 機制。
        cls.Tag = cls.env["mfg_custom.tag"]
        cls.company = cls.env.company

    def test_01_tag_create_and_sequence(self):
        """建立標籤並驗證基本欄位。"""
        tag = self.Tag.create({"name": "高優先", "color": 1})
        self.assertTrue(tag.id)
        self.assertEqual(tag.name, "高優先")
        self.assertTrue(tag.active)
        self.assertIn(
            (tag.id, tag.name),
            tag.name_get(),
            "name_get 應回傳 (id, name) tuple",
        )

    def test_02_tag_translation(self):
        """標籤名稱欄位為 translate=True。"""
        field = self.Tag._fields["name"]
        self.assertTrue(field.translate, "name 欄位應啟用翻譯")

    def test_03_tag_archived(self):
        """歸檔後 active=False，且 archive 動作可運作。"""
        tag = self.Tag.create({"name": "暫存", "color": 2})
        self.assertTrue(tag.active)
        tag.action_archive()
        self.assertFalse(tag.active)
        tag.action_unarchive()
        self.assertTrue(tag.active)

    def test_04_sequence_used_by_mixin(self):
        """驗證 mixin 的序號 sequence 已建立。"""
        seq = self.env["ir.sequence"].search(
            [("code", "=", "mfg_custom.sequence.mixin")], limit=1
        )
        self.assertTrue(seq, "應自動建立 mfg_custom.sequence.mixin 序號")
        # 簡單呼叫 next_by_code 確保可運作
        val = self.env["ir.sequence"].next_by_code("mfg_custom.sequence.mixin")
        self.assertTrue(val, "序號應能產生")

    def test_05_groups_defined(self):
        """驗證 4 個共用群組皆已建立。"""
        Groups = self.env["res.groups"]
        self.assertTrue(Groups.search([("name", "=", "User"), ("privilege_id.name", "=", "MFG Custom")]))
        self.assertTrue(Groups.search([("name", "=", "Manager"), ("privilege_id.name", "=", "MFG Custom")]))
        self.assertTrue(Groups.search([("name", "=", "Engineering"), ("privilege_id.name", "=", "MFG Custom")]))
        self.assertTrue(Groups.search([("name", "=", "Quality"), ("privilege_id.name", "=", "MFG Custom")]))
