# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class MfgQualityCheck(models.Model):
    """MFG 自製品檢單（檢驗執行單）。

    生命週期：

    ``draft → in_progress → passed / failed / conditional``
    （建立後也可 ``→ cancelled``）

    * ``action_start()``：將 ``point_id`` 之 ``check_line_ids`` 規格帶入。
    * ``action_pass()``：判定合格（檢驗員最後按）。
    * ``action_fail(reason)``：判定不合格，留下原因並建立或關聯改善單。
    * ``action_conditional()``：特採（讓步接收），不擋出貨／入庫。
    * ``action_cancel()``：取消。

    NOTE：``corrective_action_id`` 為可選的 ``mfg_custom.issue`` Many2one，
    但目前 issue 模組尚未上線；欄位僅以 Many2one reference 存在，使用者必須
    自行建立 issue 後再回填。前端 help 文字已說明。
    """

    _name = "mfg_custom.quality.check"
    _description = "MFG 品檢單"
    _inherit = ["mail.thread"]
    _order = "inspection_date desc, id desc"
    _rec_name = "name"

    name = fields.Char(
        "品檢單號",
        default="New",
        copy=False,
        readonly=True,
        index=True,
    )
    state = fields.Selection(
        [
            ("draft", "待執行"),
            ("in_progress", "檢驗中"),
            ("passed", "合格"),
            ("failed", "不合格"),
            ("conditional", "特採"),
            ("cancelled", "取消"),
        ],
        string="狀態",
        default="draft",
        required=True,
        index=True,
        tracking=True,
    )
    point_id = fields.Many2one(
        "mfg_custom.quality.point",
        "品檢點",
        required=True,
        index=True,
    )
    production_id = fields.Many2one(
        "mrp.production",
        "相關 MO",
        index=True,
        help="由 MO 開工／完工流程自動帶入，可手動調整。",
    )
    workorder_id = fields.Many2one(
        "mrp.workorder",
        "相關工序",
        index=True,
    )
    picking_id = fields.Many2one(
        "stock.picking",
        "入庫單",
        index=True,
    )
    lot_id = fields.Many2one(
        "stock.lot",
        "批號",
        index=True,
    )
    product_id = fields.Many2one(
        "product.product",
        "檢驗產品",
        required=True,
        index=True,
    )
    qty_to_check = fields.Float(
        "檢驗數量",
        digits="Product Unit",
        required=True,
        default=1.0,
    )
    check_line_ids = fields.One2many(
        "mfg_custom.quality.check.line",
        "check_id",
        "檢驗結果",
    )
    inspector_id = fields.Many2one(
        "res.users",
        "檢驗員",
        default=lambda self: self.env.user,
        tracking=True,
    )
    inspection_date = fields.Datetime(
        "檢驗時間",
        default=fields.Datetime.now,
        required=True,
        index=True,
    )
    failure_reason = fields.Html("不合格原因")
    corrective_action_id = fields.Many2one(
        "mfg_custom.issue",
        "對應改善單",
        help="待 mfg_custom_issue 模組建好後生效；目前僅作為 Many2one reference。",
    )
    notes = fields.Text("備註")
    company_id = fields.Many2one(
        "res.company",
        "公司",
        index=True,
        default=lambda self: self.env.company,
    )

    _check_state_product_idx = models.Index(
        "(state, product_id, inspection_date)",
    )
    _check_company_uniq = models.Constraint(
        "UNIQUE(name, company_id)",
        "同公司內品檢單號不可重複。",
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "mfg_custom.quality.check",
                )
        return super().create(vals_list)

    @api.onchange("point_id")
    def _onchange_point_id(self):
        """選擇品檢點時，自動帶入產品與抽樣數。"""
        if self.point_id:
            self.product_id = self.point_id.product_id or self._guess_product_from_context()
            self.qty_to_check = self.point_id.sample_qty or 1.0

    def _guess_product_from_context(self):
        """從 context 嘗試取得當前 product_id。

        主要給呼叫端（mrp.workorder 等）的 form 提供預設值。
        """
        return bool(self.env.context.get("default_production_id"))

    # ------------------------------------------------------------------
    # state transitions
    # ------------------------------------------------------------------

    def action_start(self):
        """從品檢點帶入檢項規格，並將單據狀態切到 ``in_progress``。"""
        self.ensure_one()
        if self.state != "draft":
            raise UserError(
                self.env._(
                    "%(name)s 已在「%(state)s」狀態，無法開始檢驗。",
                    name=self.display_name,
                    state=self.state,
                ),
            )
        if not self.point_id.check_line_ids:
            raise UserError(
                self.env._(
                    "品檢點「%(point)s」尚未設定任何檢項。",
                    point=self.point_id.display_name,
                ),
            )
        self._populate_check_lines_from_point()
        self.write({"state": "in_progress"})
        return True

    def _populate_check_lines_from_point(self):
        """將 ``point_id.check_line_ids`` 複製為本張單的檢驗結果。"""
        self.ensure_one()
        Line = self.env["mfg_custom.quality.check.line"]
        # 移除先前帶入但仍 pending 的，避免重複點 start 時堆疊。
        self.check_line_ids.filtered(lambda line: line.result == "pending").unlink()
        new_lines = []
        for pl in self.point_id.check_line_ids:
            new_lines.append(
                {
                    "check_id": self.id,
                    "sequence": pl.sequence,
                    "name": pl.name,
                    "spec_value": pl.spec_value,
                    "min_value": pl.min_value,
                    "max_value": pl.max_value,
                    "uom_id": pl.uom_id.id,
                    "is_critical": pl.is_critical,
                    "result": "pending",
                },
            )
        if new_lines:
            Line.create(new_lines)

    def action_pass(self):
        """將單據標記為「合格」。"""
        self.ensure_one()
        if self.state not in ("draft", "in_progress"):
            raise UserError(
                self.env._(
                    "%(name)s 狀態為「%(state)s」，無法判定為合格。",
                    name=self.display_name,
                    state=self.state,
                ),
            )
        self._check_required_lines_filled()
        self._check_critical_failures()
        self.write({"state": "passed", "failure_reason": False})
        return True

    def action_fail(self, reason=None):
        """將單據標記為「不合格」並寫入原因。

        :param reason: 不合格原因字串；為 ``None`` 時沿用欄位既有值。
        """
        self.ensure_one()
        if self.state not in ("draft", "in_progress"):
            raise UserError(
                self.env._(
                    "%(name)s 狀態為「%(state)s」，無法判定為不合格。",
                    name=self.display_name,
                    state=self.state,
                ),
            )
        self._check_required_lines_filled()
        vals = {"state": "failed"}
        if reason:
            vals["failure_reason"] = reason
        if not self.failure_reason and not reason:
            raise UserError(
                self.env._(
                    "請填寫不合格原因後再判定為不合格。",
                ),
            )
        self.write(vals)
        return True

    def action_conditional(self):
        """特採（讓步接收）。不擋後續入庫。"""
        self.ensure_one()
        if self.state not in ("draft", "in_progress"):
            raise UserError(
                self.env._(
                    "%(name)s 狀態為「%(state)s」，無法改判為特採。",
                    name=self.display_name,
                    state=self.state,
                ),
            )
        self.write({"state": "conditional"})
        return True

    def action_cancel(self):
        """取消品檢單。"""
        self.ensure_one()
        if self.state == "cancelled":
            return True
        if self.state in ("passed", "failed", "conditional"):
            raise UserError(
                self.env._(
                    "%(name)s 已結案（%(state)s），不可取消；請用調整單據或重開。",
                    name=self.display_name,
                    state=self.state,
                ),
            )
        self.write({"state": "cancelled"})
        return True

    def action_reset_to_draft(self):
        """由 in_progress 重回 draft（用於品檢員想重新帶入規格）。"""
        self.ensure_one()
        if self.state != "in_progress":
            raise UserError(
                self.env._(
                    "只有「檢驗中」狀態能重置回「待執行」。",
                ),
            )
        self.write({"state": "draft"})
        return True

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _check_required_lines_filled(self):
        """確保所有非 N/A 的檢項都已填入判定結果。"""
        self.ensure_one()
        pending = self.check_line_ids.filtered(
            lambda line: line.result == "pending",
        )
        if pending:
            raise UserError(
                self.env._(
                    "尚有 %(count)s 項結果未判定：%(names)s",
                    count=len(pending),
                    names=", ".join(pending.mapped("name")),
                ),
            )

    def _check_critical_failures(self):
        """若有任何關鍵項判定為「不合格」 → 阻擋 ``action_pass``。"""
        self.ensure_one()
        critical_fails = self.check_line_ids.filtered(
            lambda line: line.is_critical and line.result == "fail",
        )
        if critical_fails:
            raise UserError(
                self.env._(
                    "關鍵項不合格，不可判定整張單為合格：%(names)s",
                    names=", ".join(critical_fails.mapped("name")),
                ),
            )

    def action_view_point(self):
        """從品檢單跳到所屬品檢點。"""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "mfg_custom_quality.mfg_quality_point_action",
        )
        action["views"] = [(False, "form")]
        action["res_id"] = self.point_id.id
        return action

    # ------------------------------------------------------------------
    # constraints / onchange
    # ------------------------------------------------------------------

    @api.constrains("qty_to_check")
    def _check_qty_to_check(self):
        for rec in self:
            if rec.qty_to_check <= 0:
                raise ValidationError(
                    self.env._(
                        "「%s」的檢驗數量必須大於 0。", rec.display_name,
                    ),
                )
