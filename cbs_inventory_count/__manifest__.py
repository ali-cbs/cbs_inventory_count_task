# -*- coding: utf-8 -*-

{
    "name": "Inventory Count Review",
    "summary": "Store and review inventory count lines before applying to stock.",
    "version": "1.0.0",

    "author": "ByConsult",
    "website": "https://www.cbs.jo/",
    "license": "OPL-1",

    "depends": [
        "stock",
        "mail",
        "account",
    ],

    "data": [
        # security
        'security/security.xml',
        "security/ir.model.access.csv",
        # views
        "views/inventory_count_line_views.xml",
        "views/inventory_count_session_views.xml",
        "views/stock_menus.xml",
        # reports
        "reports/inventory_count_reports.xml",
    ],
}
