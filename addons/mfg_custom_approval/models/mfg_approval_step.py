# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class MfgApprovalStep(models.Model):
    """簽核關卡.

    一條 ``approval.rule`` 可包含多個關卡，依 ``sequence`` 由小到大依序核可。
    每個關卡可指定：

    * ``approver_mode``：
        - ``user``：``user_ids`` 任一人核准即可
        - ``group``：``group_id`` 任一成員核准即可
        - ``group_all``：``group_id`` 全體成員皆要核可
        - ``field``：由單據上 ``approver_field`` 指定的 Many2one res.users 決定
        - ``department``：``department_id`` 的在職員工任一人核准即可（不含部門經理）
        - ``department_manager``：``department_id`` 的經理核准
    * 金額門檻：當單據上的 ``amount_field`` 落在 ``[min_amount, max_amount]``
      之間才啟用。

    簽核者一律以 ``res.users`` 表示：簽核是「某人按下按鈕」的動作與稽核軌跡，
    必須綁在能登入、有權限的身分上。``department`` / ``department_manager``
    只是用來推導「哪些帳號合格」的設定來源，資料仍來自 Odoo 內建的
    ``hr.department``，不會另建一套員工資料。
    """

    _name = "mfg_custom.approval.step"
    _description = "MFG Custom 簽核關卡"
    _order = "sequence, id"

    rule_id = fields.Many2one(
        "mfg_custom.approval.rule",
        "簽核規則",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(default=10, index=True)
    name = fields.Char("關卡名稱", required=True, translate=True)
    approver_mode = fields.Selection(
        [
            ("user", "指定人員"),
            ("group", "指定群組（任一即可）"),
            ("group_all", "指定群組（全員皆要核可）"),
            ("field", "由單據欄位決定"),
            ("department", "部門人員（任一即可）"),
            ("department_manager", "部門經理"),
        ],
        required=True,
        default="user",
    )
    user_ids = fields.Many2many(
        "res.users",
        "mfg_approval_step_user_rel",
        column1="step_id",
        column2="user_id",
        help="approver_mode 為 user 時使用；任一人核准即可通過本關卡。",
    )
    group_id = fields.Many2one(
        "res.groups",
        "指定群組",
        help="approver_mode 為 group / group_all 時使用。",
    )
    department_id = fields.Many2one(
        "hr.department",
        "指定部門",
        help=(
            "approver_mode 為 department / department_manager 時使用。"
            "部門人員取該部門的在職員工（不含部門經理本人），"
            "部門經理則取該部門設定的經理。"
        ),
    )
    approver_field_id = fields.Many2one(
        "ir.model.fields",
        "簽核者欄位",
        ondelete="set null",
        index=True,
        help=(
            "approver_mode 為「由單據欄位決定」時使用；"
            "選擇單據上指向使用者（res.users）的欄位，例如「ECO 負責人」。"
        ),
    )
    approver_field = fields.Char(
        "欄位名稱",
        related="approver_field_id.name",
        store=True,
        readonly=True,
        help="由「簽核者欄位」自動帶出的技術欄位名。",
    )
    min_amount = fields.Monetary(
        "金額門檻（最小）",
        currency_field="amount_currency_id",
        help="單據金額大於等於此值才需要走本關卡；留空表示不限制。",
    )
    max_amount = fields.Monetary(
        "金額上限（最大）",
        currency_field="amount_currency_id",
        help="單據金額小於等於此值才需要走本關卡；留空表示不限制。",
    )
    amount_field_id = fields.Many2one(
        "ir.model.fields",
        "金額欄位",
        ondelete="set null",
        index=True,
        help="單據上用來判斷金額門檻的數值欄位，例如「訂單金額」。",
    )
    amount_field = fields.Char(
        "金額欄位名稱",
        related="amount_field_id.name",
        store=True,
        readonly=True,
        help="由「金額欄位」自動帶出的技術欄位名。",
    )
    amount_currency_id = fields.Many2one(
        "res.currency",
        "金額幣別",
        default=lambda self: self.env.company.currency_id,
    )
    required = fields.Boolean(
        "必經關卡",
        default=True,
        help=(
            "必經關卡：若解析不到任何簽核者，送出簽核時會直接報錯，"
            "避免單據在無人簽核的情況下通過。"
            "取消勾選後，解析不到簽核者的關卡會被略過。"
        ),
    )
    note = fields.Char("說明")
    preview_approver_info = fields.Char(
        "解析出的簽核者",
        compute="_compute_preview_approver_info",
        help="依目前關卡設定即時解析出的簽核者，供設定時確認人選是否正確。",
    )

    _step_rule_idx = models.Index("(rule_id, sequence)")

    @api.model_create_multi
    def create(self, vals_list):
        """未指定金額欄位時，預設帶出單據上的 ``amount_total`` 欄位。"""
        IrModelFields = self.env["ir.model.fields"]
        for vals in vals_list:
            if vals.get("amount_field_id") or not vals.get("rule_id"):
                continue
            rule = self.env["mfg_custom.approval.rule"].browse(vals["rule_id"])
            field = IrModelFields.search(
                [("model", "=", rule.res_model), ("name", "=", "amount_total")],
                limit=1,
            )
            if field:
                vals["amount_field_id"] = field.id
        return super().create(vals_list)

    @api.constrains("min_amount", "max_amount")
    def _check_amount_range(self):
        for step in self:
            # 0 代表「未設定」（與 _is_active_for_record 的判斷一致），
            # 只有上下限都有設定時才需要比較。
            if step.max_amount and step.min_amount > step.max_amount:
                raise ValidationError(
                    self.env._(
                        "關卡 %s 的最小金額不可大於最大金額",
                        step.display_name,
                    )
                )

    @api.constrains(
        "approver_mode",
        "user_ids",
        "group_id",
        "approver_field_id",
        "department_id",
    )
    def _check_approver_config(self):
        for step in self:
            if step.approver_mode == "user" and not step.user_ids:
                raise ValidationError(
                    self.env._(
                        "關卡 %s 採用「指定人員」時必須填寫指定人員",
                        step.display_name,
                    )
                )
            if step.approver_mode in ("group", "group_all") and not step.group_id:
                raise ValidationError(
                    self.env._(
                        "關卡 %s 採用群組模式時必須選擇群組",
                        step.display_name,
                    )
                )
            if (
                step.approver_mode in ("department", "department_manager")
                and not step.department_id
            ):
                raise ValidationError(
                    self.env._(
                        "關卡 %s 採用部門模式時必須選擇部門",
                        step.display_name,
                    ),
                )
            if step.approver_mode == "field" and not step.approver_field_id:
                raise ValidationError(
                    self.env._(
                        "關卡 %s 採用「由單據欄位決定」時必須選擇簽核者欄位",
                        step.display_name,
                    )
                )
            if step.approver_mode == "field" and step.approver_field_id:
                field = step.approver_field_id
                if field.relation != "res.users":
                    raise ValidationError(
                        self.env._(
                            "關卡 %s 的簽核者欄位必須是指向使用者的欄位",
                            step.display_name,
                        )
                    )
                if field.model != step.rule_id.res_model:
                    raise ValidationError(
                        self.env._(
                            "關卡 %s 的簽核者欄位不屬於規則適用的單據類型",
                            step.display_name,
                        )
                    )

    def _resolve_approver_users(self, record=None):
        """依 ``approver_mode`` 解析出本關卡的所有潛在簽核者。

        已停用（離職）的帳號不列入簽核者，否則一位員工離職就會永久卡住
        該群組的所有送簽流程。

        :param record: 對應的業務單據 recordset；``field`` 模式需要它，
                       其他模式可省略
        :return: ``res.users`` recordset
        """
        self.ensure_one()
        users = self.env["res.users"]
        if self.approver_mode == "user":
            users = self.user_ids
        elif self.approver_mode in ("group", "group_all"):
            users = self.group_id.all_user_ids
        elif self.approver_mode == "field":
            field_name = self.approver_field
            if not field_name or record is None or field_name not in record._fields:
                return self.env["res.users"]
            field = record._fields[field_name]
            # 簽核者欄位必須是指向 res.users 的單值欄位
            if field.comodel_name != "res.users":
                return self.env["res.users"]
            value = record[field_name]
            if not value or len(value) != 1:
                return self.env["res.users"]
            users = value
        elif self.approver_mode == "department":
            users = self._department_member_users()
        elif self.approver_mode == "department_manager":
            users = self._department_manager_users()
        # 去掉 sudo 旗標：部門模式讀 hr.employee 時用了 sudo()，若原樣回傳，
        # 日後有人對回傳值寫值會繞過 ACL。
        return self.env["res.users"].browse(users.ids).filtered(lambda u: u.active)

    def _department_member_users(self):
        """回傳部門內在職員工所綁定的帳號（不含部門經理本人）。

        部門成員任一人核准即可通過本關卡；部門經理請另外設定
        「部門經理」關卡，避免部門成員互相代簽。

        已封存的部門、已離職的員工、以及其他公司的員工都不列入。
        """
        self.ensure_one()
        department = self.department_id.sudo()
        if not department or not department.active:
            return self.env["res.users"]
        manager = department.manager_id
        employees = department.member_ids.filtered(
            lambda employee: employee.active
            and employee != manager
            and employee.company_id == self.env.company,
        )
        return employees.mapped("user_id")

    def _department_manager_users(self):
        """回傳部門經理所綁定的帳號（經理已離職時視為沒有簽核者）。

        封存員工不會清掉 ``hr.department.manager_id``（Odoo 只會清掉
        ``parent_id`` / ``coach_id``），因此這裡要另外檢查 ``active``。
        """
        self.ensure_one()
        department = self.department_id.sudo()
        if not department or not department.active:
            return self.env["res.users"]
        manager = department.manager_id
        if not manager or not manager.active:
            return self.env["res.users"]
        return manager.user_id

    def _approver_missing_hint(self):
        """回傳解析不到簽核者時，該提示使用者檢查什麼。"""
        self.ensure_one()
        dept = self.department_id.sudo()
        if self.approver_mode in ("department", "department_manager") and not dept:
            return self.env._(
                "此關卡的簽核者模式是部門，但沒有指定部門（部門可能已被刪除）。",
            )
        if self.approver_mode == "department_manager":
            manager = dept.manager_id
            if not manager:
                return self.env._(
                    "部門「%s」尚未設定經理。",
                    dept.display_name,
                )
            if not manager.user_id:
                return self.env._(
                    "部門「%s」的經理「%s」尚未綁定 Odoo 使用者帳號，"
                    "請先於【員工】中為其建立帳號。",
                    dept.display_name,
                    manager.display_name,
                )
            return self.env._(
                "部門「%s」的經理「%s」已離職或帳號已停用。",
                dept.display_name,
                manager.display_name,
            )
        if self.approver_mode == "department":
            return self.env._(
                "部門「%s」沒有可用的在職員工（部門經理本人不列入本模式，"
                "請改用「部門經理」模式，或補上其他在職員工）。",
                dept.display_name,
            )
        return self.env._("請檢查群組成員或單據上的簽核者欄位。")

    @api.depends("approver_mode", "department_id", "user_ids", "group_id")
    def _compute_preview_approver_info(self):
        """解析出目前設定會讓哪些人簽核，並標示其部門與員工狀態。

        讓管理者在設定關卡時就能看出人選是不是在職員工，
        避免把系統／測試／Portal 帳號指派成簽核者。

        依賴只列到本模組的設定欄位；群組成員或部門成員的異動不會即時反映，
        需要重整頁面才會重算（這是設定畫面的輔助資訊，不影響實際簽核解析）。
        """
        for step in self:
            if step.approver_mode == "field":
                step.preview_approver_info = step.env._(
                    "（由單據欄位決定，無法預覽）",
                )
                continue
            users = step._resolve_approver_users()
            if not users:
                step.preview_approver_info = step.env._("（解析不到簽核者）")
                continue
            employee_map = users._mfg_employee_map()
            descriptions = []
            for user in users:
                employee = employee_map.get(user)
                if not employee:
                    state = self.env._("非員工帳號")
                elif employee.active:
                    state = self.env._("在職員工")
                else:
                    state = self.env._("已離職")
                descriptions.append(
                    self.env._(
                        "%(name)s（%(department)s／%(state)s）",
                        name=user.display_name,
                        department=(
                            employee.department_id.display_name
                            if employee and employee.department_id
                            else self.env._("無部門")
                        ),
                        state=state,
                    ),
                )
            # 部門可能有幾十人，全部列出會讓欄位長到讀不了；只留前幾個並標明總數
            visible = descriptions[:5]
            if len(descriptions) > len(visible):
                visible.append(
                    self.env._("…等 %d 位", len(descriptions)),
                )
            step.preview_approver_info = ", ".join(visible)

    def _is_active_for_record(self, record):
        """依金額區間判斷本關卡是否對 ``record`` 啟用。"""
        self.ensure_one()
        if not self.min_amount and not self.max_amount:
            return True
        if not self.amount_field or self.amount_field not in record._fields:
            return True
        amount = record[self.amount_field]
        if amount is False or amount is None:
            return True
        currency = self.amount_currency_id
        amount_field = record._fields[self.amount_field]
        # 只有 Monetary 欄位才有幣別換算，一般 Float 欄位直接比對門檻
        record_currency_name = (
            amount_field.get_currency_field(record)
            if isinstance(amount_field, fields.Monetary)
            else None
        )
        if record_currency_name and record_currency_name in record._fields:
            record_curr = record[record_currency_name]
            if record_curr and currency and currency != record_curr:
                amount = record_curr._convert(
                    amount, currency, record.env.company, fields.Date.today()
                )
        if self.min_amount and amount < self.min_amount:
            return False
        if self.max_amount and amount > self.max_amount:
            return False
        return True
