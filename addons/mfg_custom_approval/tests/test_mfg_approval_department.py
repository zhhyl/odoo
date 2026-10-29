# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged("post_install", "-at_install", "mfg_custom", "plm_custom")
class TestMfgApprovalDepartment(TransactionCase):
    """測試以部門推導簽核者的關卡模式。

    簽核者一律以 ``res.users`` 記錄；``department`` / ``department_manager``
    只是用 Odoo 內建的 ``hr.department`` 推導出哪些帳號合格。
    """

    # 註：``_test_user_groups`` 是 ``odoo.addons.base.tests.common.BaseCommon``
    # 的機制，在純 ``TransactionCase`` 下不會生效；本測試直接用系統管理員
    # 環境（``cls.env``），所以不宣告該屬性，避免誤導。

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Rule = cls.env["mfg_custom.approval.rule"]
        cls.Step = cls.env["mfg_custom.approval.step"]
        cls.Request = cls.env["mfg_custom.approval.request"]
        cls.Line = cls.env["mfg_custom.approval.line"]
        cls.Employee = cls.env["hr.employee"]
        cls.Department = cls.env["hr.department"]
        cls.TestModel = cls.env["mfg_custom.approval.test.model"]

        cls.department = cls.Department.create({"name": "研發部"})
        cls.other_department = cls.Department.create({"name": "品保部"})
        cls.no_account_department = cls.Department.create({"name": "無帳號部門"})

        # 沒有對應員工檔案的帳號（系統 / 測試 / Portal 帳號）。
        # **刻意第一個建立**：簽核紀錄的 _order 是 "step_id, user_id, id"，
        # 帳號 id 越小越前面，測試才能確定性地抓到「部門配錯人」的問題。
        cls.user_no_employee = new_test_user(
            cls.env,
            login="dept_no_employee",
            groups="base.group_user,mfg_custom_base.group_user",
        )
        cls.user_member = new_test_user(
            cls.env,
            login="dept_member",
            groups="base.group_user,mfg_custom_base.group_user",
        )
        cls.user_manager = new_test_user(
            cls.env,
            login="dept_manager",
            groups="base.group_user,mfg_custom_base.group_user",
        )
        cls.user_outside = new_test_user(
            cls.env,
            login="dept_outside",
            groups="base.group_user,mfg_custom_base.group_user",
        )

        cls.employee_member = cls.Employee.create({
            "name": "部員小王",
            "user_id": cls.user_member.id,
            "department_id": cls.department.id,
        })
        cls.employee_manager = cls.Employee.create({
            "name": "經理小李",
            "user_id": cls.user_manager.id,
            "department_id": cls.department.id,
        })
        cls.employee_outside = cls.Employee.create({
            "name": "外包小陳",
            "user_id": cls.user_outside.id,
            "department_id": cls.other_department.id,
        })
        cls.employee_no_account = cls.Employee.create({
            "name": "無帳號經理",
            "department_id": cls.no_account_department.id,
        })

        cls.department.manager_id = cls.employee_manager
        cls.no_account_department.manager_id = cls.employee_no_account

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _make_step(self, vals):
        """建立一個掛在測試規則下的關卡。"""
        rule = self.Rule.create({
            "name": "Department Rule",
            "model_id": self.env["ir.model"]._get(
                "mfg_custom.approval.test.model",
            ).id,
        })
        return self.Step.create(dict(vals, rule_id=rule.id))

    def _make_rule(self, steps):
        return self.Rule.create({
            "name": "Department Rule",
            "model_id": self.env["ir.model"]._get(
                "mfg_custom.approval.test.model",
            ).id,
            "step_ids": [Command.create(s) for s in steps],
        })

    def _submit(self):
        rec = self.TestModel.create({})
        rec.action_submit_for_approval()
        return rec.approval_request_id

    # ------------------------------------------------------------------
    # tests
    # ------------------------------------------------------------------

    def test_01_department_mode_resolves_member_users(self):
        """部門模式只解析出該部門的在職員工。"""
        step = self._make_step({
            "name": "部門核准",
            "approver_mode": "department",
            "department_id": self.department.id,
        })
        self.assertEqual(step._resolve_approver_users(), self.user_member)

    def test_02_department_mode_excludes_manager(self):
        """部門模式不含部門經理本人，避免部門成員互相代簽。"""
        step = self._make_step({
            "name": "部門核准",
            "approver_mode": "department",
            "department_id": self.department.id,
        })
        approvers = step._resolve_approver_users()
        self.assertNotIn(self.user_manager, approvers)
        self.assertNotIn(self.user_outside, approvers)

    def test_03_department_mode_excludes_archived_employee(self):
        """已封存（離職）的員工不再列為簽核者。"""
        step = self._make_step({
            "name": "部門核准",
            "approver_mode": "department",
            "department_id": self.department.id,
        })
        self.assertTrue(step._resolve_approver_users())
        self.employee_member.action_archive()
        self.assertFalse(step._resolve_approver_users())

    def test_04_department_manager_mode(self):
        """部門經理模式解析出部門經理的帳號。"""
        step = self._make_step({
            "name": "經理核准",
            "approver_mode": "department_manager",
            "department_id": self.department.id,
        })
        self.assertEqual(step._resolve_approver_users(), self.user_manager)

    def test_04b_department_manager_mode_excludes_archived_manager(self):
        """部門經理已離職時，即使部門仍指向他也不列為簽核者。"""
        step = self._make_step({
            "name": "經理核准",
            "approver_mode": "department_manager",
            "department_id": self.department.id,
        })
        self.employee_manager.action_archive()
        self.assertFalse(step._resolve_approver_users())

    def test_05_department_mode_requires_department(self):
        """部門模式未選部門應在建檔時報錯。"""
        with self.assertRaises(ValidationError):
            self._make_step({
                "name": "壞關卡",
                "approver_mode": "department",
            })

    def test_06_department_manager_without_account_raises(self):
        """部門經理沒有綁定帳號時，送出簽核應給出明確錯誤。"""
        self._make_rule([
            {
                "name": "經理核准",
                "approver_mode": "department_manager",
                "department_id": self.no_account_department.id,
            },
        ])
        with self.assertRaises(UserError) as catcher:
            self._submit()
        self.assertIn("尚未綁定 Odoo 使用者帳號", catcher.exception.args[0])

    def test_07_department_step_creates_approval_line(self):
        """部門關卡送簽後，簽核紀錄只建立給該部門的在職員工。"""
        self._make_rule([
            {
                "name": "部門核准",
                "approver_mode": "department",
                "department_id": self.department.id,
            },
        ])
        req = self._submit()
        self.assertEqual(req.state, "pending")
        self.assertEqual(req.line_ids.user_id, self.user_member)
        req.with_user(self.user_member).action_approve()
        self.assertEqual(req.state, "approved")

    def test_08_field_mode_still_requires_res_users(self):
        """迴歸測試：field 模式仍只接受指向 res.users 的欄位。"""
        amount_field = self.env["ir.model.fields"].search(
            [
                ("model", "=", "mfg_custom.approval.test.model"),
                ("name", "=", "amount_total"),
            ],
            limit=1,
        )
        with self.assertRaises(ValidationError):
            self._make_step({
                "name": "欄位關卡",
                "approver_mode": "field",
                "approver_field_id": amount_field.id,
            })

    def test_09_employee_state_fields(self):
        """帳號的員工狀態與部門欄位要正確反映【員工】模組的資料。"""
        self.assertEqual(self.user_member.mfg_employee_state, "active_employee")
        self.assertEqual(
            self.user_member.mfg_employee_department_id, self.department,
        )
        self.assertEqual(
            self.user_outside.mfg_employee_department_id, self.other_department,
        )
        self.assertEqual(
            self.user_no_employee.mfg_employee_state, "no_employee",
        )

    def test_10_approval_line_shows_approver_info(self):
        """簽核紀錄要帶出簽核者的部門與員工狀態。"""
        self._make_rule([
            {
                "name": "部門核准",
                "approver_mode": "department",
                "department_id": self.department.id,
            },
        ])
        req = self._submit()
        line = req.line_ids
        self.assertEqual(line.approver_employee_state, "active_employee")
        self.assertEqual(line.approver_department_id, self.department)

    def test_11_step_preview_lists_approvers(self):
        """關卡預覽要列出解析出的簽核者與其員工狀態。"""
        step = self._make_step({
            "name": "部門核准",
            "approver_mode": "department",
            "department_id": self.department.id,
        })
        self.assertIn(self.user_member.display_name, step.preview_approver_info)
        self.assertIn("在職員工", step.preview_approver_info)

    def test_12_department_with_only_manager_has_no_member(self):
        """部門只有經理一人時，department 模式解析不到人（經理被刻意排除）。"""
        department = self.Department.create({"name": "只有經理的部門"})
        manager_employee = self.Employee.create({
            "name": "唯一經理",
            "department_id": department.id,
        })
        department.manager_id = manager_employee
        step = self._make_step({
            "name": "部門核准",
            "approver_mode": "department",
            "department_id": department.id,
        })
        self.assertFalse(step._resolve_approver_users())
        # 提示訊息要說明是「經理被排除」而不是讓人以為資料沒維護好
        self.assertIn("部門經理本人不列入本模式", step._approver_missing_hint())

    def test_13_archived_department_is_ignored(self):
        """已封存的部門不應該還能解析出簽核者。"""
        step = self._make_step({
            "name": "部門核准",
            "approver_mode": "department",
            "department_id": self.department.id,
        })
        self.assertTrue(step._resolve_approver_users())
        self.department.active = False
        self.assertFalse(step._resolve_approver_users())

    def test_14_missing_department_hint_does_not_show_false(self):
        """部門被刪掉後，提示訊息不能印出「False」。"""
        step = self._make_step({
            "name": "部門核准",
            "approver_mode": "department",
            "department_id": self.department.id,
        })
        self.department.unlink()
        hint = step._approver_missing_hint()
        self.assertNotIn("False", hint)
        self.assertIn("沒有指定部門", hint)

    def test_15_resolve_returns_non_sudo_users(self):
        """解析結果不該帶著 sudo 旗標，否則日後寫值會繞過 ACL。"""
        step = self._make_step({
            "name": "部門核准",
            "approver_mode": "department",
            "department_id": self.department.id,
        })
        # 測試環境本身是 superuser（su 恆為 True），要換成一般使用者才看得出差別
        users = step.with_user(self.user_member)._resolve_approver_users()
        self.assertTrue(users)
        self.assertFalse(users.env.su)

    def test_16_multiple_approvers_keep_their_own_department(self):
        """多位簽核者時，每人的部門不能配錯到別人身上。

        迴歸測試：曾經用 ``mapped()`` 取關聯欄位，而 ORM 的 ``mapped()``
        對 relational 欄位回傳的是「聯集 recordset」，會讓沒有員工檔案的
        簽核者「偷走」別人的部門。
        """
        self._make_rule([
            {
                "name": "兩人核准",
                "approver_mode": "user",
                "user_ids": [
                    Command.set([self.user_member.id, self.user_no_employee.id]),
                ],
            },
        ])
        req = self._submit()
        self.assertEqual(len(req.line_ids), 2)
        line_by_user = {line.user_id: line for line in req.line_ids}

        member_line = line_by_user[self.user_member]
        self.assertEqual(member_line.approver_employee_state, "active_employee")
        self.assertEqual(member_line.approver_department_id, self.department)

        no_employee_line = line_by_user[self.user_no_employee]
        self.assertEqual(no_employee_line.approver_employee_state, "no_employee")
        self.assertFalse(no_employee_line.approver_department_id)

    def test_17_approvers_in_different_departments(self):
        """兩位簽核者分屬不同部門時，各拿自己的部門。"""
        other_user = new_test_user(
            self.env,
            login="dept_member_other",
            groups="base.group_user,mfg_custom_base.group_user",
        )
        self.Employee.create({
            "name": "品保部小張",
            "user_id": other_user.id,
            "department_id": self.other_department.id,
        })
        self._make_rule([
            {
                "name": "兩人核准",
                "approver_mode": "user",
                "user_ids": [
                    Command.set([self.user_member.id, other_user.id]),
                ],
            },
        ])
        req = self._submit()
        line_by_user = {line.user_id: line for line in req.line_ids}
        self.assertEqual(
            line_by_user[self.user_member].approver_department_id,
            self.department,
        )
        self.assertEqual(
            line_by_user[other_user].approver_department_id,
            self.other_department,
        )

    def test_18_approver_department_is_not_stolen_from_another_user(self):
        """簽核紀錄的部門必須是「該簽核者自己的」，不能被別人借用。

        迴歸測試：曾經用 ``mapped()`` 取關聯欄位，而 ORM 的 ``mapped()``
        對 relational 欄位回傳的是「聯集 recordset」（去重後依首次出現排序），
        於是排在前面、但沒有員工檔案的簽核者會「偷走」後面那個人的部門。

        這裡刻意讓「沒有員工檔案」的簽核紀錄排在前面，讓錯配必然發生。
        """
        rule = self.Rule.create({
            "name": "先簽沒有員工檔案的人",
            "model_id": self.env["ir.model"]._get(
                "mfg_custom.approval.test.model",
            ).id,
            "step_ids": [Command.create({
                "name": "第一關",
                "approver_mode": "user",
                "user_ids": [Command.set([self.user_no_employee.id])],
            })],
        })
        record = self.TestModel.create({})
        request = self.Request.create({
            "rule_id": rule.id,
            "res_model": "mfg_custom.approval.test.model",
            "res_id": record.id,
        })
        # 再補一筆「有部門」的簽核紀錄，排在後面
        self.Line.create({
            "request_id": request.id,
            "step_id": rule.step_ids.id,
            "user_id": self.user_member.id,
        })
        line_by_user = {line.user_id: line for line in request.line_ids}
        self.assertFalse(line_by_user[self.user_no_employee].approver_department_id)
        self.assertEqual(
            line_by_user[self.user_member].approver_department_id,
            self.department,
        )
