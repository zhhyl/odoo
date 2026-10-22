# Part of Odoo. See LICENSE file for full copyright and licensing details.

import ast
import logging

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain

_logger = logging.getLogger(__name__)


def _approvable_model_names(env, selectable_only=False):
    """回傳已掛載簽核 mixin 的模型技術名清單（遞增排序）。

    直接掃描 ``env.registry.models`` 而非 ``env[model_name]``：
    模組安裝初期（資料載入階段）模型可能尚未 setup 完成，
    用 ``env[...]`` 會出現 KeyError。

    :param selectable_only: 只回傳管理者可選的模型（排除測試用模型）
    """
    mixin_cls = env.registry.models.get("mfg_custom.approval.mixin")
    if mixin_cls is None:
        return []
    names = []
    for name, cls in env.registry.models.items():
        if cls._abstract or not issubclass(cls, mixin_cls):
            continue
        if selectable_only and getattr(cls, "_mfg_custom_approval_hidden", False):
            continue
        names.append(name)
    return sorted(names)


class MfgApprovalRule(models.Model):
    """簽核規則.

    每一條規則描述「哪些單據要走哪些關卡」。可依 ``model_id``（適用單據類型）
    與 ``domain``（適用條件）動態匹配。匹配順序以 ``sequence`` 為主（小的優先），
    命中第一條即採用。

    管理員透過前端介面設定本模型：``model_id`` 是下拉選單、``domain`` 使用
    Odoo 原生條件建構器（domain widget），完全不需要撰寫程式碼。
    """

    _name = "mfg_custom.approval.rule"
    _description = "MFG Custom 簽核規則"
    _order = "sequence, id"

    name = fields.Char("規則名稱", required=True, translate=True)
    active = fields.Boolean(default=True, index=True)
    model_id = fields.Many2one(
        "ir.model",
        "適用單據類型",
        required=True,
        ondelete="cascade",
        index=True,
        # 下拉只列出已掛載簽核功能（且非測試用）的模型
        domain=lambda env: [
            ("model", "in", _approvable_model_names(env, selectable_only=True))
        ],
        help="要套用此簽核流程的單據類型。只能選擇已掛載簽核功能的單據。",
    )
    res_model = fields.Char(
        "技術模型名",
        related="model_id.model",
        store=True,
        readonly=True,
        index=True,
        help="技術模型名稱，如 plm_custom.eco、mrp.production。（由「適用單據類型」自動帶出）",
    )
    model_name = fields.Char(
        "模型技術名",
        compute="_compute_model_name",
        help="供前端條件建構器使用，指定要對哪個模型建立條件。",
    )
    model_display = fields.Char(
        "適用單據",
        compute="_compute_model_display",
        help="顯示用的單據名稱。",
    )
    domain = fields.Char(
        "適用條件 (domain)",
        help=(
            "符合條件的單據才走此規則；留空代表所有此類單據都適用。"
            "可使用右側的條件建構器設定，不需手寫。"
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

    @api.depends("model_id")
    def _compute_model_name(self):
        for rec in self:
            rec.model_name = rec.model_id.model

    @api.depends("model_id")
    def _compute_model_display(self):
        for rec in self:
            if not rec.model_id:
                rec.model_display = False
            else:
                rec.model_display = "%s（%s）" % (
                    rec.model_id.name or rec.model_id.model,
                    rec.model_id.model,
                )

    @api.model
    def _get_approvable_models(self):
        """回傳目前掛載簽核 mixin 的模型技術名清單（遞增排序）。

        以 runtime 掃描 registry 得出，不需人工維護清單。
        """
        return _approvable_model_names(self.env)

    @api.model
    def _get_selectable_models(self):
        """回傳管理者在「適用單據類型」下拉選單中可選的模型。

        與 ``_get_approvable_models()`` 的差別：測試用模型
        （標記 ``_mfg_custom_approval_hidden``）不在此清單中，
        避免正式環境的管理介面出現測試模型。
        """
        return _approvable_model_names(self.env, selectable_only=True)

    @api.constrains("model_id")
    def _check_model_is_approvable(self):
        """規則只能套用在已掛載簽核 mixin 的模型上。"""
        approvable = self._get_approvable_models()
        for rec in self:
            if not rec.model_id:
                continue
            if rec.model_id.model not in approvable:
                raise ValidationError(
                    self.env._(
                        "模型「%s」尚未掛載簽核功能，無法設定簽核規則。\n"
                        "可套用的單據類型：%s",
                        rec.model_id.model,
                        ", ".join(approvable) or "（無）",
                    )
                )

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
            rec._check_domain_fields(parsed)

    def _check_domain_fields(self, parsed):
        """確認 domain 中引用的欄位確實存在於規則適用的模型。

        domain 錯誤會讓單據表單在計算「符合的簽核規則」時直接拋錯，
        因此在儲存規則時就擋下，避免整張單據開不起來。
        """
        self.ensure_one()
        if not self.res_model:
            return True
        model_fields = set(
            self.env["ir.model.fields"]._get_fields_cached(self.res_model)
        )
        for leaf in parsed:
            if (
                isinstance(leaf, (list, tuple))
                and len(leaf) == 3
                and isinstance(leaf[0], str)
            ):
                name = leaf[0]
                if name not in model_fields and name not in (
                    "id", "create_uid", "write_uid", "create_date", "write_date",
                    "display_name",
                ):
                    raise ValidationError(
                        self.env._(
                            "簽核規則的適用條件使用了不存在的欄位「%s」"
                            "（模型：%s）",
                            name,
                            self.res_model,
                        )
                    )
            elif isinstance(leaf, (list, tuple)):
                self._check_domain_fields(leaf)
        return True

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
            [
                ("res_model", "=", res_model),
                ("active", "=", True),
                ("company_id", "in", (False, self.env.company.id)),
            ],
            order="sequence asc, id asc",
        )
        # 單據端可透過 _get_approval_rule_domain() 追加額外條件（與規則 domain 取 AND）
        extra_domain = []
        getter = getattr(record, "_get_approval_rule_domain", None)
        if callable(getter):
            extra_domain = getter() or []
        for rule in rules:
            rule_domain = rule._parse_domain()
            if rule_domain is None:
                continue
            domains = [rule_domain]
            if extra_domain:
                domains.append(Domain(extra_domain))
            try:
                matched = record.filtered_domain(Domain.AND(domains))
            except ValueError as err:
                # domain 引用了不存在的欄位：略過這條規則，
                # 不可讓整張單據的表單開不起來（錯誤已於儲存規則時擋下）
                _logger.warning(
                    "mfg_custom.approval: 規則「%s」的適用條件無法套用：%s",
                    rule.display_name,
                    err,
                )
                continue
            if matched:
                return rule
        return self.browse()

    def _parse_domain(self):
        """將字串 domain 解析為 ``Domain``；無法解析時回傳 None。"""
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
