# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models

# 帳號對應到【員工】模組的員工檔案與否，以及是否仍在職。
# 供 res.users 與 mfg_custom.approval.line 共用，避免兩處定義不同步。
EMPLOYEE_STATE_SELECTION = [
    ("active_employee", "在職員工"),
    ("inactive_employee", "已離職"),
    ("no_employee", "非員工帳號"),
]


class ResUsers(models.Model):
    """使用者：補上「在職員工」的身分標示。

    簽核引擎一律以 ``res.users`` 記錄簽核者（能登入、有權限、留得下稽核軌跡），
    但設定簽核關卡時管理者需要分辨對方是「真正的公司員工」還是
    「只有帳號沒有員工檔案」的系統／測試／Portal 帳號，這裡提供兩個唯讀的
    衍生欄位供介面顯示。

    讀取 ``hr.employee`` 需要 ``hr.group_hr_user`` 權限，一般內部使用者讀不到；
    因此查詢一律以 ``sudo()`` 進行，且只輸出「三值狀態 + 部門」，
    不外洩薪資等敏感欄位。
    """

    _inherit = "res.users"

    mfg_employee_state = fields.Selection(
        EMPLOYEE_STATE_SELECTION,
        string="員工狀態",
        compute="_compute_mfg_employee_info",
        help="依【員工】模組的員工檔案判斷此帳號是否為在職員工。",
    )
    mfg_employee_department_id = fields.Many2one(
        "hr.department",
        string="部門",
        compute="_compute_mfg_employee_info",
    )

    def _mfg_employee_map(self):
        """批次查出 ``self`` 這些帳號在目前公司的員工檔案。

        :return: ``{res.users: hr.employee}`` 對應表；查無員工檔案的帳號
                 不會出現在表中。
        """
        if not self:
            return {}
        employees = (
            self.env["hr.employee"]
            .sudo()
            .with_context(active_test=False)
            .search([
                ("user_id", "in", self.ids),
                ("company_id", "=", self.env.company.id),
            ])
        )
        return {
            employee.user_id: employee
            for employee in employees
            if employee.user_id
        }

    @api.depends_context("company")
    def _compute_mfg_employee_info(self):
        """由員工檔案推導出員工狀態與所屬部門。

        以 ``sudo()`` 查詢：一般內部使用者沒有讀取 ``hr.employee`` 的權限，
        若不快取會把所有人都顯示成「非員工帳號」。

        員工檔案本身不在依賴清單內（跨模型且非本模型的欄位），
        因此同一個環境內不會因為員工異動而自動重算；
        實務上每次請求都是新的環境，讀到的都是最新狀態。
        """
        employee_map = self._mfg_employee_map()
        for user in self:
            employee = employee_map.get(user)
            if not employee:
                user.mfg_employee_state = "no_employee"
                user.mfg_employee_department_id = self.env["hr.department"]
                continue
            user.mfg_employee_state = (
                "active_employee" if employee.active else "inactive_employee"
            )
            user.mfg_employee_department_id = employee.department_id
