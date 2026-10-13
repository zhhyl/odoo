# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class MfgQualityPoint(models.Model):
    """MFG 自製品檢點（規格書）。

    描述「在什麼時機、對什麼產品／工序、用什麼方法、抽多少樣本、
    抽哪些檢項」這個規格本身。
    本模組不自動觸發建立 ``mfg_custom.quality.check``；
    觸發流程（MO 開工／完工、工序完工、入庫前）由呼叫端（其它模組或人工）
    在 ``action_start()`` 後再決定行為。
    """

    _name = "mfg_custom.quality.point"
    _description = "MFG 品檢點"
    _inherit = ["mail.thread"]
    _order = "sequence_default, name"
    _rec_name = "name"

    sequence_default = fields.Integer(default=10)
    name = fields.Char("品檢項目", required=True)
    code = fields.Char(
        "編號",
        copy=False,
        index=True,
        default=lambda self: self.env["ir.sequence"].next_by_code(
            "mfg_custom.quality.point",
        ),
    )
    product_id = fields.Many2one(
        "product.product",
        "適用產品",
        index=True,
        help="留空代表適用於「適用分類」內所有產品。",
    )
    product_category_id = fields.Many2one(
        "product.category",
        "適用分類",
        help="未指定產品時，依分類套用。",
    )
    operation = fields.Char(
        "適用工序",
        help="對應 ``mrp.routing.operation`` 的工序名稱（非必填）。",
    )
    workcenter_id = fields.Many2one(
        "mrp.workcenter",
        "適用工作中心",
        help="搭配 ``trigger_on='workorder_finish'`` 使用，限制生效工序。",
    )
    spec = fields.Html("規格說明")
    sample_qty = fields.Integer("抽樣數", default=1)
    method = fields.Selection(
        [
            ("visual", "目視"),
            ("measure", "量測"),
            ("functional", "功能測試"),
            ("document", "文件核對"),
        ],
        string="檢驗方式",
        default="measure",
        required=True,
    )
    trigger_on = fields.Selection(
        [
            ("production_start", "MO 開工"),
            ("production_finish", "MO 完工"),
            ("workorder_finish", "工序完工"),
            ("incoming", "入庫前"),
            ("manual", "手動"),
        ],
        string="自動觸發時機",
        default="manual",
        required=True,
        index=True,
    )
    check_line_ids = fields.One2many(
        "mfg_custom.quality.point.line",
        "point_id",
        "檢查項目",
    )
    active = fields.Boolean(default=True, index=True)
    notes = fields.Text("備註")
    company_id = fields.Many2one(
        "res.company",
        "公司",
        index=True,
        default=lambda self: self.env.company,
    )

    _point_company_uniq = models.Constraint(
        "UNIQUE(code, company_id)",
        "同公司內品檢點編號不可重複。",
    )
    _point_product_idx = models.Index("(product_id, trigger_on)")
    _point_category_idx = models.Index("(product_category_id, trigger_on)")

    @api.constrains("sample_qty")
    def _check_sample_qty(self):
        for rec in self:
            if rec.sample_qty < 1:
                raise ValidationError(
                    self.env._("抽樣數必須 ≥ 1（%s）", rec.display_name),
                )

    @api.constrains("product_id", "product_category_id")
    def _check_product_scope(self):
        for rec in self:
            if rec.product_id and rec.product_category_id:
                # 已綁定產品時，分類應與產品所屬分類一致，否則規格語意不清。
                if rec.product_id.categ_id != rec.product_category_id:
                    raise ValidationError(
                        self.env._(
                            "品檢點「%(name)s」指定的產品分類 (%(cat)s) "
                            "與產品實際所屬分類不符。",
                            name=rec.display_name,
                            cat=rec.product_category_id.display_name,
                        ),
                    )

    def action_view_checks(self):
        """從品檢點開啟相關品檢單的列表。"""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "mfg_custom_quality.mfg_quality_check_action",
        )
        action["domain"] = [("point_id", "=", self.id)]
        action["context"] = {
            "default_point_id": self.id,
            "default_product_id": self.product_id.id,
        }
        return action

    def copy(self, default=None):
        default = dict(default or {})
        default.setdefault("code", _("New"))
        return super().copy(default=default)
