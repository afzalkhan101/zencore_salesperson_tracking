
import { registry } from "@web/core/registry";
import { Component, xml } from "@odoo/owl";

export class SalespersonDashboardAction extends Component {
    static template = xml`
        <div class="h-100 w-100" style="position:relative; min-height:600px;">
            <iframe src="/salesperson/dashboard"
                    style="position:absolute; inset:0; width:100%; height:100%; border:0; display:block;"
                    title="Salesperson Dashboard"/>
        </div>
    `;
    static props = ["*"];
}

registry.category("actions").add("salesperson_dashboard_iframe", SalespersonDashboardAction);
