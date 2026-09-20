{
    "name": "ZenCore Salesperson Tracking",
    "summary": "Complete salesperson tracking with geofencing, visit plans, and KPI reports",
    "version": "19.0.2.0.0",
    "category": "Zencore",
    "author": "ZenCore",
    "website": "",

    "depends": [
        "sale_management",
        "base_geolocalize",
        "crm",
        "mail",
        "hr",
        "contacts",
    ],

    "data": [
        "security/salesperson_tracking_groups.xml",
        "security/salesperson_tracking_security.xml",
        "security/ir.model.access.csv",
        "data/sequences.xml",
        "views/salesperson_visit_plan_views.xml",
        "views/salesperson_tracker_views.xml",
        "views/salesperson_location_log_views.xml",
        "views/salesperson_location_backup_views.xml",
        "views/res_users_views.xml",
        "views/res_config_settings_views.xml",
        "views/templates.xml",
        "views/dashboard_template.xml",
        "views/menus.xml",
        "reports/report_visit_plan.xml",
        "reports/report_tracking_summary.xml",
        "data/location_backup_cron.xml",
        "data/idle_time_cron.xml",
    ],

    "images": [
        "static/description/icon.png",
    ],

    "assets": {
        "web.assets_backend": [
            "zencore_salesperson_tracking/static/src/js/dashboard_action.js",
            "zencore_salesperson_tracking/static/src/js/salesperson_iframe_action.js",
            "zencore_salesperson_tracking/static/src/css/dashboard_view.css",
        ],
    },

    "application": True,
    "auto_install": False,
    "installable": True,
    "license": "LGPL-3",
}