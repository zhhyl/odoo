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
    * 金額門檻：當單據上的 ``amount_field`` 落在 ``[min_amount, max_amount]`` 之間才啟用。
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
    required = fields.Boolean("必經關卡", default=True)
    note = fields.Char("說明")

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

    @api.constrains("approver_mode", "user_ids", "group_id", "approver_field_id")
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

    def _resolve_approver_users(self, record):
        """依 ``approver_mode`` 解析出本關卡的所有潛在簽核者。

        已停用（离职）的帳號不列入簽核者，否則一位員工離職就會永久卡住
        該群組的所有送簽流程。

        :param record: 對應的業務單據 recordset
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
            if not field_name or field_name not in record._fields:
                return self.env["res.users"]
            field = record._fields[field_name]
            # 簽核者欄位必須是指向 res.users 的單值欄位
            if field.comodel_name != "res.users":
                return self.env["res.users"]
            value = record[field_name]
            if not value or len(value) != 1:
                return self.env["res.users"]
            users = value
        return users.filtered(lambda u: u.active)

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
