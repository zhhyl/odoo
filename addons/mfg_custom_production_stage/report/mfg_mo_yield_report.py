# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, models


class MfgCustomMoYieldReport(models.AbstractModel):
    """MO 含良率總覽報告（PDF 樣板）。

    不覆寫 ``mrp_report_mo_overview``；僅在 ``mfg_custom_production_stage``
    模組下額外提供「列印含良率」視角，補上：

    * 生產階段、期望得料率 vs 實際得料率（彩色裝飾）
    * 報廢子件清單（從 ``stock.move(is_scrap=True)`` 取）
    * PASS / FAIL 結論
    """

    _name = "report.mfg_custom_production_stage.mfg_mo_yield_report"
    _description = "MO 含良率總覽報告"

    @api.model
    def _get_report_values(self, docids, data=None):
        """回傳 QWeb 樣板所需資料。

        樣板中會迭代 ``docs``，並以 ``scrap_data[mo.id]`` 取出每張 MO 對應的
        報廢子件 ``stock.move`` recordset。
        """
        docs = self.env["mrp.production"].browse(docids)
        scrap_data = self._get_scrap_data(docids)
        return {
            "doc_ids": docids,
            "doc_model": "mrp.production",
            "docs": docs,
            "scrap_data": scrap_data,
            "format_qty": self._format_qty,
            "render_pass": self._render_pass,
        }

    @api.model
    def _get_scrap_data(self, docids):
        """以 MO id 為 key，回傳對應的報廢子件 recordset。

        一次性 ``search`` 後分組，避免 N+1 查詢。
        """
        scrap_data = {mo_id: self.env["stock.move"] for mo_id in (docids or ())}
        if not docids:
            return scrap_data
        scrap_moves = self.env["stock.move"].search(
            [
                ("is_scrap", "=", True),
                ("raw_material_production_id", "in", docids),
                ("state", "=", "done"),
            ],
        )
        for move in scrap_moves:
            key = move.raw_material_production_id.id
            scrap_data[key] |= move
        return scrap_data

    @api.model
    def _format_qty(self, qty, uom):
        """格式化數量字串，例如 ``'12.00 Units'``。"""
        if not uom:
            return f"{qty:.2f}"
        return f"{qty:.2f} {uom.name}"

    @api.model
    def _render_pass(self, mo):
        """回傳該 MO 的 PASS / FAIL 結論字串與 CSS class。

        ``state != 'done'`` 時不判定（樣板上顯示 ``N/A``）。
        """
        if mo.state != "done":
            return {"label": "N/A", "klass": "text-muted"}
        if mo.mfg_custom_yield_rate >= mo.mfg_custom_expected_yield_rate:
            return {"label": "PASS", "klass": "text-success"}
        return {"label": "FAIL", "klass": "text-danger"}
