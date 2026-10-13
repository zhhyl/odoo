MFG Custom - Quality Inspection
===============================

以 `mfg_custom_base` 為基礎，提供 Community 版缺漏的品質檢驗流程：

* 品檢點（規格書）+ 品檢細項（上下限）
* 品檢單（MO／工序／入庫單關聯）+ 檢驗結果（量測值）
* 不合格自動建立改善單（待 ``mfg_custom_issue`` 模組上線後生效）

依賴
----

* ``mfg_custom_base`` — 共用 mixin、群組、序號
* ``mrp`` — ``mrp.production`` / ``mrp.workorder`` / ``mrp.workcenter``
* ``stock`` — ``stock.picking`` / ``stock.lot``

安裝
----

直接 ``./odoo-bin -i mfg_custom_quality`` 即可。

主要選單：MFG Custom → 品檢。

測試
----

::

    ./odoo-bin -d testdb --test-enable --stop-after-init \
        --test-tags=/mfg_custom_quality \
        --addons-path=addons,odoo/addons -i mfg_custom_quality
