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
        # Odoo 20 已移除 name_get()，顯示名稱改由 display_name 提供
        self.assertEqual(tag.display_name, tag.name)

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

    def test_05_new_internal_user_gets_mfg_group(self):
        """新建內部使用者時自動加入 MFG Custom 共用群組（否則看不到 MFG Custom 選單）。"""
        user = self.env["res.users"].create({
            "name": "MFG 新人",
            "login": "mfg_auto_group_user",
            "groups_id": [(6, 0, [self.env.ref("base.group_user").id])],
        })
        self.assertIn(
            self.env.ref("mfg_custom_base.group_user"),
            user.all_group_ids,
            "新建的內部使用者應自動加入 MFG Custom 共用群組",
        )

    def test_06_portal_user_not_in_mfg_group(self):
        """Portal（外部）使用者不應取得 MFG Custom 群組。"""
        user = self.env["res.users"].create({
            "name": "外部使用者",
            "login": "mfg_portal_user",
            "groups_id": [(6, 0, [self.env.ref("base.group_portal").id])],
        })
        self.assertNotIn(
            self.env.ref("mfg_custom_base.group_user"),
            user.all_group_ids,
            "Portal 使用者不應自動加入 MFG Custom 共用群組",
        )

    def test_05_groups_defined(self):
        """驗證 4 個共用群組皆已建立。"""
        Groups = self.env["res.groups"]
        self.assertTrue(Groups.search([("name", "=", "User"), ("privilege_id.name", "=", "MFG Custom")]))
        self.assertTrue(Groups.search([("name", "=", "Manager"), ("privilege_id.name", "=", "MFG Custom")]))
        self.assertTrue(Groups.search([("name", "=", "Engineering"), ("privilege_id.name", "=", "MFG Custom")]))
        self.assertTrue(Groups.search([("name", "=", "Quality"), ("privilege_id.name", "=", "MFG Custom")]))
