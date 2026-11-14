
import { registry } from "@web/core/registry";
import { Component, xml } from "@odoo/owl";

export class SalespersonIframeAction extends Component {
    static template = xml`
        <div class="h-100 w-100" style="position:relative; min-height:600px;">
            <iframe t-att-src="props.action.params.url"
                    style="position:absolute; inset:0; width:100%; height:100%; border:0; display:block;"
                    t-att-title="props.action.params.title or 'Salesperson Tracking'"
                    allow="geolocation; camera"/>
        </div>
    `;
    static props = ["*"];
}

registry.category("actions").add("salesperson_iframe_action", SalespersonIframeAction);
