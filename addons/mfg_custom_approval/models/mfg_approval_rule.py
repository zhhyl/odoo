# Part of Odoo. See LICENSE file for full copyright and licensing details.

import ast

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain


class MfgApprovalRule(models.Model):
    """簽核規則.

    每一條規則描述「哪些單據要走哪些關卡」。可依 ``res_model`` 與 ``domain``
    動態匹配。匹配順序以 ``sequence`` 為主（小的優先），命中第一條即採用。
    """

    _name = "mfg_custom.approval.rule"
    _description = "MFG Custom 簽核規則"
    _order = "sequence, id"

    name = fields.Char("規則名稱", required=True, translate=True)
    active = fields.Boolean(default=True, index=True)
    res_model = fields.Char(
        "適用 Model",
        required=True,
        index=True,
        help="技術模型名稱，如 plm_custom.eco, sale.order, mrp.production",
    )
    domain = fields.Char(
        "適用條件 (domain)",
        help=(
            "符合條件的單據才走此規則；"
            "例：[('amount_total', '>', 1000000)]"
        ),
    )
    sequence = fields.Integer(default=10, index=True)
    step_ids = fields.One2many(
        "mfg_custom.approval.step",
        "rule_id",
        "簽核關卡",
    )
    company_id = fields.Many2one(
        "res.company",
        "公司",
        default=lambda self: self.env.company,
        index=True,
    )
    note = fields.Text("說明")

    _rule_model_uniq = models.Constraint(
        "UNIQUE(res_model, name, company_id)",
        "同公司內同一 model 的規則名稱不可重複。",
    )
    _rule_seq_idx = models.Index("(sequence, res_model)")

    @api.constrains("domain")
    def _check_domain(self):
        for rec in self:
            if not rec.domain:
                continue
            try:
                parsed = ast.literal_eval(rec.domain)
            except (ValueError, SyntaxError) as err:
                raise ValidationError(
                    self.env._("簽核規則 domain 語法錯誤：%s", err)
                ) from err
            if not isinstance(parsed, (list, tuple)):
                raise ValidationError(
                    self.env._("簽核規則 domain 必須是 list 或 tuple")
                )

    @api.model
    def _match_rule(self, res_model, record):
        """找出符合條件的第一條 ``approval.rule``。

        :param res_model: 技術模型名稱
        :param record: 該模型的 recordset（用以 evaluate domain）
        :return: 單一 ``mfg_custom.approval.rule`` 紀錄，或空的 recordset
        """
        if not record or not record.ids:
            return self.browse()
        rules = self.search(
            [("res_model", "=", res_model), ("active", "=", True)],
            order="sequence asc, id asc",
        )
        for rule in rules:
            extra = rule._parse_domain()
            if extra is None:
                continue
            if record.filtered_domain(Domain.AND([extra])):
                return rule
        return self.browse()

    def _parse_domain(self):
        """將字串 domain 解析為 list/tuple；空字串回傳空 list。"""
        self.ensure_one()
        if not self.domain:
            return Domain.TRUE
        try:
            parsed = ast.literal_eval(self.domain)
        except (ValueError, SyntaxError):
            return None
        if not isinstance(parsed, (list, tuple)):
            return None
        return Domain(parsed)
