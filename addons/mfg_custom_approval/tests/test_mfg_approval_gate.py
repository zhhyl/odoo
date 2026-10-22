# Part of Odoo. See LICENSE file for full copyright and licensing details.

"""針對 20.0.1.1.0 修正的缺陷所新增的回歸測試。"""

from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged("post_install", "-at_install", "mfg_custom", "plm_custom")
class TestMfgApprovalGate(TransactionCase):
    """驗證簽核引擎的守門、重送與權限限制。"""

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
        cls.user_a = new_test_user(cls.env, login="gate_a", groups="base.group_user,mfg_custom_base.group_user")
        cls.user_b = new_test_user(cls.env, login="gate_b", groups="base.group_user,mfg_custom_base.group_user")
        cls.user_c = new_test_user(cls.env, login="gate_c", groups="base.group_user,mfg_custom_base.group_user")
        cls.model_id = cls.env["ir.model"]._get(
            "mfg_custom.approval.test.model"
        ).id

    def _make_rule(
        self,
        name="Gate Rule",
        steps=None,
        company=None,
        sequence=10,
        domain=None,
        due_days=0,
    ):
        if steps is None:
            steps = [{
                "name": "S1",
                "approver_mode": "user",
                "user_ids": [Command.set([self.user_a.id])],
            }]
        return self.Rule.create({
            "name": name,
            "model_id": self.model_id,
            "sequence": sequence,
            "domain": domain or False,
            "due_days": due_days,
            "company_id": company.id if company else self.env.company.id,
            "step_ids": [Command.create(s) for s in steps],
        })

    def _submit(self, vals=None):
        rec = self.TestModel.create(vals or {})
        rec.action_submit_for_approval()
        return rec, rec.approval_request_id

    # ------------------------------------------------------------------
    # 規則必須綁定到已掛載簽核功能的模型
    # ------------------------------------------------------------------

    def test_01_rule_requires_approvable_model(self):
        """未掛載簽核 mixin 的模型不可設定簽核規則。"""
        other_model = self.env["ir.model"]._get("res.partner")
        with self.assertRaises(ValidationError):
            self.Rule.create({
                "name": "不合法規則",
                "model_id": other_model.id,
                "step_ids": [Command.create({
                    "name": "S1",
                    "approver_mode": "user",
                    "user_ids": [Command.set([self.user_a.id])],
                })],
            })

    # ------------------------------------------------------------------
    # 沒有簽核者的關卡不可送出（避免送出後永久卡在待簽核）
    # ------------------------------------------------------------------

    def test_02_step_without_approver_raises_on_submit(self):
        """關卡解析不到簽核者時，送出當下就應報錯，不得產生無人可簽的單據。"""
        approver_field = self.env["ir.model.fields"].search(
            [
                ("model", "=", "mfg_custom.approval.test.model"),
                ("name", "=", "approver_user_id"),
            ],
            limit=1,
        )
        self._make_rule(steps=[{
            "name": "Field",
            "approver_mode": "field",
            "approver_field_id": approver_field.id,
        }])
        rec = self.TestModel.create({})  # approver_user_id 留空
        with self.assertRaises(UserError):
            rec.action_submit_for_approval()
        self.assertFalse(rec.approval_request_id)
        self.assertEqual(self.Request.search_count([]), 0)

    # ------------------------------------------------------------------
    # 駁回後可重新送出簽核
    # ------------------------------------------------------------------

    def test_03_resubmit_after_reject(self):
        """駁回後可再次送出簽核，並重用同一張簽核單。"""
        self._make_rule()
        rec, req = self._submit()
        req.with_user(self.user_a).action_reject(reason="資料不全")
        self.assertEqual(req.state, "rejected")

        rec.action_submit_for_approval()
        rec.invalidate_recordset()
        self.assertEqual(req.state, "pending")
        self.assertEqual(rec.approval_request_id, req)
        # 舊的簽核紀錄應被清掉並重建
        self.assertEqual(len(req.line_ids), 1)
        self.assertEqual(req.line_ids.decision, "pending")
        self.assertFalse(req.reason)

    # ------------------------------------------------------------------
    # 核准後可再走第二輪簽核
    # ------------------------------------------------------------------

    def test_04_second_round_after_approval(self):
        """核准後可再送出一次簽核（第二輪）。"""
        self._make_rule()
        rec, req = self._submit()
        req.with_user(self.user_a).action_approve()
        self.assertEqual(req.state, "approved")

        rec.action_submit_for_approval()
        rec.invalidate_recordset()
        self.assertEqual(req.state, "pending")
        self.assertEqual(rec.approval_request_id, req)

    # ------------------------------------------------------------------
    # 被駁回 / 已取消的簽核單可重設為草稿
    # ------------------------------------------------------------------

    def test_05_reset_to_draft_allows_rejected(self):
        """被駁回的簽核單可重設為草稿並重新開始。"""
        self._make_rule()
        _rec, req = self._submit()
        req.with_user(self.user_a).action_reject(reason="退件")
        self.assertEqual(req.state, "rejected")
        req.action_reset_to_draft()
        self.assertEqual(req.state, "pending")
        self.assertEqual(len(req.line_ids), 1)

    def test_06_reset_to_draft_rejects_pending(self):
        """進行中的簽核單不可直接重設。"""
        self._make_rule()
        _rec, req = self._submit()
        with self.assertRaises(UserError):
            req.action_reset_to_draft()

    # ------------------------------------------------------------------
    # 審批欄位必須由 mixin 統一提供
    # ------------------------------------------------------------------

    def test_07_approval_fields_defined_by_mixin(self):
        """所有掛載 mixin 的模型都必須沿用 mixin 提供的審批欄位定義。"""
        mixin_cls = type(self.env["mfg_custom.approval.mixin"])
        checked = 0
        for name, model in self.env.registry.models.items():
            if model._abstract or not issubclass(model, mixin_cls):
                continue
            checked += 1
            for field_name in ("approval_request_id", "approval_state"):
                field = model._fields.get(field_name)
                self.assertIsNotNone(
                    field, f"{name} 缺少 {field_name} 欄位"
                )
                self.assertEqual(
                    tuple(field._modules),
                    ("mfg_custom_approval",),
                    f"{name}.{field_name} 被其他模組重新定義，請改用 mixin 的定義",
                )
        self.assertTrue(checked, "測試模型應有掛載 mixin")

    # ------------------------------------------------------------------
    # 簽核紀錄只能由本人修改
    # ------------------------------------------------------------------

    def test_08_only_owner_can_change_decision(self):
        """非簽核者不可變更別人的簽核紀錄。"""
        self._make_rule()
        _rec, req = self._submit()
        line = req.line_ids
        with self.assertRaises(AccessError):
            line.with_user(self.user_b).write({"decision": "approved"})
        # 本人則可
        line.with_user(self.user_a).write({"decision": "approved"})
        self.assertEqual(line.decision, "approved")

    # ------------------------------------------------------------------
    # 規則的公司隔離
    # ------------------------------------------------------------------

    def test_09_match_rule_respects_company(self):
        """其他公司的規則不應被命中。"""
        other_company = self.env["res.company"].create({"name": "其他公司"})
        rule = self._make_rule(name="他公司規則", company=other_company)
        rec = self.TestModel.create({})
        self.assertNotEqual(
            self.Rule._match_rule("mfg_custom.approval.test.model", rec),
            rule,
        )

    # ------------------------------------------------------------------
    # 多簽核人關卡：任一核准即可推進（不需等待其他人簽）
    # ------------------------------------------------------------------

    def test_10_multi_approver_step_advances(self):
        """關卡有多位簽核者時，任一核准即可推進到下一關。

        舊實作會讓「當前關卡」停在已有人核准的關卡，
        導致下一關的簽核者永遠輪不到。
        """
        grp = self.env["res.groups"].create({"name": "Gate Multi Approver"})
        self.user_a.group_ids = [Command.link(grp.id)]
        self.user_b.group_ids = [Command.link(grp.id)]
        self._make_rule(steps=[
            {
                "name": "S1",
                "approver_mode": "group",
                "group_id": grp.id,
            },
            {
                "name": "S2",
                "approver_mode": "user",
                "user_ids": [Command.set([self.user_c.id])],
            },
        ])
        _rec, req = self._submit()
        self.assertEqual(len(req.line_ids), 3)
        self.assertEqual(req.current_step_no, 1)

        # A 核准即過關，流程自動推進到第二關
        req.with_user(self.user_a).action_approve()
        self.assertEqual(req.state, "pending")
        self.assertEqual(req.current_step_no, 2)
        # 其他簽核者的待簽紀錄自動略過
        skipped = req.line_ids.filtered(lambda ln: ln.decision == "skipped")
        self.assertEqual(len(skipped), 1)

        # 第二關可由 C 簽核並結案
        req.with_user(self.user_c).action_approve()
        self.assertEqual(req.state, "approved")

    # ------------------------------------------------------------------
    # 簽核狀態不可被直接改寫（否則可繞過所有關卡）
    # ------------------------------------------------------------------

    def test_11_user_cannot_write_request_state(self):
        """一般使用者不可直接改寫簽核單狀態。"""
        self._make_rule()
        _rec, req = self._submit()
        with self.assertRaises(AccessError):
            req.with_user(self.user_b).write({"state": "approved"})
        self.assertEqual(req.state, "pending")

    def test_12_user_cannot_delete_other_request(self):
        """非申請人不可刪除簽核單。"""
        self._make_rule()
        _rec, req = self._submit()
        with self.assertRaises(AccessError):
            req.with_user(self.user_b).unlink()
        self.assertTrue(req.exists())

    # ------------------------------------------------------------------
    # 金額門檻：一般 Float 欄位（Odoo 20 只有 Monetary 有幣別換算）
    # ------------------------------------------------------------------

    def test_17_due_date_from_rule(self):
        """簽核期限依規則的「簽核期限（天）」自動帶出。"""
        self._make_rule(due_days=3)
        rec = self.TestModel.create({})
        rec.action_submit_for_approval()
        req = rec.approval_request_id
        self.assertTrue(req.due_date)
        self.assertEqual(
            req.due_date,
            fields.Date.today() + timedelta(days=3),
        )
        self.assertFalse(req.is_overdue)

    def test_18_overdue_cron_notifies(self):
        """逾期的待簽核申請會被每日 cron 找出並留下提醒。"""
        self._make_rule(due_days=1)
        rec = self.TestModel.create({})
        rec.action_submit_for_approval()
        req = rec.approval_request_id
        # 改成昨天到期
        req.due_date = fields.Date.today() - timedelta(days=1)
        self.assertTrue(req.is_overdue)
        count = self.Request._cron_notify_overdue_approvals()
        self.assertEqual(count, 1)
        # 提醒訊息應貼在簽核單上
        bodies = req.message_ids.mapped("body")
        self.assertTrue(
            any("逾期" in (body or "") for body in bodies),
            "應留下逾期提醒訊息",
        )

    def test_19_no_due_date_means_no_reminder(self):
        """規則未設定期限時，不列入逾期提醒。"""
        self._make_rule()
        rec = self.TestModel.create({})
        rec.action_submit_for_approval()
        self.assertFalse(rec.approval_request_id.due_date)
        self.assertEqual(self.Request._cron_notify_overdue_approvals(), 0)

    def test_14_selectable_models_exclude_test_model(self):
        """管理者可選的單據類型不得包含測試用模型，但規則仍可對它建立。"""
        selectable = self.Rule._get_selectable_models()
        approvable = self.Rule._get_approvable_models()
        self.assertNotIn("mfg_custom.approval.test.model", selectable)
        self.assertIn("mfg_custom.approval.test.model", approvable)

    def test_15_rule_domain_field_must_exist(self):
        """規則的適用條件若引用不存在的欄位，儲存時即報錯（避免單據表單開不起來）。"""
        with self.assertRaises(ValidationError):
            self._make_rule(domain="[('no_such_field', '=', 1)]")

    def test_16_business_model_can_add_extra_domain(self):
        """單據端可透過 _get_approval_rule_domain() 追加條件（與規則 domain 取 AND）。"""
        self._make_rule(domain="[('state', '=', 'confirmed')]")
        rec = self.TestModel.create({"state": "confirmed"})
        self.assertTrue(self.Rule._match_rule("mfg_custom.approval.test.model", rec))
        rec2 = self.TestModel.create({"state": "draft"})
        self.assertFalse(
            self.Rule._match_rule("mfg_custom.approval.test.model", rec2)
        )

    def test_13_float_amount_threshold_works(self):
        """金額門檻套用在 Float 欄位時不應拋 AttributeError。"""
        self._make_rule(steps=[{
            "name": "Amount",
            "approver_mode": "user",
            "user_ids": [Command.set([self.user_a.id])],
            "min_amount": 100,
        }])
        rec = self.TestModel.create({"amount_total": 500})
        rec.action_submit_for_approval()
        req = rec.approval_request_id
        self.assertEqual(req.state, "pending")
        self.assertEqual(len(req.line_ids), 1)
