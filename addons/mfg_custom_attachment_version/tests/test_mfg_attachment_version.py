# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install", "mfg_custom", "plm_custom")
class TestMfgAttachmentVersion(TransactionCase):
    """測試 ``mfg_custom_attachment_version`` 模組的版本與狀態控管邏輯."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Attachment = cls.env["ir.attachment"]
        cls.TagModel = cls.env["mfg_custom.attachment.tag"]
        # 任意挑一個穩定的 res_model/res_id 當掛載點：res.partner 的 self.env.company
        cls.partner = cls.env["res.partner"].create({"name": "MFG Attachment Test Partner"})

    # ---------------------------------------------------------------
    # 工具
    # ---------------------------------------------------------------

    def _make_attachment(self, *, res_id=False, name="customer_spec.pdf",
                         doc_type="customer_spec", doc_state="released",
                         version=None, raw=b"v1"):
        vals = {
            "name": name,
            "res_model": "res.partner" if res_id else False,
            "res_id": res_id or False,
            "type": "binary",
            "mfg_custom_doc_type": doc_type,
            "mfg_custom_doc_state": doc_state,
            "raw": raw,
        }
        if version is not None:
            vals["mfg_custom_version"] = version
        return self.Attachment.create(vals)

    # ---------------------------------------------------------------
    # 案例
    # ---------------------------------------------------------------

    def test_01_new_version_increments(self):
        """同 res_model+res_id+name 上傳第二版 → version=2（且與首版不再衝突）."""
        v1 = self._make_attachment(res_id=self.partner.id, doc_state="released", raw=b"v1")
        v2 = self._make_attachment(res_id=self.partner.id, doc_state="released", raw=b"v2")

        self.assertEqual(v1.mfg_custom_version, 1)
        self.assertEqual(v2.mfg_custom_version, 2)

        # DB 內有兩筆同名附件，版本遞增
        same_group = self.Attachment.search([
            ("res_model", "=", "res.partner"),
            ("res_id", "=", self.partner.id),
            ("name", "=", "customer_spec.pdf"),
        ])
        self.assertEqual(len(same_group), 2)

    def test_02_released_obsoletes_previous(self):
        """新附件 state=released → 既有 released 同群組轉為 obsolete 且 superseded_by 指到自身."""
        v1 = self._make_attachment(res_id=self.partner.id, doc_state="released", raw=b"v1")
        v2 = self._make_attachment(res_id=self.partner.id, doc_state="released", raw=b"v2")

        v1.invalidate_recordset()
        self.assertEqual(v1.mfg_custom_doc_state, "obsolete")
        self.assertEqual(v1.mfg_custom_superseded_by_id.id, v2.id)

        # v2 自身仍是 released，沒有被取代
        self.assertEqual(v2.mfg_custom_doc_state, "released")
        self.assertFalse(v2.mfg_custom_superseded_by_id)

    def test_03_draft_does_not_obsolete_predecessor(self):
        """新附件若是 draft/in_review，不會動到既有附件的狀態."""
        v1 = self._make_attachment(res_id=self.partner.id, doc_state="released", raw=b"v1")
        v2 = self._make_attachment(res_id=self.partner.id, doc_state="draft", raw=b"v2")

        v1.invalidate_recordset()
        self.assertEqual(v1.mfg_custom_doc_state, "released")
        # version 依然遞增，但 superseded_by 留空
        self.assertEqual(v2.mfg_custom_version, 2)
        self.assertFalse(v1.mfg_custom_superseded_by_id)
        self.assertFalse(v2.mfg_custom_superseded_by_id)

    def test_04_eco_bump_helper(self):
        """`_mfg_custom_bump_version` 對單一附件：建立新版本、自身標為 obsolete 並指向新版."""
        original = self._make_attachment(res_id=self.partner.id, doc_state="released", raw=b"v1")
        new = original._mfg_custom_bump_version(reason="ECO-001")

        self.assertEqual(len(new), 1)
        # 新版沿用 res_model / res_id / name，版本 +1，state 退回 draft
        self.assertEqual(new.res_model, "res.partner")
        self.assertEqual(new.res_id, self.partner.id)
        self.assertEqual(new.name, original.name)
        self.assertEqual(new.mfg_custom_version, original.mfg_custom_version + 1)
        self.assertEqual(new.mfg_custom_doc_state, "draft")
        # ir.attachment 在 Odoo 20 沒有 chatter，觸發原因記在「版本說明」
        self.assertEqual(new.mfg_custom_version_reason, "ECO-001")

        # 原附件 invalidate 後讀取：obsolete + 指向新版
        original.invalidate_recordset()
        self.assertEqual(original.mfg_custom_doc_state, "obsolete")
        self.assertEqual(original.mfg_custom_superseded_by_id.id, new.id)

    def test_05_release_action(self):
        """使用者動作 action_mfg_custom_release：把草稿/審核中一次切到 released."""
        att = self._make_attachment(res_id=self.partner.id, doc_state="draft", raw=b"v3")
        att.action_mfg_custom_release()
        att.invalidate_recordset()
        self.assertEqual(att.mfg_custom_doc_state, "released")

    def test_06_release_action_rejects_released(self):
        """已是 released 的附件呼叫 release 應直接拋錯，避免誤觸."""
        att = self._make_attachment(res_id=self.partner.id, doc_state="released", raw=b"v4")
        with self.assertRaises(UserError):
            att.action_mfg_custom_release()

    def test_07_tag_create_and_crud(self):
        """附件標籤字典基本 CRUD。"""
        tag = self.TagModel.create({"name": "客戶機密", "color": 9})
        self.assertTrue(tag.id)
        self.assertTrue(tag.active)
        self.assertEqual(tag.color, 9)

        tag.write({"description": "出貨前僅限 QA 與業務主管"})
        self.assertEqual(tag.description, "出貨前僅限 QA 與業務主管")

        # 與附件的 M2M 對應可寫可讀
        att = self._make_attachment(res_id=self.partner.id, doc_state="draft", raw=b"v5")
        att.write({"mfg_custom_tag_ids": [(4, tag.id)]})
        att.invalidate_recordset()
        self.assertIn(tag, att.mfg_custom_tag_ids)
