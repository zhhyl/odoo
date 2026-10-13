# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models, tools


class MfgCustomComponentScrapStat(models.Model):
    """BOM 子件報廢統計（SQL view 聚合）。

    從 ``stock.move(is_scrap=True, state='done', raw_material_production_id)`` 入手，
    join ``mrp_production``、``mrp_bom``、``mrp_bom_line``，加上
    LATERAL 子查詢加總同 MO × 同產品的非報廢消耗量，產出每筆 scrap × BOM
    子件的標準用量、實際消耗、報廢率、有效得料率。

    用於 pivot / graph 分析：哪個 BOM 子件最容易壞、報廢率最高、
    哪張 MO 損耗最大。
    """

    _name = "mfg_custom.component.scrap.stat"
    _description = "BOM 子件報廢統計"
    _auto = False
    _order = "scrap_date desc, scrap_rate desc"
    _rec_name = "scrap_move_id"

    # ---- 來源 / 維度欄位 -------------------------------------------------

    scrap_move_id = fields.Many2one(
        "stock.move",
        "報廢 stock.move",
        readonly=True,
    )
    production_id = fields.Many2one(
        "mrp.production",
        "製造工單",
        readonly=True,
    )
    component_product_id = fields.Many2one(
        "product.product",
        "零件",
        readonly=True,
    )
    finished_product_id = fields.Many2one(
        "product.product",
        "成品",
        readonly=True,
    )
    bom_id = fields.Many2one(
        "mrp.bom",
        "BOM",
        readonly=True,
    )
    bom_line_id = fields.Many2one(
        "mrp.bom.line",
        "BOM 明細",
        readonly=True,
    )
    scrap_user_id = fields.Many2one(
        "res.users",
        "報廢者",
        readonly=True,
    )

    # ---- 數值欄位 ---------------------------------------------------------

    scrapped_qty = fields.Float(
        "報廢數量",
        digits="Product Unit of Measure",
        readonly=True,
        aggregator="sum",
    )
    standard_qty = fields.Float(
        "標準用量",
        digits="Product Unit of Measure",
        readonly=True,
        aggregator="sum",
        help="= BOM 子件用量 * (MO 數量 / BOM 數量)。",
    )
    actual_consumed_qty = fields.Float(
        "實際消耗",
        digits="Product Unit of Measure",
        readonly=True,
        aggregator="sum",
        help="= 同 MO、同產品的非報廢 stock.move (state='done') 數量加總。",
    )
    scrap_rate = fields.Float(
        "報廢率 %",
        digits=(5, 2),
        readonly=True,
        aggregator="avg",
        help="= 報廢數量 / 標準用量 * 100。",
    )
    effective_yield = fields.Float(
        "有效得料率 %",
        digits=(5, 2),
        readonly=True,
        aggregator="avg",
        help="= 100 - 報廢率。",
    )

    # ---- 日期 / 標籤欄位 --------------------------------------------------

    scrap_date = fields.Datetime(
        "報廢日期",
        readonly=True,
    )
    # 報廢原因標籤（m2m）透過 related 從 scrap_move_id 取，不存於 SQL view。
    scrap_reason_tag_ids = fields.Many2many(
        "stock.scrap.reason.tag",
        string="報廢原因",
        related="scrap_move_id.scrap_reason_tag_ids",
        readonly=True,
    )
    primary_reason_tag_id = fields.Many2one(
        "stock.scrap.reason.tag",
        "主要原因",
        compute="_compute_primary_reason_tag_id",
        readonly=True,
    )

    # ---- compute ---------------------------------------------------------

    def _compute_primary_reason_tag_id(self):
        """取第一個報廢原因標籤作為主要原因。"""
        for record in self:
            tags = record.scrap_move_id.scrap_reason_tag_ids
            record.primary_reason_tag_id = tags[:1].id if tags else False

    # ---- SQL view --------------------------------------------------------

    def init(self):
        """建立/更新 SQL view。

        以 ``stock_move.id`` 作為 view 的 id（確保唯一、與原 stock.move 一對一）。
        透過 LEFT JOIN mrp_production / mrp_bom / mrp_bom_line 補上 BOM 維度；
        透過 LATERAL 子查詢補上實際消耗量。
        """
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    sm.id                                 AS id,
                    sm.id                                 AS scrap_move_id,
                    sm.raw_material_production_id         AS production_id,
                    sm.product_id                         AS component_product_id,
                    sm.product_qty                        AS scrapped_qty,
                    sm.date                               AS scrap_date,
                    sm.create_uid                         AS scrap_user_id,
                    mo.bom_id                             AS bom_id,
                    mo.product_id                         AS finished_product_id,
                    bl.id                                 AS bom_line_id,
                    CASE
                        WHEN bom.product_qty IS NOT NULL
                             AND bom.product_qty > 0
                             AND bl.id IS NOT NULL
                        THEN bl.product_qty * (mo.product_qty / bom.product_qty)
                        ELSE 0
                    END                                  AS standard_qty,
                    COALESCE(rm_consumed.total_consumed, 0) AS actual_consumed_qty,
                    CASE
                        WHEN bom.product_qty IS NOT NULL
                             AND bom.product_qty > 0
                             AND bl.id IS NOT NULL
                             AND (bl.product_qty * mo.product_qty / bom.product_qty)
                                 > 0
                        THEN
                            sm.product_qty
                            / (bl.product_qty * (mo.product_qty / bom.product_qty))
                            * 100
                        ELSE 0
                    END                                  AS scrap_rate,
                    CASE
                        WHEN bom.product_qty IS NOT NULL
                             AND bom.product_qty > 0
                             AND bl.id IS NOT NULL
                             AND (bl.product_qty * mo.product_qty / bom.product_qty)
                                 > 0
                        THEN
                            100.0
                            - (
                                sm.product_qty
                                / (bl.product_qty * (mo.product_qty / bom.product_qty))
                                * 100
                            )
                        ELSE 100.0
                    END                                  AS effective_yield
                FROM stock_move sm
                LEFT JOIN mrp_production mo
                    ON mo.id = sm.raw_material_production_id
                LEFT JOIN mrp_bom bom
                    ON bom.id = mo.bom_id
                LEFT JOIN mrp_bom_line bl
                    ON bl.bom_id = bom.id
                    AND bl.product_id = sm.product_id
                LEFT JOIN LATERAL (
                    SELECT SUM(sm2.product_qty) AS total_consumed
                    FROM stock_move sm2
                    WHERE sm2.raw_material_production_id = sm.raw_material_production_id
                      AND sm2.product_id = sm.product_id
                      AND sm2.state = 'done'
                      AND sm2.is_scrap = FALSE
                ) rm_consumed ON TRUE
                WHERE sm.is_scrap = TRUE
                  AND sm.state = 'done'
                  AND sm.raw_material_production_id IS NOT NULL
            )
            """
            % self._table,
        )
